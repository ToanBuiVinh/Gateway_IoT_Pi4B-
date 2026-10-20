"""Validator: JSON Schema (Canonical v2.1) + khoang hop le KY THUAT + UCUM.

- Schema bat loi cau truc/kieu.
- Range check loc "du lieu rac" (gia tri phi ly nghi loi do) theo Muc 2.
- UCUM check: don vi numeric phai nam trong bang UCUM bat buoc.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Tuple

import jsonschema

from . import devices as reg

_SCHEMA_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "schema", "canonical-v2.schema.json")


def load_schema() -> Dict[str, Any]:
    with open(_SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


_VALIDATOR = jsonschema.Draft202012Validator(load_schema())


def validate_schema(payload: Dict[str, Any]) -> List[str]:
    """Tra ve danh sach loi schema (rong = hop le)."""
    errs = []
    for e in sorted(_VALIDATOR.iter_errors(payload), key=lambda x: list(x.path)):
        loc = "/".join(str(p) for p in e.path) or "(root)"
        errs.append(f"[schema] {loc}: {e.message}")
    return errs


def _range_index() -> Dict[Tuple[str, str], Dict[str, Any]]:
    """Index (system, code) -> spec de tra khoang KT nhanh."""
    idx: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for dev in reg.DEVICES.values():
        specs: List[Dict[str, Any]] = []
        specs += dev.get("measurements", [])
        specs += dev.get("components", [])
        specs += dev.get("extra", [])
        if "panel" in dev:
            specs.append(dev["panel"])
        if "waveform" in dev:
            specs.append(dev["waveform"])
        for s in specs:
            idx[(s["system"], s["code"])] = s
    return idx


_RANGE = _range_index()


def validate_ranges(payload: Dict[str, Any]) -> List[str]:
    """Kiem tra gia tri numeric nam trong khoang hop le KY THUAT + UCUM hop le."""
    errs: List[str] = []

    def check_value(system: str, code: str, value, unit):
        spec = _RANGE.get((system, code))
        if unit is not None and unit not in reg.UCUM_DISPLAY:
            errs.append(f"[ucum] {system}|{code}: don vi '{unit}' khong thuoc bang UCUM bat buoc")
        if spec and isinstance(value, (int, float)):
            lo, hi = spec.get("kt_min"), spec.get("kt_max")
            if lo is not None and hi is not None and not (lo <= value <= hi):
                errs.append(f"[range] {system}|{code}={value} ngoai khoang KT [{lo},{hi}]")

    for meas in payload.get("measurements", []):
        c = meas.get("code", {})
        if meas.get("value") is not None:
            check_value(c.get("system"), c.get("code"), meas.get("value"), meas.get("unit"))
        for comp in (meas.get("components") or []):
            cc = comp.get("code", {})
            check_value(cc.get("system"), cc.get("code"), comp.get("value"), comp.get("unit"))
    return errs


def validate(payload: Dict[str, Any]) -> List[str]:
    """Validate day du: schema truoc; neu pass thi check range + UCUM."""
    errs = validate_schema(payload)
    if errs:
        return errs
    return validate_ranges(payload)
