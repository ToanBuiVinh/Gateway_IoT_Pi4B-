"""pvl_subscribe.py — lang nghe ban tin PavaLife tren broker (de test cuc bo).

Mac dinh nghe broker cuc bo:
    python tools/pvl_subscribe.py
Hoac chi dinh broker:
    python tools/pvl_subscribe.py --broker mqtt://localhost:1883
In ra topic + JSON moi ban tin nhan duoc. Ctrl+C de dung.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paho.mqtt.client as mqtt   # noqa: E402

TOPIC = "pvl/v2/gw/+/up/#"
_DEFAULT_PORT = {"wss": 443, "ws": 9001, "mqtts": 8883, "mqtt": 1883, "tcp": 1883}


def _parse(url):
    if "://" not in url:
        url = "mqtt://" + url
    u = urlparse(url)
    ws = u.scheme in ("ws", "wss")
    tls = u.scheme in ("wss", "mqtts")
    return (u.hostname or "localhost"), (u.port or _DEFAULT_PORT.get(u.scheme, 1883)), (u.path or "/mqtt"), ws, tls


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", default="mqtt://localhost:1883")
    ap.add_argument("--topic", default=TOPIC)
    ap.add_argument("--mqtt-version", choices=["5", "311"], default="311",
                    help="mac dinh 311 (hop mini_broker va Mosquitto)")
    args = ap.parse_args()
    host, port, path, ws, tls = _parse(args.broker)

    proto = mqtt.MQTTv311 if args.mqtt_version == "311" else mqtt.MQTTv5
    # Tuong thich paho-mqtt 1.x va 2.x.
    if hasattr(mqtt, "CallbackAPIVersion"):
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="pvl-subscriber",
                        protocol=proto, transport="websockets" if ws else "tcp")
    else:
        c = mqtt.Client(client_id="pvl-subscriber", protocol=proto,
                        transport="websockets" if ws else "tcp")
    if ws:
        c.ws_set_options(path=path)
    if tls:
        c.tls_set()

    def on_connect(cl, u, f, rc, props=None):
        print(f"Da ket noi {args.broker} — subscribe '{args.topic}'")
        cl.subscribe(args.topic, qos=1)

    def on_message(cl, u, msg):
        try:
            data = json.loads(msg.payload.decode("utf-8"))
            mt = data.get("message_type", "?")
            seq = data.get("sequence_no", "?")
            print(f"\n===== {msg.topic}  (seq {seq}, {mt}) =====")
            print(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception:
            print(f"{msg.topic}: {msg.payload[:200]!r}")

    c.on_connect = on_connect
    c.on_message = on_message
    c.connect(host, port, keepalive=30)
    print("Dang nghe... (Ctrl+C de dung)")
    try:
        c.loop_forever()
    except KeyboardInterrupt:
        print("\nDung.")


if __name__ == "__main__":
    main()
