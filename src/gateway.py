"""Bộ điều phối chính: nối nguồn MQTT -> node manager -> storage -> forwarder."""
from __future__ import annotations

import logging
import threading
import time

from .config import Config
from .forwarder import Forwarder
from .mqtt_source import LocalMqttSource
from .node_manager import NodeManager
from .storage import Storage

log = logging.getLogger("gateway")


class Gateway:
    def __init__(self, config: Config) -> None:
        self.config = config
        self.storage = Storage(
            config.storage["path"],
            int(config.storage.get("max_buffer_rows", 100_000)),
        )
        self.nodes = NodeManager(
            gateway_id=config.gateway_id,
            node_defs=config.enabled_nodes(),
            offline_after=int(config.logging_cfg.get("node_offline_after_sec", 120)),
        )
        self.forwarder = Forwarder(config.cloud, self.storage)
        self.source = LocalMqttSource(config.local_broker, self._on_message)
        self._stop = threading.Event()

    def _on_message(self, node_id: str, payload: bytes) -> None:
        reading = self.nodes.handle_payload(node_id, payload)
        if reading is not None:
            self.storage.save(reading)
            log.debug("Luu reading tu %s: %s", node_id, reading.metrics)

    def run(self) -> None:
        log.info("=== Khoi dong Gateway %s ===", self.config.gateway_id)
        log.info("Theo doi %d node", len(self.config.enabled_nodes()))
        self.forwarder.start()
        self.source.start()
        try:
            while not self._stop.is_set():
                self._stop.wait(30)
                self.nodes.refresh_offline()
                online = sum(1 for s in self.nodes.snapshot() if s["online"])
                log.info(
                    "Nhip: %d/%d node online | %d ban ghi cho day cloud",
                    online, len(self.config.enabled_nodes()),
                    self.storage.pending_count(),
                )
        finally:
            self.shutdown()

    def stop(self) -> None:
        self._stop.set()

    def shutdown(self) -> None:
        log.info("Dang tat gateway...")
        self.source.stop()
        self.forwarder.stop()
        self.storage.close()
        log.info("Da tat gateway.")
