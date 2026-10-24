"""pvl_send.py — cong cu gui ban tin PavaLife v2.1 (theo Data Contract).

Vi du (in JSON ra man hinh):
    python pvl_send.py vitals --devices blood_pressure,spo2
    python pvl_send.py lab    --devices lab_analyzer,glucose
    python pvl_send.py status

Gui that len broker MQTT 5.0/WSS (can thong tin dang nhap):
    python pvl_send.py vitals --devices spo2 --publish \
        --username <u> --password <p>
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gateway import contract as C      # noqa: E402
from gateway import registry as reg    # noqa: E402
from gateway import validator          # noqa: E402

# Gia tri demo khi khong co phan cung
DEMO = {
    "blood_pressure": {"systolic": 120, "diastolic": 80, "mean": 93, "pulse_rate": 78},
    "spo2": {"spo2": 98, "heart_rate": 76},
    "thermometer": {"temperature": 36.8},
    "scale": {"body_weight": 64.3},
    "lab_analyzer": {"uric_acid": 360},
    "glucose": {"blood_glucose": 5.6},
}
VITALS_KEYS = ["blood_pressure", "spo2", "thermometer", "scale"]
LAB_KEYS = ["lab_analyzer", "glucose"]


def now_iso() -> str:
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=7))).isoformat(timespec="milliseconds")


def build(kind: str, devices: list[str]) -> list[dict]:
    et = now_iso()
    msgs = []
    if kind == "status":
        return [C.build_device_status(et)]
    if kind == "imaging":
        return [C.build_imaging_study("ultrasound", et)]
    if kind == "audio":
        return [C.build_audio_recording("stethoscope", et)]
    if kind == "all":
        msgs.append(C.build_device_status(et))
        for k in VITALS_KEYS:
            msgs.append(C.build_vitals(k, DEMO[k], et))
        for k in LAB_KEYS:
            msgs.append(C.build_lab(k, DEMO[k], et))
        msgs.append(C.build_imaging_study("ultrasound", et))
        msgs.append(C.build_audio_recording("stethoscope", et))
        return msgs
    for key in devices:
        if key not in reg.DEVICES:
            print(f"[bo qua] khong co thiet bi '{key}'", file=sys.stderr)
            continue
        if kind == "vitals":
            msgs.append(C.build_vitals(key, DEMO[key], et))
        else:
            msgs.append(C.build_lab(key, DEMO[key], et))
    return msgs


def main() -> int:
    ap = argparse.ArgumentParser(description="PavaLife v2.1 message sender")
    ap.add_argument("kind", choices=["vitals", "lab", "imaging", "audio", "status", "all"])
    ap.add_argument("--devices", default="", help="danh sach key, vd: blood_pressure,spo2")
    ap.add_argument("--publish", action="store_true", help="gui that len broker")
    ap.add_argument("--broker", default=reg.BROKER_URL, help="URL broker (mqtt/mqtts/ws/wss)")
    ap.add_argument("--local", action="store_true", help="tat: gui len broker cuc bo mqtt://localhost:1883")
    ap.add_argument("--mqtt-version", choices=["5", "311"], default=None,
                    help="mac dinh 5; --local tu dung 311 (hop mini_broker / Mosquitto)")
    ap.add_argument("--username", default="")
    ap.add_argument("--password", default="")
    ap.add_argument("--ca-cert", default=None, help="CA chung chi broker (neu CA noi bo)")
    ap.add_argument("--insecure", action="store_true", help="bo qua xac minh TLS (CHI de thu nghiem)")
    args = ap.parse_args()
    if args.local:
        args.broker = "mqtt://localhost:1883"
    mqtt_version = args.mqtt_version or ("311" if args.local else "5")

    if args.kind == "vitals":
        devices = args.devices.split(",") if args.devices else VITALS_KEYS
    elif args.kind == "lab":
        devices = args.devices.split(",") if args.devices else LAB_KEYS
    else:
        devices = []
    devices = [d.strip() for d in devices if d.strip()]

    msgs = build(args.kind, devices)
    # Validate truoc khi gui (contract yeu cau pass schema)
    for m in msgs:
        errs = validator.validate(m)
        if errs:
            print(f"[LOI schema] {m['message_type']}: {errs}", file=sys.stderr)
            return 1

    if args.publish:
        from gateway.publisher import PavaLifePublisher
        pub = PavaLifePublisher(args.broker, username=args.username, password=args.password,
                                ca_cert=args.ca_cert, insecure=args.insecure,
                                mqtt_version=mqtt_version)
        pub.connect()
        for m in msgs:
            pub.publish(m)
        pub.disconnect()
        print(f"Da gui {len(msgs)} ban tin len {args.broker}")
    else:
        for m in msgs:
            print(json.dumps(m, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
