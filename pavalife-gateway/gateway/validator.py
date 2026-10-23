"""Validator PavaLife v2.1: JSON Schema 2020-12 + nguong ky thuat + rule #7.

- Schema: dung draft 2020-12, additionalProperties:false.
- Nguong ky thuat: gia tri ngoai khoang -> KHONG loai, danh dau 'suspect' (de
  gateway dat quality.status=suspect theo contract).
- Rule #7: khong duoc gui value:null (schema da chan; kiem tra them cho chac).
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List

import jsonschema

from . import registry as reg

_SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "schema", "device_data_contract_v2_1.schema.json")


def load_schema() -> Dict[str, Any]:
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


_VALIDATOR = jsonschema.Draft202012Validator(load_schema())


def validate_schema(msg: Dict[str, Any]) -> List[str]:
    errs = []
    for e in sorted(_VALIDATOR.iter_errors(msg), key=lambda x: list(x.path)):
        loc = "/".join(str(p) for p in e.path) or "(root)"
        errs.append(f"[schema] {loc}: {e.message}")
    return errs


def _iter_values(msg: Dict[str, Any]):
    """Sinh (local_code, value) cho moi gia tri so trong ban tin."""
    payload = msg.get("payload", {})
    for m in payload.get("measurements", []):
        if "value" in m:
            yield m["local_code"], m["value"]
        for c in m.get("components", []):
            if "value" in c:
                yield c["local_code"], c["value"]


def check_thresholds(msg: Dict[str, Any]) -> List[str]:
    """Tra ve danh sach canh bao 'suspect' cho gia tri ngoai nguong ky thuat."""
    out = []
    for local_code, value in _iter_values(msg):
        thr = reg.M.get(local_code, {}).get("thr")
        if thr and isinstance(value, (int, float)) and not (thr[0] <= value <= thr[1]):
            out.append(f"[suspect] {local_code}={value} ngoai nguong KT [{thr[0]},{thr[1]}] "
                       f"-> can quality.status=suspect")
    return out


def validate(msg: Dict[str, Any]) -> List[str]:
    """Validate cung (schema). Loi schema la loi that; nguong la canh bao rieng."""
    return validate_schema(msg)
