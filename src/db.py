"""Lớp truy cập SQLite cho bộ đệm telemetry (store-and-forward).

SQLite là đồng bộ (blocking). Để không chặn vòng lặp asyncio, các worker gọi
các hàm này thông qua ``asyncio.to_thread(...)``. Một khoá threading bảo vệ
connection khi bị gọi từ nhiều thread của executor.

Bật WAL (Write-Ahead Logging) để tăng tốc ghi và giảm hao mòn thẻ SD.
"""
from __future__ import annotations

import os
import shutil
import sqlite3
import threading
import time
from typing import Iterable, List, Sequence, Tuple

# Kiểu một bản ghi đọc ra: (id, node_id, payload_json, created_at)
BufferRow = Tuple[int, str, str, float]


class Database:
    def __init__(self, path: str, max_buffer_rows: int = 200_000) -> None:
        self.path = path
        self.max_buffer_rows = max_buffer_rows
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._configure()
        self._init_schema()

    def _configure(self) -> None:
        with self._lock:
            # WAL: ghi nhanh, ít khoá đọc; synchronous=NORMAL an toàn với WAL.
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
            self._conn.execute("PRAGMA temp_store=MEMORY;")
            self._conn.commit()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS telemetry_buffer (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id     TEXT NOT NULL,
                    payload     TEXT NOT NULL,           -- JSON payload
                    created_at  REAL NOT NULL,           -- epoch giây
                    status      INTEGER NOT NULL DEFAULT 0  -- 0=cho gui, 1=da gui
                )
                """
            )
            # Phục vụ truy vấn FIFO các bản ghi đang chờ.
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_buffer_status_id "
                "ON telemetry_buffer(status, id)"
            )
            self._conn.commit()

    # ------------------------------------------------------------------ ghi
    def insert_batch(self, items: Sequence[Tuple[str, str, float]]) -> int:
        """Ghi cả LÔ trong MỘT transaction duy nhất.

        items: list các (node_id, payload_json, created_at).
        Trả về số bản ghi đã ghi.
        """
        if not items:
            return 0
        with self._lock:
            self._conn.executemany(
                "INSERT INTO telemetry_buffer (node_id, payload, created_at, status) "
                "VALUES (?, ?, ?, 0)",
                items,
            )
            self._conn.commit()
            self._enforce_row_limit_locked()
            return len(items)

    # ------------------------------------------------------------------ đọc
    def fetch_pending(self, limit: int) -> List[BufferRow]:
        """Đọc FIFO (cũ trước) các bản ghi status=0."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, node_id, payload, created_at "
                "FROM telemetry_buffer WHERE status=0 ORDER BY id ASC LIMIT ?",
                (limit,),
            )
            return cur.fetchall()

    def mark_sent(self, ids: Iterable[int]) -> None:
        """Đánh dấu đã gửi (status=1) sau khi nhận PUBACK."""
        ids = list(ids)
        if not ids:
            return
        with self._lock:
            self._conn.executemany(
                "UPDATE telemetry_buffer SET status=1 WHERE id=?",
                [(i,) for i in ids],
            )
            self._conn.commit()

    def pending_count(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM telemetry_buffer WHERE status=0"
            ).fetchone()[0]

    def total_count(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM telemetry_buffer"
            ).fetchone()[0]

    # -------------------------------------------------------------- bảo trì
    def _enforce_row_limit_locked(self) -> None:
        """Chống tràn: nếu vượt trần, xoá bản ghi ĐÃ gửi cũ nhất trước."""
        total = self._conn.execute(
            "SELECT COUNT(*) FROM telemetry_buffer"
        ).fetchone()[0]
        if total <= self.max_buffer_rows:
            return
        over = total - self.max_buffer_rows
        # Ưu tiên xoá status=1 (đã gửi) cũ nhất; nếu vẫn thừa thì đành xoá cả
        # status=0 cũ nhất để giữ thiết bị sống (đánh đổi mất dữ liệu rất cũ).
        self._conn.execute(
            "DELETE FROM telemetry_buffer WHERE id IN ("
            "  SELECT id FROM telemetry_buffer ORDER BY status DESC, id ASC LIMIT ?"
            ")",
            (over,),
        )
        self._conn.commit()

    def cleanup_sent(self, batch: int) -> int:
        """Xoá bớt bản ghi ĐÃ gửi (status=1) cũ nhất. Trả về số dòng đã xoá."""
        with self._lock:
            cur = self._conn.execute(
                "DELETE FROM telemetry_buffer WHERE id IN ("
                "  SELECT id FROM telemetry_buffer WHERE status=1 ORDER BY id ASC LIMIT ?"
                ")",
                (batch,),
            )
            self._conn.commit()
            deleted = cur.rowcount
        return deleted

    def checkpoint(self) -> None:
        """Gộp WAL vào file chính để giải phóng dung lượng đĩa."""
        with self._lock:
            self._conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            self._conn.commit()

    def disk_usage_percent(self) -> float:
        """% dung lượng đã dùng của phân vùng chứa file DB."""
        target = os.path.dirname(os.path.abspath(self.path)) or "."
        usage = shutil.disk_usage(target)
        return usage.used / usage.total * 100.0

    def close(self) -> None:
        with self._lock:
            self._conn.close()
