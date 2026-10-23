"""Kiem thu PavaLife v2.1: validate 9 ban tin + kiem tra rule.

Chay:  python tests/test_contract.py
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gateway import registry as reg      # noqa: E402
from gateway import validator            # noqa: E402

SAMPLES = os.path.join(ROOT, "samples")


def _no_null_value(obj) -> bool:
    """Rule #7: khong duoc co value:null o bat ky dau."""
    if isinstance(obj, dict):
        if "value" in obj and obj["value"] is None:
            return False
        return all(_no_null_value(v) for v in obj.values())
    if isinstance(obj, list):
        return all(_no_null_value(v) for v in obj)
    return True


def main() -> int:
    files = sorted(f for f in os.listdir(SAMPLES) if f.endswith(".json"))
    assert files, "khong co ban tin mau"
    fails = 0
    for fn in files:
        with open(os.path.join(SAMPLES, fn), encoding="utf-8") as f:
            msg = json.load(f)
        name = fn[:-5]

        errs = validator.validate(msg)
        if errs:
            fails += 1
            print(f"  [FAIL] {name}: {errs[:3]}")
            continue

        mtype = msg["message_type"]
        # Rule #10: patient_id KHONG nam trong topic
        topic = reg.topic_for(mtype)
        assert "patient" not in topic.lower() and "BN-" not in topic
        # Rule #7: khong value:null
        assert _no_null_value(msg), f"{name}: co value:null"
        # observation.* / imaging.study phai co patient_context
        if mtype.startswith("observation") or mtype == "imaging.study":
            assert "patient_context" in msg, f"{name}: thieu patient_context"
        # imaging.study: KHONG chua pixel trong ban tin; phai co tham chieu storage
        if mtype == "imaging.study":
            st = msg["payload"]["storage"]
            assert "wado_rs_study" in st or "stow_rs" in st, f"{name}: thieu tham chieu DICOMweb"
            assert "data" not in json.dumps(msg), f"{name}: khong duoc nhung pixel (data) trong MQTT"
        # Rule #8: observation.lab phai co specimen + report + source_type lab_analyzer/lis
        if mtype == "observation.lab":
            p = msg["payload"]
            assert "specimen" in p and "report" in p, f"{name}: lab thieu specimen/report"
            assert msg["source"]["source_type"] in ("lab_analyzer", "lis")
        # Canh bao nguong (khong phai loi)
        warns = validator.check_thresholds(msg)

        extra = f"  ⚠ {warns}" if warns else ""
        print(f"  [OK]  {name:14} {mtype:20} seq={msg['sequence_no']:<4} topic={topic}{extra}")

    if fails:
        print(f"\n=> {fails} ban tin FAIL.")
        return 1
    print(f"\n=> TAT CA {len(files)} BAN TIN PASS (schema 2020-12 + rule #7/#8/#10).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
