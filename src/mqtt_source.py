"""Nguồn dữ liệu cục bộ: subscribe broker Mosquitto trên Pi.

Node ESP32 publish JSON vào topic <base_topic>/<node_id>.
Mỗi message nhận được sẽ được đưa qua callback do gateway cung cấp.
"""
from __future__ import annotations

import logging
from typing import Callable

import paho.mqtt.client as mqtt

log = logging.getLogger("gateway.mqtt")

# callback(node_id: str, payload: bytes) -> None
OnMessage = Callable[[str, bytes], None]


class LocalMqttSource:
    def __init__(self, broker_cfg: dict, on_message: OnMessage) -> None:
        self.cfg = broker_cfg
        self.base_topic = broker_cfg.get("base_topic", "iot/nodes").rstrip("/")
        self._on_message = on_message
        self._client = mqtt.Client(client_id="pi4b-gateway-local")
        if broker_cfg.get("username"):
            self._client.username_pw_set(
                broker_cfg["username"], broker_cfg.get("password", "")
            )
        self._client.on_connect = self._handle_connect
        self._client.on_message = self._handle_message
        self._client.on_disconnect = self._handle_disconnect

    def start(self) -> None:
        host = self.cfg.get("host", "127.0.0.1")
        port = int(self.cfg.get("port", 1883))
        keepalive = int(self.cfg.get("keepalive", 60))
        log.info("Ket noi broker cuc bo %s:%s", host, port)
        self._client.connect(host, port, keepalive)
        self._client.loop_start()

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    # --- callbacks ---
    def _handle_connect(self, client, userdata, flags, rc):  # noqa: ANN001
        if rc == 0:
            topic = f"{self.base_topic}/+"
            client.subscribe(topic, qos=1)
            log.info("Da subscribe: %s", topic)
        else:
            log.error("Ket noi broker that bai, rc=%s", rc)

    def _handle_disconnect(self, client, userdata, rc):  # noqa: ANN001
        if rc != 0:
            log.warning("Mat ket noi broker (rc=%s), paho se tu ket noi lai", rc)

    def _handle_message(self, client, userdata, msg):  # noqa: ANN001
        # Topic: base_topic/<node_id>
        parts = msg.topic.split("/")
        node_id = parts[-1] if parts else ""
        try:
            self._on_message(node_id, msg.payload)
        except Exception as exc:  # noqa: BLE001
            log.exception("Loi khi xu ly message tu %s: %s", node_id, exc)
