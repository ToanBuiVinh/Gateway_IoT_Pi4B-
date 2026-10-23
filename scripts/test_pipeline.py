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
from src.ratelimit import FloodGuard   # noqa: E402
from src.state import AppState         # noqa: E402
from src.workers import (              # noqa: E402
    ack_worker,
    command_worker,
    database_worker,
    ingestion_worker,
    store_and_forward_worker,
)


class FakePublisher:
    """Giả lập Cloud MQTT Client: gom payload đã gửi để kiểm chứng."""

    def __init__(self, state: AppState) -> None:
        self.state = state
        self.sent: list[dict] = []
        self.acks: list[tuple] = []
        self.fail = False

    @property
    def connected(self) -> bool:
        return self.state.is_online

    async def publish(self, payload: dict) -> bool:
        if self.fail or not self.state.is_online:
            return False
        self.sent.append(payload)
        return True

    async def publish_ack(self, node_id: str, payload: dict) -> bool:
        if self.fail or not self.state.is_online:
            return False
        self.acks.append((node_id, payload))
        return True


class FakeLocalClient:
    """Giả lập Local MQTT Client: ghi lại lệnh downlink đã relay xuống node."""

    def __init__(self) -> None:
        self.commands: list[tuple] = []

    def publish_command(self, node_id: str, payload: bytes) -> bool:
        self.commands.append((node_id, payload))
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

    local = FakeLocalClient()
    known = [n["id"] for n in cfg.enabled_nodes()]
    # Guard cho pipeline: tốc độ rộng rãi (không cản kịch bản 1-6), chặn payload > 2KB.
    guard = FloodGuard(
        {"enabled": True, "max_msgs_per_sec": 1000, "burst": 1000,
         "max_payload_bytes": 2048}, known_ids=known)
    ingest_q: asyncio.Queue = asyncio.Queue(maxsize=1000)
    db_q: asyncio.Queue = asyncio.Queue()
    cmd_q: asyncio.Queue = asyncio.Queue(maxsize=1000)
    ack_q: asyncio.Queue = asyncio.Queue(maxsize=1000)
    tasks = [
        asyncio.create_task(ingestion_worker(state, ingest_q, db_q, pub, nodes, guard)),
        asyncio.create_task(database_worker(cfg.pipeline, db, db_q, state)),
        asyncio.create_task(store_and_forward_worker(cfg.store_forward, db, pub, state)),
        asyncio.create_task(command_worker(cmd_q, local, nodes, state)),
        asyncio.create_task(ack_worker(ack_q, pub, nodes, cfg.gateway_id, state)),
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

        # 5) dieu khien 2 chieu: relay lenh downlink xuong node
        print("== Downlink: relay lenh xuong node ==")
        cmd_q.put_nowait(("node-06", b'{"cmd":"relay","state":1}'))  # hop le
        cmd_q.put_nowait(("node-99", b'{"cmd":"relay"}'))            # node la -> loai
        cmd_q.put_nowait(("node-06", b'not-json'))                   # hong  -> loai
        await asyncio.sleep(1)
        assert state.stats.commands_relayed == 1, "phai relay 1 lenh hop le"
        assert state.stats.commands_dropped == 2, "phai loai 2 lenh xau"
        assert local.commands[0][0] == "node-06"
        print(f"   OK: relay={state.stats.commands_relayed}, loai={state.stats.commands_dropped}")

        # 6) command/ack: node phan hoi -> relay len cloud (state dang ONLINE)
        print("== Command/ack: relay phan hoi len cloud ==")
        ack_q.put_nowait(("node-06", b'{"cmd_id":"abc123","status":"ok"}'))  # hop le
        ack_q.put_nowait(("node-99", b'{"cmd_id":"x","status":"ok"}'))       # node la
        ack_q.put_nowait(("node-06", b'not-json'))                           # hong
        await asyncio.sleep(1)
        assert state.stats.acks_relayed == 1, "phai relay 1 ack hop le"
        assert state.stats.acks_dropped == 2, "phai loai 2 ack xau"
        node_id, ack_payload = pub.acks[0]
        assert node_id == "node-06" and ack_payload["cmd_id"] == "abc123"
        assert ack_payload["gateway_id"] == cfg.gateway_id, "ack phai co gateway_id"
        print(f"   OK: ack_relay={state.stats.acks_relayed}, loai={state.stats.acks_dropped}")

        # 7a) chong flood: payload qua lon -> bi loai (qua pipeline, tat dinh)
        print("== Flood guard: payload qua lon ==")
        big = b'{"temperature":25,"x":"' + b'A' * 3000 + b'"}'  # > 2048 bytes
        ingest_q.put_nowait(("node-01", big, 5000.0))
        await asyncio.sleep(0.5)
        assert state.stats.oversized == 1, "payload lon phai bi loai"
        print(f"   OK: oversized={state.stats.oversized}")

        # 7b) chong flood: token-bucket theo toc do (tat dinh voi dong ho gia)
        print("== Flood guard: rate-limit (token-bucket) ==")
        g = FloodGuard({"enabled": True, "max_msgs_per_sec": 1, "burst": 2},
                       known_ids=["node-01"])
        p = b'{"temperature":25}'
        assert g.check("node-01", p, now=100.0)[0] is True    # token 1
        assert g.check("node-01", p, now=100.0)[0] is True    # token 2 (burst)
        assert g.check("node-01", p, now=100.0)[0] is False   # het token -> chan
        assert g.check("node-01", p, now=102.0)[0] is True    # +2s -> nap lai token
        # Node la khong cap phat bucket (chong phinh bo nho)
        assert g.check("node-77", p, now=100.0) == (True, None)
        print("   OK: burst=2 cho qua 2, chan tin thu 3, nap lai sau 2s")

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
