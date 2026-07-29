"""Kiểm thử pipeline asyncio với publisher giả (KHÔNG cần MQTT broker).

Chạy:  python scripts/test_pipeline.py
Xác minh 4 kịch bản khớp đặc tả kỹ thuật:
  1) OFFLINE            -> mọi tin buffer vào SQLite (status=0)
  2) ONLINE trở lại     -> store-and-forward đẩy bù, payload có cờ buffered=true
  3) ONLINE trực tiếp   -> publish thẳng, KHÔNG buffer
  4) node lạ / JSON hỏng -> bị loại
"""
from __future__ import annotations

import asyncio
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config          # noqa: E402
from src.db import Database            # noqa: E402
from src.node_manager import NodeManager  # noqa: E402
from src.state import AppState         # noqa: E402
from src.workers import (              # noqa: E402
    database_worker,
    ingestion_worker,
    store_and_forward_worker,
)


class FakePublisher:
    """Giả lập Cloud MQTT Client: gom payload đã gửi để kiểm chứng."""

    def __init__(self, state: AppState) -> None:
        self.state = state
        self.sent: list[dict] = []
        self.fail = False

    @property
    def connected(self) -> bool:
        return self.state.is_online

    async def publish(self, payload: dict) -> bool:
        if self.fail or not self.state.is_online:
            return False
        self.sent.append(payload)
        return True


async def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    cfg = Config(os.path.join(root, "config/gateway.yaml"),
                 os.path.join(root, "config/nodes.yaml"))
    db_path = tempfile.mktemp(suffix=".db")
    db = Database(db_path)
    state = AppState()
    nodes = NodeManager(cfg.gateway_id, cfg.enabled_nodes())
    pub = FakePublisher(state)

    ingest_q: asyncio.Queue = asyncio.Queue(maxsize=1000)
    db_q: asyncio.Queue = asyncio.Queue()
    tasks = [
        asyncio.create_task(ingestion_worker(state, ingest_q, db_q, pub, nodes)),
        asyncio.create_task(database_worker(cfg.pipeline, db, db_q, state)),
        asyncio.create_task(store_and_forward_worker(cfg.store_forward, db, pub, state)),
    ]

    try:
        # 1) OFFLINE
        print("== OFFLINE: du lieu phai vao buffer ==")
        state.set_offline()
        for i in range(12):
            ingest_q.put_nowait(("node-01", b'{"temperature":25.0,"humidity":60}', 1000.0 + i))
        await asyncio.sleep(4)
        assert state.stats.received == 12
        assert db.pending_count() == 12
        assert state.stats.published_direct == 0
        print(f"   OK: buffer={db.pending_count()}")

        # 2) ONLINE -> store-and-forward
        print("== ONLINE: store-and-forward day bu ==")
        state.set_online()
        await asyncio.sleep(3)
        assert db.pending_count() == 0
        assert state.stats.forwarded == 12
        assert all(p.get("buffered") is True for p in pub.sent)
        print(f"   OK: gui_bu={state.stats.forwarded}, tat ca co buffered=true")

        # 3) ONLINE truc tiep
        print("== ONLINE: publish thang ==")
        ingest_q.put_nowait(("node-10", b'{"pressure":1013,"temperature":28}', 2000.0))
        await asyncio.sleep(1)
        assert state.stats.published_direct == 1
        assert db.pending_count() == 0
        assert pub.sent[-1].get("buffered") is None
        print("   OK: gui thang, khong buffer, khong co buffered")

        # 4) du lieu loi
        print("== Du lieu loi: bi loai ==")
        ingest_q.put_nowait(("node-99", b'{"x":1}', 3000.0))
        ingest_q.put_nowait(("node-01", b'not-json', 3001.0))
        await asyncio.sleep(1)
        assert state.stats.dropped == 2
        print("   OK: loai 2 tin loi")

        print("\n=> TAT CA KICH BAN PASS.")
        return 0
    finally:
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        db.close()
        if os.path.exists(db_path):
            os.remove(db_path)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
