"""Đẩy dữ liệu từ bộ đệm cục bộ lên Cloud (HTTP hoặc MQTT).

Chạy trong một luồng riêng, định kỳ gom bản ghi chưa gửi và đẩy đi.
Nếu thất bại (mất mạng...) thì giữ nguyên trong SQLite, thử lại sau.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import List

from .models import Reading
from .storage import Storage

log = logging.getLogger("gateway.forwarder")


class Forwarder:
    def __init__(self, cloud_cfg: dict, storage: Storage) -> None:
        self.cfg = cloud_cfg
        self.storage = storage
        self.mode = cloud_cfg.get("mode", "none")
        self.batch_size = int(cloud_cfg.get("batch_size", 50))
        self.flush_interval = float(cloud_cfg.get("flush_interval_sec", 10))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._backoff = 1.0
        self._mqtt_client = None
        if self.mode == "mqtt":
            self._init_mqtt()

    # ------------------------------------------------------------------
    def _init_mqtt(self) -> None:
        import paho.mqtt.client as mqtt

        c = self.cfg["mqtt"]
        client = mqtt.Client()
        if c.get("username"):
            client.username_pw_set(c["username"], c.get("password", ""))
        if c.get("tls"):
            client.tls_set()
        client.connect_async(c["host"], int(c.get("port", 8883)))
        client.loop_start()
        self._mqtt_client = client
        log.info("Ket noi cloud MQTT toi %s:%s", c["host"], c.get("port", 8883))

    # ------------------------------------------------------------------
    def start(self) -> None:
        if self.mode == "none":
            log.info("Cloud mode = none -> chi luu cuc bo, khong day di")
            return
        self._thread = threading.Thread(target=self._run, name="forwarder", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self._mqtt_client:
            self._mqtt_client.loop_stop()
            self._mqtt_client.disconnect()

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._flush_once()
                self._backoff = 1.0
            except Exception as exc:  # noqa: BLE001 - giữ luồng sống dù có lỗi
                self._backoff = min(self._backoff * 2, 60.0)
                log.error("Day cloud that bai: %s -> thu lai sau %.0fs", exc, self._backoff)
                self._stop.wait(self._backoff)
                continue
            self._stop.wait(self.flush_interval)

    # ------------------------------------------------------------------
    def _flush_once(self) -> None:
        rows = self.storage.fetch_unsent(self.batch_size)
        if not rows:
            return
        readings = [Reading.from_row(r) for r in rows]
        ids = [r[0] for r in rows]

        if self.mode == "http":
            self._send_http(readings)
        elif self.mode == "mqtt":
            self._send_mqtt(readings)
        else:
            return

        self.storage.mark_sent(ids)
        log.info("Da day %d ban ghi len cloud (con lai %d)",
                 len(ids), self.storage.pending_count())

    def _send_http(self, readings: List[Reading]) -> None:
        import requests

        h = self.cfg["http"]
        payload = [json.loads(r.to_json()) for r in readings]
        resp = requests.request(
            method=h.get("method", "POST"),
            url=h["url"],
            headers=h.get("headers", {}),
            json=payload,
            timeout=float(h.get("timeout_sec", 10)),
        )
        if resp.status_code >= 300:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:200]}")

    def _send_mqtt(self, readings: List[Reading]) -> None:
        if self._mqtt_client is None:
            raise RuntimeError("MQTT cloud client chua san sang")
        topic = self.cfg["mqtt"]["publish_topic"]
        for r in readings:
            info = self._mqtt_client.publish(topic, r.to_json(), qos=1)
            info.wait_for_publish(timeout=5)
            if info.rc != 0:
                raise RuntimeError(f"MQTT publish loi rc={info.rc}")
