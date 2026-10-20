"""Doc samples/mqtt/*.json -> mapper_fhir -> samples/fhir/*.bundle.json.

Chay:  python tools/gen_fhir.py   (chay sau gen_samples.py)
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gateway import mapper_fhir  # noqa: E402

MQTT_DIR = os.path.join(ROOT, "samples", "mqtt")
FHIR_DIR = os.path.join(ROOT, "samples", "fhir")


def main():
    os.makedirs(FHIR_DIR, exist_ok=True)
    files = sorted(f for f in os.listdir(MQTT_DIR) if f.endswith(".json"))
    for fn in files:
        with open(os.path.join(MQTT_DIR, fn), "r", encoding="utf-8") as f:
            payload = json.load(f)
        bundle = mapper_fhir.to_bundle(payload)
        out = os.path.join(FHIR_DIR, fn.replace(".json", ".bundle.json"))
        with open(out, "w", encoding="utf-8") as f:
            json.dump(bundle, f, ensure_ascii=False, indent=2)
        n = len(bundle["entry"])
        print(f"  {fn} -> {os.path.basename(out)} ({n} entries)")
    print(f"=> {len(files)} Bundle FHIR.")


if __name__ == "__main__":
    main()
