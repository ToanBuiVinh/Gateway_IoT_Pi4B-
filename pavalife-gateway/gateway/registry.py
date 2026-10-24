"""Registry 6 thiet bi PavaLife + hang so chung (theo Device Data Contract v2.1)."""
from __future__ import annotations

SCHEMA_VERSION = "2.1"

# --- Hang so he thong (Bang 0) ---
FACILITY_ID = "PVL-ROBOT-DEV"
GATEWAY_ID = "GW-ROBOT-DEV-001"
GATEWAY_SW = "0.2.0"
SOURCE_ID = "ROBOT-DEV-001"
BROKER_URL = "wss://mqtt-hn-n1.pavalife.com:443/mqtt"   # MQTT 5.0 over WSS
TOPIC_TPL = "pvl/v2/gw/{gateway_id}/up/{message_type}"  # rule #10: KHONG co patient_id

LOINC = "http://loinc.org"
UCUM = "http://unitsofmeasure.org"


def code(c, display):
    return {"system": LOINC, "code": c, "display": display}


def unit(c, display):
    return {"system": UCUM, "code": c, "display": display}


# --- Dinh nghia phep do (local_code -> code/unit/thresholds) ---
# thr = (min, max) nguong hop le KY THUAT tai gateway (khong phai nguong lam sang)
M = {
    # Huyet ap (panel + components)
    "nibp":        {"code": code("85354-9", "Blood pressure panel"), "unit": None, "thr": None, "panel": True},
    "systolic":    {"code": code("8480-6", "Systolic blood pressure"), "unit": unit("mm[Hg]", "mmHg"), "thr": (50, 260)},
    "diastolic":   {"code": code("8462-4", "Diastolic blood pressure"), "unit": unit("mm[Hg]", "mmHg"), "thr": (30, 160)},
    "mean":        {"code": code("8478-0", "Mean blood pressure"), "unit": unit("mm[Hg]", "mmHg"), "thr": (40, 200)},
    "pulse_rate":  {"code": code("8867-4", "Heart rate"), "unit": unit("/min", "beats/minute"), "thr": (30, 220)},
    # SpO2
    "spo2":        {"code": code("2708-6", "Oxygen saturation in arterial blood"), "unit": unit("%", "percent"), "thr": (50, 100)},
    "heart_rate":  {"code": code("8867-4", "Heart rate"), "unit": unit("/min", "beats/minute"), "thr": (30, 250)},
    # Nhiet do
    "temperature": {"code": code("8310-5", "Body temperature"), "unit": unit("Cel", "degree Celsius"), "thr": (30.0, 43.0)},
    # Can
    "body_weight": {"code": code("29463-7", "Body weight"), "unit": unit("kg", "kilogram"), "thr": (2, 300)},
    # Xet nghiem axit uric
    "uric_acid":   {"code": code("14933-6", "Urate [Moles/volume] in Serum or Plasma"), "unit": unit("umol/L", "micromole per liter"), "thr": (90, 1200)},
    # Duong huyet
    "blood_glucose": {"code": code("14743-9", "Glucose [Moles/volume] in Capillary blood by Glucometer"), "unit": unit("mmol/L", "millimole per liter"), "thr": (1.1, 33.3)},
}

# --- 6 thiet bi (Bang 1) ---
DEVICES = {
    "blood_pressure": {
        "device_id": "BP-001", "message_type": "observation.vitals", "source_type": "robot_doctor",
        "nibp": {"panel": "nibp", "components": ["systolic", "diastolic", "mean"], "suffix": "NIBP"},
        "extra": [{"local_code": "pulse_rate", "suffix": "PR"}],
    },
    "spo2": {
        "device_id": "SPO2-001", "message_type": "observation.vitals", "source_type": "robot_doctor",
        "measurements": [{"local_code": "spo2", "suffix": "SPO2"}, {"local_code": "heart_rate", "suffix": "HR"}],
    },
    "thermometer": {
        "device_id": "TEMP-001", "message_type": "observation.vitals", "source_type": "robot_doctor",
        "measurements": [{"local_code": "temperature", "suffix": "TEMP"}],
    },
    "scale": {
        "device_id": "SCALE-001", "message_type": "observation.vitals", "source_type": "robot_doctor",
        "measurements": [{"local_code": "body_weight", "suffix": "WT"}],
    },
    "lab_analyzer": {
        "device_id": "LAB-001", "message_type": "observation.lab", "source_type": "lab_analyzer",
        "specimen_type": "capillary_blood",
        "measurements": [{"local_code": "uric_acid", "suffix": "UA", "status": "preliminary"}],
    },
    "glucose": {
        "device_id": "GLU-001", "message_type": "observation.lab", "source_type": "lab_analyzer",
        "specimen_type": "capillary_blood",
        "measurements": [{"local_code": "blood_glucose", "suffix": "GLU", "status": "preliminary"}],
    },
    # Sieu am: imaging.study (control plane) — pixel tai qua DICOMweb (data plane)
    "ultrasound": {
        "device_id": "US-001", "message_type": "imaging.study", "source_type": "imaging_device",
        "modality": "US",
    },
    # Ong nghe dien tu: observation.audio — file WAV/FLAC lossless + live streaming
    "stethoscope": {
        "device_id": "STE-001", "message_type": "observation.audio", "source_type": "auscultation_device",
    },
}

# Noi luu file am thanh goc (lossless) va endpoint nghe truc tiep. [CAN PAVALIFE XAC NHAN]
AUDIO_STORAGE_BASE = "s3://pvl-audio/PVL-ROBOT-DEV"
LIVE_MEDIA_BASE = "wss://media.pavalife.com/live"

# DICOMweb cua PACS (noi luu & lay anh). [CAN PAVALIFE XAC NHAN]
DICOMWEB_BASE = "https://pacs.pavalife.com/dicom-web"
UID_ROOT = "1.2.826.0.1.3680043.8.498"   # OID goc (vi du) — PavaLife cap OID that

# Thu tu + sequence_no demo (device.status=100, roi 101..106)
ORDER = ["blood_pressure", "spo2", "thermometer", "scale", "lab_analyzer", "glucose"]
SEQ = {"blood_pressure": 101, "spo2": 102, "thermometer": 103, "scale": 104,
       "lab_analyzer": 105, "glucose": 106, "ultrasound": 107, "stethoscope": 108,
       "device.status": 100}


def topic_for(message_type: str) -> str:
    return TOPIC_TPL.format(gateway_id=GATEWAY_ID, message_type=message_type)
