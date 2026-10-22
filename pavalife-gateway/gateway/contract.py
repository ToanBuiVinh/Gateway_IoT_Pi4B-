"""Dung ban tin Canonical PavaLife v2.1.

Firmware/driver cung cap gia tri do; Gateway (module nay) dong goi thanh ban tin
chuan: facility/gateway/source/patient_context/payload. Tuan thu rule #7 (khong
gui value:null), #8 (lab co specimen+report), #10 (patient_id khong vao topic).
"""
from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from . import registry as reg


def new_id() -> str:
    return str(uuid.uuid4())


def _patient_context(event_time: str) -> Dict[str, Any]:
    return {
        "patient_id": "BN-TEST-000001",
        "patient_id_issuer": reg.FACILITY_ID,
        "encounter_id": "ENC-TEST-000001",
        "encounter_id_issuer": reg.FACILITY_ID,
        "binding": {
            "binding_id": "BIND-TEST-001",
            "method": "manual",
            "status": "pending_verification",
            "bound_at": event_time,
        },
    }


def _base(message_type: str, event_time: str, sequence_no: int,
          source_type: str, with_patient: bool) -> Dict[str, Any]:
    msg = {
        "schema_version": reg.SCHEMA_VERSION,
        "message_id": new_id(),
        "message_type": message_type,
        "event_time": event_time,
        "sequence_no": sequence_no,
        "facility": {"facility_id": reg.FACILITY_ID},
        "gateway": {
            "gateway_id": reg.GATEWAY_ID,
            "software_version": reg.GATEWAY_SW,
            "received_at": event_time,
            "published_at": event_time,
            "clock_source": "ntp",
        },
        "source": {"source_id": reg.SOURCE_ID, "source_type": source_type, "connection": "wifi"},
    }
    if with_patient:
        msg["patient_context"] = _patient_context(event_time)
    return msg


# --- Phan tu measurements[] ---
def meas_value(obs_id: str, local_code: str, value, measured_at: str,
               status: str = "final", quality_status: str = "good",
               method: Optional[str] = None) -> Dict[str, Any]:
    spec = reg.M[local_code]
    item = {
        "observation_id": obs_id,
        "local_code": local_code,
        "code": spec["code"],
        "measured_at": measured_at,
        "status": status,
        "value": value,
        "unit": spec["unit"],
        "quality": {"status": quality_status},
    }
    if method:
        item["method"] = method
    return item


def component(local_code: str, value) -> Dict[str, Any]:
    spec = reg.M[local_code]
    return {"local_code": local_code, "code": spec["code"], "value": value, "unit": spec["unit"]}


def meas_panel(obs_id: str, panel_code: str, comps: List[Dict[str, Any]],
               measured_at: str, status: str = "final", method: str = "non-invasive") -> Dict[str, Any]:
    spec = reg.M[panel_code]
    return {
        "observation_id": obs_id,
        "local_code": panel_code,
        "code": spec["code"],
        "measured_at": measured_at,
        "status": status,
        "method": method,
        "components": comps,
        "quality": {"status": "good"},
    }


def meas_absent(obs_id: str, local_code: str, measured_at: str,
                reason: str = "not-available", quality_reason: str = "measurement not completed",
                method: Optional[str] = None, panel: bool = False) -> Dict[str, Any]:
    """Rule #7: thieu du lieu -> KHONG value:null; dung data_absent_reason."""
    spec = reg.M[local_code]
    item = {
        "observation_id": obs_id,
        "local_code": local_code,
        "code": spec["code"],
        "measured_at": measured_at,
        "status": "unknown",
        "quality": {"status": "unavailable", "reason": quality_reason},
        "data_absent_reason": reason,
    }
    if method:
        item["method"] = method
    return item


def _obs_id(device_id: str, seq: int, suffix: str) -> str:
    return f"{device_id}-{seq:06d}-{suffix}"


# --- Dung ban tin cho 1 thiet bi ---
def build_vitals(device_key: str, values: Dict[str, Any], event_time: str,
                 sequence_no: Optional[int] = None) -> Dict[str, Any]:
    dev = reg.DEVICES[device_key]
    seq = sequence_no if sequence_no is not None else reg.SEQ[device_key]
    did = dev["device_id"]
    measurements: List[Dict[str, Any]] = []

    if "nibp" in dev:  # may huyet ap: panel + components
        comps = [component(c, values[c]) for c in dev["nibp"]["components"] if c in values]
        measurements.append(meas_panel(_obs_id(did, seq, dev["nibp"]["suffix"]),
                                        dev["nibp"]["panel"], comps, event_time))
        for ex in dev.get("extra", []):
            lc = ex["local_code"]
            measurements.append(meas_value(_obs_id(did, seq, ex["suffix"]), lc, values[lc], event_time))
    else:
        for m in dev["measurements"]:
            lc = m["local_code"]
            measurements.append(meas_value(_obs_id(did, seq, m["suffix"]), lc, values[lc], event_time))

    msg = _base("observation.vitals", event_time, seq, dev["source_type"], with_patient=True)
    msg["payload"] = {"measurements": measurements}
    return msg


def build_lab(device_key: str, values: Dict[str, Any], event_time: str,
              sequence_no: Optional[int] = None) -> Dict[str, Any]:
    dev = reg.DEVICES[device_key]
    seq = sequence_no if sequence_no is not None else reg.SEQ[device_key]
    did = dev["device_id"]
    measurements = []
    for m in dev["measurements"]:
        lc = m["local_code"]
        measurements.append(meas_value(_obs_id(did, seq, m["suffix"]), lc, values[lc], event_time,
                                        status=m.get("status", "preliminary")))
    msg = _base("observation.lab", event_time, seq, dev["source_type"], with_patient=True)
    msg["payload"] = {
        "specimen": {"specimen_id": f"{did}-SPEC-{seq:06d}",
                     "specimen_type": dev["specimen_type"], "collected_at": event_time},
        "report": {"report_id": f"{did}-RPT-{seq:06d}", "status": "preliminary",
                   "issued_at": None, "verified_at": None},
        "measurements": measurements,
    }
    return msg


def build_imaging_study(device_key: str, event_time: str, sequence_no: Optional[int] = None,
                        instances: int = 24, body_site: str = "Abdomen") -> Dict[str, Any]:
    """Thong bao anh (imaging.study) — CHI tham chieu DICOM, KHONG chua pixel.

    Pixel duoc upload truoc qua DICOMweb STOW-RS / object storage (data plane);
    ban tin nay chi bao cloud co study moi & cach lay (wado_rs). Giu MQTT nhe.
    """
    dev = reg.DEVICES[device_key]
    seq = sequence_no if sequence_no is not None else reg.SEQ[device_key]
    did = dev["device_id"]
    study_uid = f"{reg.UID_ROOT}.100.{seq}"
    series_uid = f"{reg.UID_ROOT}.200.{seq}"
    wado = f"{reg.DICOMWEB_BASE}/studies/{study_uid}"
    msg = _base("imaging.study", event_time, seq, dev["source_type"], with_patient=True)
    msg["payload"] = {
        "study": {
            "study_instance_uid": study_uid,
            "accession_number": f"{did}-ACC-{seq:06d}",
            "modality": dev["modality"],
            "started_at": event_time,
            "number_of_series": 1,
            "number_of_instances": instances,
            "description": "Ultrasound abdomen",
            "body_site": body_site,
        },
        "series": [{
            "series_instance_uid": series_uid, "modality": dev["modality"],
            "number_of_instances": instances, "body_site": body_site,
        }],
        "storage": {
            "type": "dicomweb",
            "stored_at": event_time,
            "wado_rs_study": wado,                               # lay anh: WADO-RS
            "stow_rs": f"{reg.DICOMWEB_BASE}/studies",           # noi da luu: STOW-RS
            "thumbnail_url": f"{wado}/thumbnail",
            "size_bytes": 10485760,
            "transfer_syntax": "1.2.840.10008.1.2.4.50",         # JPEG Baseline
        },
    }
    return msg


def build_device_status(event_time: str, battery_percent: int = 85,
                        sequence_no: Optional[int] = None) -> Dict[str, Any]:
    seq = sequence_no if sequence_no is not None else reg.SEQ["device.status"]
    msg = _base("device.status", event_time, seq, "robot_doctor", with_patient=False)
    msg["payload"] = {
        "connectivity": "online",
        "battery_percent": battery_percent,
        "sensor_health": "ok",
        "last_measurement_at": event_time,
        "hardware_fault_codes": [],
    }
    return msg
