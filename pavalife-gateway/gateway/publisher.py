"""Publisher MQTT 5.0 over WSS (WebSocket Secure) theo contract Bang 0.

Topic: pvl/v2/gw/{gateway_id}/up/{message_type}  (rule #10: KHONG co patient_id).
Import paho tre -> chi can khi publish that.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict
from urllib.parse import urlparse

from . import registry as reg

log = logging.getLogger("pvl.mqtt")


class PavaLifePublisher:
    def __init__(self, broker_url: str = reg.BROKER_URL, *, username: str = "",
                 password: str = "", client_id: str = None) -> None:
        import paho.mqtt.client as mqtt

        u = urlparse(broker_url)   # wss://host:443/mqtt
        self._host = u.hostname
        self._port = u.port or (443 if u.scheme == "wss" else 8083)
        self._path = u.path or "/mqtt"
        self._tls = (u.scheme == "wss")

        self._client = mqtt.Client(
            client_id=client_id or f"{reg.GATEWAY_ID}-pub",
            protocol=mqtt.MQTTv5, transport="websockets",
        )
        self._client.ws_set_options(path=self._path)
        if self._tls:
            self._client.tls_set()   # dung CA he thong; them ca_certs/cert neu mTLS
        if username:
            self._client.username_pw_set(username, password)

    def connect(self) -> None:
        log.info("Ket noi broker wss://%s:%s%s (MQTT 5.0)", self._host, self._port, self._path)
        self._client.connect(self._host, self._port, keepalive=30)
        self._client.loop_start()

    def publish(self, msg: Dict[str, Any], qos: int = 1) -> bool:
        topic = reg.topic_for(msg["message_type"])
        assert "patient" not in topic.lower(), "rule #10: patient_id khong duoc vao topic"
        info = self._client.publish(topic, json.dumps(msg, ensure_ascii=False), qos=qos)
        info.wait_for_publish(timeout=10)
        ok = info.is_published()
        log.info("publish %s -> %s %s", msg["message_id"], topic, "OK" if ok else "FAIL")
        return ok

    def disconnect(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()
