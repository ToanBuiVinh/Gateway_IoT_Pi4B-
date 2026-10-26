"""Publisher PavaLife — ho tro nhieu loai broker (de test cuc bo).

broker_url chap nhan:
  mqtt://localhost:1883     (TCP thuong - test cuc bo)
  mqtts://host:8883         (TCP + TLS)
  ws://localhost:9001/mqtt  (WebSocket)
  wss://host:443/mqtt       (WebSocket + TLS - production PavaLife)

Topic: pvl/v2/gw/{gateway_id}/up/{message_type}  (rule #10: KHONG co patient_id).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, Tuple
from urllib.parse import urlparse

from . import registry as reg

log = logging.getLogger("pvl.mqtt")

_DEFAULT_PORT = {"wss": 443, "ws": 9001, "mqtts": 8883, "mqtt": 1883, "tcp": 1883}


def _parse(url: str) -> Tuple[str, int, str, bool, bool]:
    if "://" not in url:
        url = "mqtt://" + url
    u = urlparse(url)
    scheme = u.scheme or "mqtt"
    ws = scheme in ("ws", "wss")
    tls = scheme in ("wss", "mqtts")
    port = u.port or _DEFAULT_PORT.get(scheme, 1883)
    return (u.hostname or "localhost"), port, (u.path or "/mqtt"), ws, tls


class PavaLifePublisher:
    def __init__(self, broker_url: str = reg.BROKER_URL, *, username: str = "",
                 password: str = "", client_id: str = None,
                 ca_cert: str = None, insecure: bool = False,
                 mqtt_version: str = "5") -> None:
        import paho.mqtt.client as mqtt

        # Nhanh PavaLife: dung thong tin dang nhap mac dinh trong registry
        # khi caller khong truyen username/password.
        if not username:
            username = getattr(reg, "BROKER_USERNAME", "")
            password = password or getattr(reg, "BROKER_PASSWORD", "")

        self._host, self._port, self._path, self._ws, self._tls = _parse(broker_url)
        transport = "websockets" if self._ws else "tcp"
        proto = mqtt.MQTTv311 if str(mqtt_version) in ("311", "3.1.1", "v311") else mqtt.MQTTv5
        cid = client_id or f"{reg.GATEWAY_ID}-pub"
        # Tuong thich paho-mqtt 1.x va 2.x: 2.x bat buoc callback_api_version.
        if hasattr(mqtt, "CallbackAPIVersion"):
            self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2,
                                       client_id=cid, protocol=proto, transport=transport)
        else:
            self._client = mqtt.Client(client_id=cid, protocol=proto, transport=transport)
        if self._ws:
            self._client.ws_set_options(path=self._path)
        if self._tls:
            self._client.tls_set(ca_certs=ca_cert)
            if insecure:
                self._client.tls_insecure_set(True)
        if username:
            self._client.username_pw_set(username, password)

    def connect(self) -> None:
        log.info("Ket noi broker %s://%s:%s (MQTT 5.0, transport=%s)",
                 "wss" if (self._ws and self._tls) else ("ws" if self._ws else ("mqtts" if self._tls else "mqtt")),
                 self._host, self._port, "websockets" if self._ws else "tcp")
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
