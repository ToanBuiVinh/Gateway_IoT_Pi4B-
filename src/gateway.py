"""Orchestrator asyncio: khởi tạo hạ tầng và chạy tất cả worker song song."""
from __future__ import annotations

import asyncio
import logging

from .cloud_publisher import CloudPublisher
from .config import Config
from .db import Database
from .mqtt_local import LocalMqttClient
from .network_monitor import network_monitor_worker
from .node_manager import NodeManager
from .ratelimit import FloodGuard
from .state import AppState
from .workers import (
    ack_worker,
    command_worker,
    database_worker,
    disk_cleanup_worker,
    ingestion_worker,
    store_and_forward_worker,
)

log = logging.getLogger("gateway")


class Gateway:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.state = AppState()
        self.db = Database(
            config.storage.get("path", "data/gateway.db"),
            int(config.storage.get("max_buffer_rows", 200_000)),
        )
        self.nodes = NodeManager(
            gateway_id=config.gateway_id,
            node_defs=config.enabled_nodes(),
            offline_after=int(config.logging_cfg.get("node_offline_after_sec", 120)),
        )
        # Chống flood: chỉ cấp bucket cho node đã khai báo.
        self.guard = FloodGuard(
            config.security.get("flood_guard", {}),
            known_ids=[n["id"] for n in config.enabled_nodes()],
        )
        # Hàng đợi trên RAM
        qmax = int(config.pipeline.get("ingest_queue_max", 10000))
        self.ingest_queue: asyncio.Queue = asyncio.Queue(maxsize=qmax)
        self.db_queue: asyncio.Queue = asyncio.Queue()
        self.cmd_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)  # lệnh downlink
        self.ack_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)  # phản hồi từ node
        # Được gán trong run() khi đã có event loop
        self.local: LocalMqttClient | None = None
        self.publisher: CloudPublisher | None = None

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        log.info("=== Khoi dong Gateway %s (%d node) ===",
                 self.config.gateway_id, len(self.config.enabled_nodes()))

        # Hai MQTT client (§1). Cloud client kèm cmd_queue để nhận lệnh downlink.
        self.publisher = CloudPublisher(
            self.config.cloud, loop, self.state, command_queue=self.cmd_queue)
        self.local = LocalMqttClient(
            self.config.local_broker, loop, self.ingest_queue,
            ack_queue=self.ack_queue)
        self.publisher.start()
        self.local.start()

        # Các worker chạy song song
        tasks = [
            asyncio.create_task(ingestion_worker(
                self.state, self.ingest_queue, self.db_queue,
                self.publisher, self.nodes, self.guard), name="ingestion"),
            asyncio.create_task(database_worker(
                self.config.pipeline, self.db, self.db_queue, self.state),
                name="database"),
            asyncio.create_task(store_and_forward_worker(
                self.config.store_forward, self.db, self.publisher, self.state),
                name="store-forward"),
            asyncio.create_task(network_monitor_worker(
                self.config.network_monitor, self.config.cloud, self.state),
                name="netmon"),
            asyncio.create_task(command_worker(
                self.cmd_queue, self.local, self.nodes, self.state),
                name="command"),
            asyncio.create_task(ack_worker(
                self.ack_queue, self.publisher, self.nodes,
                self.config.gateway_id, self.state), name="ack"),
            asyncio.create_task(disk_cleanup_worker(
                self.config.maintenance, self.db), name="disk-cleanup"),
            asyncio.create_task(self._heartbeat(), name="heartbeat"),
        ]
        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            log.info("Nhan lenh dung, huy cac worker...")
        finally:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self.shutdown()

    async def _heartbeat(self) -> None:
        """Định kỳ log tình trạng: online, số node, thống kê pipeline."""
        while True:
            await asyncio.sleep(30)
            self.nodes.refresh_offline()
            online = sum(1 for s in self.nodes.snapshot() if s["online"])
            st = self.state.stats
            pending = await asyncio.to_thread(self.db.pending_count)
            log.info(
                "Nhip | cloud=%s | node online=%d/%d | nhan=%d thang=%d buffer=%d "
                "gui_bu=%d loai=%d flood(rl=%d,big=%d) | lenh=%d ack=%d | cho gui=%d",
                "ON" if self.state.is_online else "OFF",
                online, len(self.config.enabled_nodes()),
                st.received, st.published_direct, st.buffered,
                st.forwarded, st.dropped, st.rate_limited, st.oversized,
                st.commands_relayed, st.acks_relayed, pending,
            )

    def shutdown(self) -> None:
        log.info("Dang tat gateway...")
        if self.local:
            self.local.stop()
        if self.publisher:
            self.publisher.stop()
        self.db.close()
        log.info("Da tat gateway.")
