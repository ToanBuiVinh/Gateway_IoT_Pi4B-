"""Local MQTT Client: subscribe Mosquitto trên Pi, đẩy tin vào asyncio.Queue.

paho chạy callback trong thread mạng riêng của nó. Ta bắc cầu sang asyncio
bằng ``loop.call_soon_threadsafe`` để đưa dữ liệu vào Queue một cách an toàn.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict

import paho.mqtt.client as mqtt

log = logging.getLogger("gateway.local")

# Phần tử trong queue: (node_id, payload_bytes, recv_ts)
IngestItem = tuple


class LocalMqttClient:
    def __init__(self, cfg: Dict[str, Any], loop: asyncio.AbstractEventLoop,
                 queue: "asyncio.Queue[IngestItem]") -> None:
        self.cfg = cfg
        self._loop = loop
        self._queue = queue
        self.base_topic = cfg.get("base_topic", "iot/nodes").rstrip("/")
        self._client = mqtt.Client(client_id="pi4b-gateway-local")
        if cfg.get("username"):
            self._client.username_pw_set(cfg["username"], cfg.get("password", ""))
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.on_disconnect = self._on_disconnect

    def start(self) -> None:
        host = self.cfg.get("host", "127.0.0.1")
        port = int(self.cfg.get("port", 1883))
        keepalive = int(self.cfg.get("keepalive", 60))
        log.info("Ket noi local broker %s:%s", host, port)
        self._client.connect_async(host, port, keepalive)
        self._client.loop_start()   # paho tự quản lý & tự reconnect

    def stop(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()

    # --- callbacks (chạy trong thread paho) ---
    def _on_connect(self, client, userdata, flags, rc):  # noqa: ANN001
        if rc == 0:
            topic = f"{self.base_topic}/+"
            client.subscribe(topic, qos=1)
            log.info("Da subscribe local: %s", topic)
        else:
            log.error("Local broker connect that bai rc=%s", rc)

    def _on_disconnect(self, client, userdata, rc):  # noqa: ANN001
        if rc != 0:
            log.warning("Mat ket noi local broker (rc=%s), paho se reconnect", rc)

    def _on_message(self, client, userdata, msg):  # noqa: ANN001
        node_id = msg.topic.split("/")[-1]
        item = (node_id, msg.payload, time.time())
        # Bắc cầu an toàn sang event loop asyncio.
        self._loop.call_soon_threadsafe(self._enqueue, item)

    def _enqueue(self, item: IngestItem) -> None:
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            log.error("Ingest queue DAY -> bo tin tu %s", item[0])
