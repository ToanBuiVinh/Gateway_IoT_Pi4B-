"""Cloud MQTT Client: publish telemetry lên cloud broker (TLS), chờ PUBACK.

- Duy trì kết nối bền (paho loop_start tự reconnect).
- Cập nhật cờ ``AppState.online`` qua on_connect/on_disconnect.
- ``publish()`` là coroutine: gửi QoS1 và chờ PUBACK bằng ``asyncio.to_thread``
  để không chặn event loop; trả về True nếu cloud đã xác nhận.
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
from typing import Any, Dict

import paho.mqtt.client as mqtt

from .state import AppState

log = logging.getLogger("gateway.cloud")


class CloudPublisher:
    def __init__(self, cfg: Dict[str, Any], loop: asyncio.AbstractEventLoop,
                 state: AppState,
                 command_queue: "asyncio.Queue | None" = None) -> None:
        self.cfg = cfg
        self._loop = loop
        self._state = state
        self._command_queue = command_queue
        self.enabled = bool(cfg.get("enabled", False))
        self.topic = cfg.get("publish_topic", "telemetry")
        self.qos = int(cfg.get("qos", 1))
        self.puback_timeout = float(cfg.get("puback_timeout_sec", 10))
        # Downlink: subscribe lệnh từ cloud (điều khiển 2 chiều)
        self.command_topic = cfg.get("command_topic", "")
        self.command_qos = int(cfg.get("command_qos", 1))
        # Command/ack: topic để relay phản hồi từ node lên cloud
        self.ack_topic = cfg.get("ack_topic", "").rstrip("/")

        self._client = mqtt.Client(client_id="pi4b-gateway-cloud")
        if cfg.get("username"):
            self._client.username_pw_set(cfg["username"], cfg.get("password", ""))
        if cfg.get("tls"):
            ca = cfg.get("ca_cert") or None
            self._client.tls_set(ca_certs=ca, cert_reqs=ssl.CERT_REQUIRED)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    # ------------------------------------------------------------------
    def start(self) -> None:
        if not self.enabled:
            log.warning("Cloud DISABLED -> moi du lieu se buffer vao SQLite")
            return
        host = self.cfg["host"]
        port = int(self.cfg.get("port", 8883))
        keepalive = int(self.cfg.get("keepalive", 30))
        log.info("Ket noi cloud broker %s:%s (tls=%s)", host, port, self.cfg.get("tls"))
        self._client.connect_async(host, port, keepalive)
        self._client.loop_start()

    def stop(self) -> None:
        if not self.enabled:
            return
        self._client.loop_stop()
        self._client.disconnect()

    @property
    def connected(self) -> bool:
        return self.enabled and self._state.is_online

    # ------------------------------------------------------------------
    async def publish(self, payload: Dict[str, Any]) -> bool:
        """Publish 1 bản ghi telemetry, chờ PUBACK. True nếu thành công."""
        return await self._publish_wait(self.topic, payload)

    async def publish_ack(self, node_id: str, payload: Dict[str, Any]) -> bool:
        """Relay phản hồi (ack) của node lên cloud tại <ack_topic>/<node_id>."""
        if not self.ack_topic:
            return False
        return await self._publish_wait(f"{self.ack_topic}/{node_id}", payload)

    async def _publish_wait(self, topic: str, payload: Dict[str, Any]) -> bool:
        """Publish QoS1 tới topic bất kỳ và chờ PUBACK (không chặn event loop)."""
        if not self.connected:
            return False
        data = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        try:
            info = self._client.publish(topic, data, qos=self.qos)
            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                log.warning("publish %s tra rc=%s", topic, info.rc)
                return False
            await asyncio.wait_for(
                asyncio.to_thread(info.wait_for_publish, self.puback_timeout),
                timeout=self.puback_timeout + 1,
            )
            return info.is_published()
        except (asyncio.TimeoutError, ValueError, RuntimeError) as exc:
            log.warning("Cho PUBACK (%s) that bai: %s", topic, exc)
            return False

    # --- callbacks (thread paho) -> bắc cầu vào event loop ---
    def _on_connect(self, client, userdata, flags, rc):  # noqa: ANN001
        if rc == 0:
            self._loop.call_soon_threadsafe(self._state.set_online)
            # (Re)subscribe topic lệnh downlink sau mỗi lần kết nối lại.
            if self._command_queue is not None and self.command_topic:
                sub = f"{self.command_topic.rstrip('/')}/+"
                client.subscribe(sub, qos=self.command_qos)
                log.info("Subscribe lenh downlink: %s", sub)
        else:
            log.error("Cloud connect that bai rc=%s", rc)
            self._loop.call_soon_threadsafe(self._state.set_offline)

    def _on_disconnect(self, client, userdata, rc):  # noqa: ANN001
        self._loop.call_soon_threadsafe(self._state.set_offline)
        if rc != 0:
            log.warning("Mat ket noi cloud (rc=%s), paho se reconnect", rc)

    def _on_message(self, client, userdata, msg):  # noqa: ANN001
        """Nhận lệnh từ cloud -> đẩy vào cmd_queue (bắc cầu vào event loop)."""
        if self._command_queue is None:
            return
        node_id = msg.topic.split("/")[-1]
        item = (node_id, msg.payload)
        self._loop.call_soon_threadsafe(self._enqueue_command, item)

    def _enqueue_command(self, item) -> None:  # noqa: ANN001
        try:
            self._command_queue.put_nowait(item)
        except asyncio.QueueFull:
            log.error("Command queue DAY -> bo lenh cho %s", item[0])
