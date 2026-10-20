"""Mapper: Canonical v2.1 -> FHIR R4 transaction Bundle.

Ho tro 6 message_type:
  observation.vitals  -> Observation (+ component cho BP panel)
  observation.lab     -> Observation[] + DiagnosticReport
  observation.waveform-> Observation (valueSampledData) + HR + DiagnosticReport  (ECG)
  imaging.study       -> ImagingStudy + DiagnosticReport                          (sieu am)
  media.audio/video   -> Media                                                    (ong nghe / camera)

Patient/Encounter/Device dung POST + ifNoneExist (conditional create) -> gui lai
khong tao trung. Tham chieu noi bo qua urn:uuid: -> HAPI tu resolve.
Provenance ghi nhan assembler=Device, custodian=Gateway.
"""
from __future__ import annotations

from typing import Any, Dict, List

from . import devices as reg

RECORDED = "2026-10-20T09:05:00+07:00"


# --- Index (system, code) -> category tu registry ---
def _category_index() -> Dict[tuple, str]:
    idx = {}
    for dev in reg.DEVICES.values():
        specs = list(dev.get("measurements", [])) + list(dev.get("components", [])) \
            + list(dev.get("extra", []))
        if "panel" in dev:
            specs.append(dev["panel"])
        if "waveform" in dev:
            specs.append(dev["waveform"])
        for s in specs:
            idx[(s["system"], s["code"])] = s.get("category", "vital-signs")
    return idx


_CAT = _category_index()


def _uri(system_token: str) -> str:
    return reg.SYSTEM_URI.get(system_token, system_token)


def _cc_from_code(code: Dict[str, Any]) -> Dict[str, Any]:
    coding = {"system": _uri(code["system"]), "code": code["code"]}
    if code.get("display"):
        coding["display"] = code["display"]
    return {"coding": [coding]}


def _quantity(value, ucum: str) -> Dict[str, Any]:
    return {"value": value, "unit": reg.UCUM_DISPLAY.get(ucum, ucum),
            "system": reg.SYSTEM_URI["UCUM"], "code": ucum}


def _category(code: str) -> Dict[str, Any]:
    pass  # placeholder (unused)


def _obs_category(cat: str) -> Dict[str, Any]:
    return {"coding": [{"system": reg.SYSTEM_URI["OBS_CAT"], "code": cat}]}


def _entry(full_url: str, resource: Dict[str, Any], url: str,
           if_none_exist: str = None) -> Dict[str, Any]:
    req = {"method": "POST", "url": url}
    if if_none_exist:
        req["ifNoneExist"] = if_none_exist
    return {"fullUrl": full_url, "resource": resource, "request": req}


# --- Resource dung chung ---
def _patient_entry(pid: str) -> Dict[str, Any]:
    return _entry("urn:uuid:patient-1",
                  {"resourceType": "Patient",
                   "identifier": [{"system": reg.SID["patient"], "value": pid}]},
                  "Patient", f"identifier={reg.SID['patient']}|{pid}")


def _encounter_entry(eid: str) -> Dict[str, Any]:
    return _entry("urn:uuid:encounter-1",
                  {"resourceType": "Encounter", "status": "in-progress",
                   "class": {"system": reg.SYSTEM_URI["ACTCODE"], "code": "AMB", "display": "ambulatory"},
                   "identifier": [{"system": reg.SID["encounter"], "value": eid}],
                   "subject": {"reference": "urn:uuid:patient-1"},
                   "period": {"start": "2026-10-20T08:45:00+07:00"}},
                  "Encounter", f"identifier={reg.SID['encounter']}|{eid}")


def _device_entry(device_id: str, serial: str, fw: str) -> Dict[str, Any]:
    d = reg.DEVICES[device_id]
    st = d["snomed_type"]
    disp = st["display"] + (" [CAN XAC MINH]" if st.get("verify") else "")
    full = f"urn:uuid:device-{device_id.lower()}"
    res = {
        "resourceType": "Device",
        "identifier": [
            {"system": reg.SID["device"], "value": device_id},
            {"system": reg.SID["device_serial"], "value": serial},
        ],
        "status": "active", "manufacturer": "[CAN XAC MINH]",
        "deviceName": [{"name": d.get("ble_profile", device_id), "type": "user-friendly-name"}],
        "type": {"coding": [{"system": reg.SYSTEM_URI["SNOMED"], "code": st["code"], "display": disp}]},
        "version": [{"type": {"text": "firmware"}, "value": fw}],
        "property": [
            {"type": {"text": "connection"}, "valueCode": [{"text": d["connection"]}]},
            {"type": {"text": "device-class"}, "valueCode": [{"text": d["device_class"]}]},
        ],
    }
    return full, _entry(full, res, "Device", f"identifier={reg.SID['device']}|{device_id}")


def _provenance_entry(dev_full: str, targets: List[str], suffix: str) -> Dict[str, Any]:
    return _entry(f"urn:uuid:prov-{suffix}", {
        "resourceType": "Provenance",
        "target": [{"reference": t} for t in targets],
        "recorded": RECORDED,
        "agent": [
            {"type": {"coding": [{"system": reg.SYSTEM_URI["PROV_TYPE"], "code": "assembler"}]},
             "who": {"reference": dev_full}},
            {"type": {"coding": [{"system": reg.SYSTEM_URI["PROV_TYPE"], "code": "custodian"}]},
             "who": {"identifier": {"system": reg.SID["gateway"], "value": reg.GATEWAY_ID}}},
        ],
    }, "Provenance")


def _obs_base(full: str, cat: str, code: Dict[str, Any], effective: str,
              dev_full: str) -> Dict[str, Any]:
    return {
        "resourceType": "Observation", "status": "final",
        "category": [_obs_category(cat)],
        "code": code,
        "subject": {"reference": "urn:uuid:patient-1"},
        "encounter": {"reference": "urn:uuid:encounter-1"},
        "effectiveDateTime": effective,
        "device": {"reference": dev_full},
    }


# =====================================================================
# MAPPER CHINH
# =====================================================================
def to_bundle(payload: Dict[str, Any]) -> Dict[str, Any]:
    device_id = payload["device"]["device_id"]
    serial = payload["device"].get("serial_number", "")
    fw = payload["device"].get("firmware_version", "1.0.0")
    mtype = payload["message_type"]
    effective = payload["timestamps"]["measured_at"][:19] + payload["timestamps"]["measured_at"][-6:]
    # Dung thang measured_at goc cho effectiveDateTime (giu offset)
    effective = payload["timestamps"]["measured_at"]
    dev = reg.DEVICES[device_id]

    entries: List[Dict[str, Any]] = [
        _patient_entry(payload["patient"]["patient_id"]),
        _encounter_entry(payload["patient"].get("encounter_id", "")),
    ]
    dev_full, dev_entry = _device_entry(device_id, serial, fw)
    entries.append(dev_entry)

    obs_refs: List[str] = []

    if mtype in ("observation.vitals", "observation.lab"):
        obs_refs = _map_observations(payload, effective, dev_full, entries)
        if mtype == "observation.lab" and "report" in dev:
            rep_full = _add_diagnostic_report(dev, obs_refs, effective, entries, imaging_ref=None)
            _finish(entries, dev_full, [rep_full])
        else:
            _finish(entries, dev_full, obs_refs)

    elif mtype == "observation.waveform":
        obs_refs = _map_waveform(payload, dev, effective, dev_full, entries)
        rep_full = _add_diagnostic_report(dev, obs_refs, effective, entries, imaging_ref=None)
        _finish(entries, dev_full, [rep_full])

    elif mtype == "imaging.study":
        img_full, media_full = _map_imaging(payload, dev, effective, dev_full, entries)
        rep_full = _add_diagnostic_report(dev, [], effective, entries, imaging_ref=img_full,
                                          media_ref=media_full)
        _finish(entries, dev_full, [rep_full])

    elif mtype in ("media.audio", "media.video"):
        media_full = _map_media(payload, dev, effective, dev_full, entries)
        _finish(entries, dev_full, [media_full])

    else:
        raise ValueError(f"message_type chua ho tro map FHIR: {mtype}")

    return {"resourceType": "Bundle", "type": "transaction", "entry": entries}


def _finish(entries: List[Dict[str, Any]], dev_full: str, targets: List[str]) -> None:
    suffix = dev_full.split("device-")[-1]
    entries.append(_provenance_entry(dev_full, targets, suffix))


def _map_observations(payload, effective, dev_full, entries) -> List[str]:
    refs = []
    for i, meas in enumerate(payload["measurements"]):
        code = meas["code"]
        cat = _CAT.get((code["system"], code["code"]), "vital-signs")
        full = f"urn:uuid:obs-{code['code']}-{i}"
        res = _obs_base(full, cat, _cc_from_code(code), effective, dev_full)
        if meas.get("components"):
            res["component"] = [
                {"code": _cc_from_code(c["code"]), "valueQuantity": _quantity(c["value"], c["unit"])}
                for c in meas["components"]
            ]
        elif meas.get("value") is not None:
            res["valueQuantity"] = _quantity(meas["value"], meas["unit"])
        entries.append(_entry(full, res, "Observation"))
        refs.append(full)
    return refs


def _map_waveform(payload, dev, effective, dev_full, entries) -> List[str]:
    refs = []
    for i, meas in enumerate(payload["measurements"]):
        code = meas["code"]
        cat = _CAT.get((code["system"], code["code"]), "procedure")
        full = f"urn:uuid:obs-{code['code']}-{i}"
        res = _obs_base(full, cat, _cc_from_code(code), effective, dev_full)
        sd = meas.get("sampled_data")
        if sd:
            res["valueSampledData"] = {
                "origin": _quantity(sd.get("origin_value", 0), sd["unit"]),
                "period": sd["period_ms"],
                "factor": sd.get("factor", 1),
                "dimensions": sd.get("dimensions", 1),
                "data": sd["data"],
            }
        elif meas.get("value") is not None:
            res["valueQuantity"] = _quantity(meas["value"], meas["unit"])
        entries.append(_entry(full, res, "Observation"))
        refs.append(full)
    return refs


def _add_diagnostic_report(dev, result_refs, effective, entries, imaging_ref, media_ref=None) -> str:
    rep = dev["report"]
    disp = rep["display"] + (" [CAN XAC MINH]" if rep.get("verify") else "")
    full = f"urn:uuid:report-{dev['device_type']}"
    res = {
        "resourceType": "DiagnosticReport", "status": "final",
        "code": {"coding": [{"system": _uri(rep["system"]), "code": rep["code"], "display": disp}]},
        "subject": {"reference": "urn:uuid:patient-1"},
        "encounter": {"reference": "urn:uuid:encounter-1"},
        "effectiveDateTime": effective,
    }
    if rep.get("category_v2"):
        res["category"] = [{"coding": [{"system": reg.SYSTEM_URI["V2_0074"],
                                        "code": rep["category_v2"]["code"],
                                        "display": rep["category_v2"]["display"]}]}]
    if result_refs:
        res["result"] = [{"reference": r} for r in result_refs]
    if imaging_ref:
        res["imagingStudy"] = [{"reference": imaging_ref}]
    if media_ref:
        res["media"] = [{"link": {"reference": media_ref}}]
    entries.append(_entry(full, res, "DiagnosticReport"))
    return full


def _map_imaging(payload, dev, effective, dev_full, entries):
    full = f"urn:uuid:imaging-{dev['device_type']}"
    mod = dev["modality"]
    meas = next((m for m in payload["measurements"] if m.get("media") or m.get("raster")),
                payload["measurements"][0])
    media = meas.get("media", {}) or {}
    raster = meas.get("raster")
    res = {
        "resourceType": "ImagingStudy", "status": "available",
        "subject": {"reference": "urn:uuid:patient-1"},
        "encounter": {"reference": "urn:uuid:encounter-1"},
        "started": effective,
        "modality": [{"system": _uri(mod["system"]), "code": mod["code"], "display": mod["display"]}],
        "numberOfSeries": media.get("number_of_series", 1),
        "numberOfInstances": media.get("number_of_instances", 1),
        "procedureCode": [{"text": "Ultrasound study [CAN XAC MINH]"}],
    }
    if media.get("url"):
        res["endpoint"] = [{"display": media["url"]}]
    entries.append(_entry(full, res, "ImagingStudy"))

    # Du lieu diem anh THO -> Media inline (base64). San xuat that dung DICOM. [CAN XAC MINH]
    media_full = None
    if raster:
        media_full = f"urn:uuid:media-{dev['device_type']}"
        ctype = (f"application/octet-stream; format={raster['pixel_format']};"
                 f" width={raster['width']}; height={raster['height']}")
        mres = {
            "resourceType": "Media", "status": "completed",
            "type": {"coding": [{"system": _MEDIA_TYPE_SYS, "code": "image"}]},
            "subject": {"reference": "urn:uuid:patient-1"},
            "encounter": {"reference": "urn:uuid:encounter-1"},
            "createdDateTime": effective,
            "device": {"reference": dev_full},
            "height": raster["height"], "width": raster["width"],
            "content": {"contentType": ctype, "data": raster["data"],
                        "title": meas["code"].get("display", "Ultrasound frame")},
        }
        if media.get("body_site"):
            mres["bodySite"] = {"text": media["body_site"]}
        entries.append(_entry(media_full, mres, "Media"))
    return full, media_full


_MEDIA_TYPE_SYS = "http://terminology.hl7.org/CodeSystem/media-type"


def _map_media(payload, dev, effective, dev_full, entries) -> str:
    meas = next((m for m in payload["measurements"] if m.get("media")), payload["measurements"][0])
    media = meas["media"]
    mcfg = dev["media"]
    full = f"urn:uuid:media-{dev['device_type']}"
    attachment = {
        "contentType": media["content_type"],
        "url": media["url"],
        "title": meas["code"].get("display", dev["device_type"]),
    }
    if media.get("size_bytes") is not None:
        attachment["size"] = media["size_bytes"]
    if media.get("sha256"):
        # Attachment.hash la base64Binary; day la sha256 hex placeholder [CAN XAC MINH cach ma hoa]
        attachment["hash"] = media["sha256"]
    # Luu y: Attachment KHONG co truong duration — duration nam o Media.duration ben duoi.
    res = {
        "resourceType": "Media", "status": "completed",
        "type": {"coding": [{"system": _MEDIA_TYPE_SYS, "code": mcfg["type"]}]},
        "subject": {"reference": "urn:uuid:patient-1"},
        "encounter": {"reference": "urn:uuid:encounter-1"},
        "createdDateTime": effective,
        "device": {"reference": dev_full},
        "content": attachment,
    }
    if media.get("duration_sec") is not None:
        res["duration"] = media["duration_sec"]
    if media.get("frames") is not None:
        res["frames"] = media["frames"]
    if media.get("width"):
        res["width"] = media["width"]
    if media.get("height"):
        res["height"] = media["height"]
    bs = mcfg.get("body_site")
    if bs:
        res["bodySite"] = {"text": bs["text"] + (" [CAN XAC MINH]" if bs.get("verify") else "")}
    entries.append(_entry(full, res, "Media"))
    return full
