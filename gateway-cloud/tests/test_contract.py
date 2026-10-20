"""Kiem thu hop dong du lieu: validate 10 payload MQTT + smoke-test mapper FHIR.

Chay:  python tests/test_contract.py
Khong can broker/HAPI; chi can jsonschema.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gateway import devices as reg          # noqa: E402
from gateway import mapper_fhir             # noqa: E402
from gateway import validator               # noqa: E402
from gateway.publisher_mqtt import build_topic, QOS_RETAIN  # noqa: E402

MQTT_DIR = os.path.join(ROOT, "samples", "mqtt")

_BASE = {"Patient", "Encounter", "Device", "Provenance"}


def expected_resources(payload: dict) -> set:
    """Resource ky vong theo message_type + co panel (DiagnosticReport) hay khong."""
    mtype = payload["message_type"]
    dev = reg.DEVICES[payload["device"]["device_id"]]
    exp = set(_BASE)
    if mtype in ("observation.vitals", "observation.lab", "observation.waveform"):
        exp.add("Observation")
    if mtype == "imaging.study":
        exp.add("ImagingStudy")
    if mtype in ("media.audio", "media.video"):
        exp.add("Media")
    # DiagnosticReport chi khi thiet bi co cau hinh panel/report (LAB-05, ECG-03, ECH-06).
    if dev.get("report"):
        exp.add("DiagnosticReport")
    return exp


def main() -> int:
    files = sorted(f for f in os.listdir(MQTT_DIR) if f.endswith(".json"))
    assert len(files) == 10, f"Phai co du 10 payload, co {len(files)}"
    fails = 0

    for fn in files:
        with open(os.path.join(MQTT_DIR, fn), "r", encoding="utf-8") as f:
            payload = json.load(f)
        name = fn.replace(".json", "")

        # 1) Schema + range + UCUM
        errs = validator.validate(payload)
        if errs:
            fails += 1
            print(f"  [FAIL] {name}: {errs}")
            continue

        # 2) Topic + QoS khop bang
        mtype = payload["message_type"]
        topic = build_topic(mtype, payload["device"]["device_id"])
        assert "BN-2026-000123" not in topic, "patient_id KHONG duoc nam trong topic!"
        assert mtype in QOS_RETAIN, f"thieu QoS cho {mtype}"

        # 3) Mapper -> Bundle transaction, du loai resource ky vong
        bundle = mapper_fhir.to_bundle(payload)
        assert bundle["type"] == "transaction"
        kinds = {e["resource"]["resourceType"] for e in bundle["entry"]}
        exp = expected_resources(payload)
        assert exp.issubset(kinds), f"{name}: thieu resource {exp - kinds}"

        print(f"  [OK]  {name:6} {mtype:22} -> {len(bundle['entry'])} entries, topic={topic}")

    # 4) Thong ke [CAN XAC MINH]
    verify_count = _count_verify()
    print(f"\n  [CAN XAC MINH] con lai: {verify_count} muc (xem README Muc 7)")

    if fails:
        print(f"\n=> {fails} payload FAIL.")
        return 1
    print("\n=> TAT CA 10 PAYLOAD PASS (schema + range + UCUM + mapper FHIR).")
    return 0


def _count_verify() -> int:
    n = 0
    for dev in reg.DEVICES.values():
        for v in dev.values():
            if isinstance(v, dict) and v.get("verify"):
                n += 1
            elif isinstance(v, list):
                for it in v:
                    if isinstance(it, dict) and it.get("verify"):
                        n += 1
    return n


if __name__ == "__main__":
    raise SystemExit(main())
