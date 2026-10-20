"""Publisher MQTT over TLS — topic, QoS/retain, LWT theo Data Contract Muc 1.

Topic:  med/{clinic_id}/{gateway_id}/{message_type}/{device_id}
Luu y:  patient_id KHONG nam trong topic (chi trong payload, duoc TLS bao ve).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict

from . import devices as reg

log = logging.getLogger("medgw.mqtt")

# QoS / retain theo Muc 1.2
QOS_RETAIN = {
    "observation.vitals": (1, False),
    "observation.lab": (1, False),
    "observation.waveform": (1, False),
    "imaging.study": (1, False),
    "media.audio": (1, False),
    "media.video": (1, False),
    "alert.clinical": (1, False),
    "device.status": (1, True),
    "ack": (1, False),
}


def build_topic(message_type: str, device_id: str,
                clinic_id: str = reg.CLINIC_ID,
                gateway_id: str = reg.GATEWAY_ID) -> str:
    return f"med/{clinic_id}/{gateway_id}/{message_type}/{device_id}"


def lwt() -> Dict[str, Any]:
    """Last Will cua Gateway (retain=true) — Muc 1.2."""
    return {
        "topic": build_topic("device.status", "gateway"),
        "payload": json.dumps({
            "schema_version": "2.0", "message_type": "device.status",
            "device": {"device_id": "gateway"}, "status": "offline",
        }, ensure_ascii=False),
        "qos": 1, "retain": True,
    }


class MedicalPublisher:
    """Bo publish payload canonical len cloud broker (TLS 1.3)."""

    def __init__(self, host: str, port: int = 8883, *, username: str = "",
                 password: str = "", ca_cert: str = None,
                 client_cert: str = None, client_key: str = None) -> None:
        import paho.mqtt.client as mqtt  # import tre: chi can khi chay that

        self._client = mqtt.Client(client_id=f"{reg.GATEWAY_ID}-pub")
        if username:
            self._client.username_pw_set(username, password)
        self._client.tls_set(ca_certs=ca_cert, certfile=client_cert, keyfile=client_key)
        self._client.tls_insecure_set(False)
        w = lwt()
        self._client.will_set(w["topic"], w["payload"], qos=w["qos"], retain=w["retain"])
        self._host, self._port = host, port

    def connect(self) -> None:
        self._client.connect(self._host, self._port, keepalive=30)
        self._client.loop_start()

    def publish(self, payload: Dict[str, Any]) -> bool:
        mtype = payload["message_type"]
        device_id = payload["device"]["device_id"]
        qos, retain = QOS_RETAIN.get(mtype, (1, False))
        topic = build_topic(mtype, device_id)
        info = self._client.publish(topic, json.dumps(payload, ensure_ascii=False),
                                    qos=qos, retain=retain)
        info.wait_for_publish(timeout=10)
        ok = info.is_published()
        log.info("publish %s -> %s (qos=%d retain=%s) %s",
                 payload["message_id"], topic, qos, retain, "OK" if ok else "FAIL")
        return ok

    def disconnect(self) -> None:
        self._client.loop_stop()
        self._client.disconnect()
