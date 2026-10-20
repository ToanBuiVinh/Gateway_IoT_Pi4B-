"""Bo dung envelope Canonical v2.1.

Firmware chi gui device/patient/measurements; Gateway (module nay) tu gan
message_id (UUID v4), sequence_no va 3 moc thoi gian — dung Muc 1.3 Data Contract.
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from . import devices as reg

SCHEMA_VERSION = "2.1"


def new_message_id() -> str:
    return str(uuid.uuid4())


def build_timestamps(measured_at: str, received_at: str, sent_at: str,
                     clock_source: str = "ntp") -> Dict[str, Any]:
    return {
        "measured_at": measured_at,
        "received_at": received_at,
        "sent_at": sent_at,
        "clock_source": clock_source,
    }


def build_device(device_id: str, firmware: str = "1.0.0") -> Dict[str, Any]:
    d = reg.DEVICES[device_id]
    return {
        "device_id": device_id,
        "device_type": d["device_type"],
        "serial_number": d["serial"],
        "firmware_version": firmware,
        "connection": d["connection"],
        "mac_address": d["mac"],
        "device_class": d["device_class"],
    }


# --- Helpers tao phan tu measurements[] ---
def _code(spec: Dict[str, Any]) -> Dict[str, str]:
    display = spec["display"]
    if spec.get("verify"):
        display = f"{display} [CAN XAC MINH]"
    return {"system": spec["system"], "code": spec["code"], "display": display}


def meas_numeric(spec: Dict[str, Any], value: float,
                 signal_quality: Optional[str] = "good") -> Dict[str, Any]:
    return {
        "code": _code(spec),
        "value": value,
        "unit": spec["unit"],
        "status": "final",
        "quality": {"signal_quality": signal_quality, "confidence": None},
        "device_flags": {},
    }


def meas_panel(panel_spec: Dict[str, Any], comp_specs: List[Dict[str, Any]],
               values: Dict[str, float], device_flags: Optional[dict] = None) -> Dict[str, Any]:
    comps = []
    for cs in comp_specs:
        if cs["key"] in values:
            comps.append({
                "code": {"system": cs["system"], "code": cs["code"]},
                "value": values[cs["key"]],
                "unit": cs["unit"],
            })
    return {
        "code": _code(panel_spec),
        "value": None,
        "unit": panel_spec["unit"],
        "status": "final",
        "components": comps,
        "quality": {"signal_quality": "good", "confidence": None},
        "device_flags": device_flags or {},
    }


def meas_waveform(spec: Dict[str, Any], sampled: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "code": _code(spec),
        "value": None,
        "unit": spec["unit"],
        "status": "final",
        "sampled_data": sampled,
        "quality": {"signal_quality": "good", "confidence": None},
        "device_flags": {},
    }


def meas_media(code: Dict[str, Any], media: Dict[str, Any]) -> Dict[str, Any]:
    c = {"system": code["system"], "code": code["code"],
         "display": code["display"] + (" [CAN XAC MINH]" if code.get("verify") else "")}
    return {
        "code": c,
        "status": "final",
        "media": media,
        "device_flags": {},
    }


def build_envelope(device_id: str, message_type: str, timestamps: Dict[str, Any],
                   measurements: List[Dict[str, Any]], sequence_no: int,
                   message_id: Optional[str] = None,
                   bound_at: str = "2026-10-20T08:46:00+07:00") -> Dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "message_id": message_id or new_message_id(),
        "message_type": message_type,
        "clinic_id": reg.CLINIC_ID,
        "gateway_id": reg.GATEWAY_ID,
        "sequence_no": sequence_no,
        "timestamps": timestamps,
        "device": build_device(device_id),
        "patient": {"patient_id": reg.PATIENT_ID, "encounter_id": reg.ENCOUNTER_ID},
        "patient_binding": {"method": "qr_scan", "operator_id": "NV-014", "bound_at": bound_at},
        "measurements": measurements,
    }
