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
                 queue: "asyncio.Queue[IngestItem]",
                 ack_queue: "asyncio.Queue | None" = None) -> None:
        self.cfg = cfg
        self._loop = loop
        self._queue = queue
        self._ack_queue = ack_queue
        self.base_topic = cfg.get("base_topic", "iot/nodes").rstrip("/")
        self.command_topic = cfg.get("command_topic", "iot/cmd").rstrip("/")
        self.command_qos = int(cfg.get("command_qos", 1))
        self.ack_topic = cfg.get("ack_topic", "iot/ack").rstrip("/")
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

    def publish_command(self, node_id: str, payload: bytes) -> bool:
        """Relay lệnh downlink xuống node qua <command_topic>/<node_id>."""
        topic = f"{self.command_topic}/{node_id}"
        info = self._client.publish(topic, payload, qos=self.command_qos)
        ok = info.rc == mqtt.MQTT_ERR_SUCCESS
        if not ok:
            log.warning("Publish lenh xuong %s that bai rc=%s", node_id, info.rc)
        return ok

    # --- callbacks (chạy trong thread paho) ---
    def _on_connect(self, client, userdata, flags, rc):  # noqa: ANN001
        if rc == 0:
            client.subscribe(f"{self.base_topic}/+", qos=1)     # uplink telemetry
            log.info("Da subscribe local telemetry: %s/+", self.base_topic)
            if self._ack_queue is not None:
                client.subscribe(f"{self.ack_topic}/+", qos=1)  # ack từ node
                log.info("Da subscribe local ack: %s/+", self.ack_topic)
        else:
            log.error("Local broker connect that bai rc=%s", rc)

    def _on_disconnect(self, client, userdata, rc):  # noqa: ANN001
        if rc != 0:
            log.warning("Mat ket noi local broker (rc=%s), paho se reconnect", rc)

    def _on_message(self, client, userdata, msg):  # noqa: ANN001
        node_id = msg.topic.split("/")[-1]
        # Phân loại theo tiền tố topic: ack hay telemetry.
        if self._ack_queue is not None and msg.topic.startswith(self.ack_topic + "/"):
            self._loop.call_soon_threadsafe(self._enqueue_ack, (node_id, msg.payload))
        else:
            item = (node_id, msg.payload, time.time())
            self._loop.call_soon_threadsafe(self._enqueue, item)

    def _enqueue(self, item: IngestItem) -> None:
        try:
            self._queue.put_nowait(item)
        except asyncio.QueueFull:
            log.error("Ingest queue DAY -> bo tin tu %s", item[0])

    def _enqueue_ack(self, item) -> None:  # noqa: ANN001
        try:
            self._ack_queue.put_nowait(item)
        except asyncio.QueueFull:
            log.error("Ack queue DAY -> bo ack tu %s", item[0])
