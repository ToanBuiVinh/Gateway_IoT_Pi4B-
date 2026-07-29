"""Bộ đệm cục bộ dùng SQLite (store-and-forward).

Giữ dữ liệu khi mất kết nối cloud và tự đẩy lại khi có mạng.
An toàn khi truy cập từ nhiều luồng nhờ khoá + connection riêng.
"""
from __future__ import annotations

import os
import sqlite3
import threading
from typing import List, Tuple

from .models import Reading


class Storage:
    def __init__(self, path: str, max_buffer_rows: int = 100_000) -> None:
        self.path = path
        self.max_buffer_rows = max_buffer_rows
        self._lock = threading.Lock()
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        # check_same_thread=False vì có nhiều luồng dùng chung; đã có _lock bảo vệ.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._conn.execute(
                """
                CREATE TABLE IF NOT EXISTS readings (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    node_id     TEXT NOT NULL,
                    gateway_id  TEXT NOT NULL,
                    ts          REAL NOT NULL,
                    metrics     TEXT NOT NULL,
                    sent        INTEGER NOT NULL DEFAULT 0
                )
                """
            )
            self._conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_readings_sent ON readings(sent, id)"
            )
            self._conn.commit()

    def save(self, reading: Reading) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO readings (node_id, gateway_id, ts, metrics, sent) "
                "VALUES (?, ?, ?, ?, 0)",
                (reading.node_id, reading.gateway_id, reading.ts, reading.to_json_metrics()),
            )
            self._conn.commit()
            self._enforce_limit()

    def _enforce_limit(self) -> None:
        """Xoá bớt bản ghi ĐÃ gửi cũ nhất nếu vượt ngưỡng."""
        cur = self._conn.execute("SELECT COUNT(*) FROM readings")
        total = cur.fetchone()[0]
        if total > self.max_buffer_rows:
            over = total - self.max_buffer_rows
            self._conn.execute(
                "DELETE FROM readings WHERE id IN "
                "(SELECT id FROM readings WHERE sent=1 ORDER BY id ASC LIMIT ?)",
                (over,),
            )
            self._conn.commit()

    def fetch_unsent(self, limit: int) -> List[Tuple]:
        with self._lock:
            cur = self._conn.execute(
                "SELECT id, node_id, gateway_id, ts, metrics, sent "
                "FROM readings WHERE sent=0 ORDER BY id ASC LIMIT ?",
                (limit,),
            )
            return cur.fetchall()

    def mark_sent(self, ids: List[int]) -> None:
        if not ids:
            return
        with self._lock:
            self._conn.executemany(
                "UPDATE readings SET sent=1 WHERE id=?", [(i,) for i in ids]
            )
            self._conn.commit()

    def pending_count(self) -> int:
        with self._lock:
            return self._conn.execute(
                "SELECT COUNT(*) FROM readings WHERE sent=0"
            ).fetchone()[0]

    def close(self) -> None:
        with self._lock:
            self._conn.close()
