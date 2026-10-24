"""Sinh ban tin mau PavaLife v2.1 -> pavalife-gateway/samples/.

Chay:  python tools/gen_samples.py
Gia tri & cau truc khop vi du trong Data Contract v2.1.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gateway import contract as C      # noqa: E402
from gateway import registry as reg    # noqa: E402

OUT = os.path.join(ROOT, "samples")

# message_id co dinh cho ban mau (thuc te: UUID moi su kien - rule #2)
MID = {
    "device_status": "cbb8ee55-f3e1-4844-8744-e39f9321ab58",
    "bp": "b493f061-b046-4e7a-a361-01ed3a981a05",
    "spo2": "29e79fe6-b7f0-46ab-b2d5-2492e599d86b",
    "temp": "7a1c2d3e-0001-4a10-9b20-000000000103",
    "scale": "7a1c2d3e-0001-4a10-9b20-000000000104",
    "lab": "b18c4116-4b7f-4666-9723-9edf1d7bf190",
    "glu": "3c551120-7a4d-43f8-8b23-db77953182ce",
    "ultrasound": "7a1c2d3e-0001-4a10-9b20-000000000107",
    "stethoscope": "7a1c2d3e-0001-4a10-9b20-000000000108",
    "bp_absent": "7a1c2d3e-0002-4a10-9b20-000000000201",
    "temp_absent": "7a1c2d3e-0002-4a10-9b20-000000000203",
}
ET = "2026-10-21T21:56:23"


def _t(ms):
    return f"{ET}.{ms:03d}+07:00"


def build_all():
    out = {}
    out["device_status"] = C.build_device_status(_t(701))
    out["bp"] = C.build_vitals("blood_pressure",
                               {"systolic": 120, "diastolic": 80, "mean": 93, "pulse_rate": 78}, _t(693))
    out["spo2"] = C.build_vitals("spo2", {"spo2": 99, "heart_rate": 80}, _t(696))
    out["temp"] = C.build_vitals("thermometer", {"temperature": 36.8}, _t(697))
    out["scale"] = C.build_vitals("scale", {"body_weight": 64.3}, _t(698))
    out["lab"] = C.build_lab("lab_analyzer", {"uric_acid": 360}, _t(699))
    out["glu"] = C.build_lab("glucose", {"blood_glucose": 5.6}, _t(700))
    out["ultrasound"] = C.build_imaging_study("ultrasound", _t(702))
    out["stethoscope"] = C.build_audio_recording("stethoscope", _t(703))

    # Ca THIEU DU LIEU (rule #7): khong value:null -> data_absent_reason
    et = _t(695)
    bpa = C._base("observation.vitals", et, 201, "robot_doctor", True)
    bpa["payload"] = {"measurements": [
        C.meas_absent(C._obs_id("BP-001", 201, "NIBP"), "nibp", et, method="non-invasive"),
        C.meas_value(C._obs_id("BP-001", 201, "PR"), "pulse_rate", 72, et),
    ]}
    out["bp_absent"] = bpa

    ta = C._base("observation.vitals", et, 203, "robot_doctor", True)
    ta["payload"] = {"measurements": [
        C.meas_absent(C._obs_id("TEMP-001", 203, "TEMP"), "temperature", et,
                      quality_reason="sensor read error"),
    ]}
    out["temp_absent"] = ta

    for name, msg in out.items():
        if name in MID:
            msg["message_id"] = MID[name]
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, msg in build_all().items():
        path = os.path.join(OUT, f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(msg, f, ensure_ascii=False, indent=2)
        print(f"  wrote {os.path.basename(path)}  (seq {msg['sequence_no']}, {msg['message_type']})")
    print("=> 9 ban tin mau.")


if __name__ == "__main__":
    main()
