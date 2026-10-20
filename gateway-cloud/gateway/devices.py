"""Registry 10 thiet bi — nguon chan ly tap trung cho Data Contract.

Moi ma chuan (LOINC/UCUM/SNOMED/DICOM) deu khai bao o day, kem co `verify`:
verify=True  => la [CAN XAC MINH], chua duoc kiem chung, KHONG dung voi benh nhan that.
verify=False => ma da duoc tai lieu Data Contract xac nhan.

Tuyet doi KHONG bia ma: cho nao chua chac -> dung code.text + verify=True.
"""
from __future__ import annotations

# --- Hang so dung chung (Muc 0) ---
CLINIC_ID = "CLINIC001"
GATEWAY_ID = "GW-PI5-001"
PATIENT_ID = "BN-2026-000123"
ENCOUNTER_ID = "ENC-2026-0456"

BASE = "https://clinic001.example.vn"  # [CAN XAC MINH] domain that cua phong kham
SID = {
    "gateway": f"{BASE}/fhir/sid/gateway-id",
    "patient": f"{BASE}/fhir/sid/patient-id",
    "encounter": f"{BASE}/fhir/sid/encounter-id",
    "device": f"{BASE}/fhir/sid/device-id",
    "device_serial": f"{BASE}/fhir/sid/device-serial",
}

# He ma (token ngan trong MQTT -> URI day du trong FHIR)
SYSTEM_URI = {
    "LOINC": "http://loinc.org",
    "UCUM": "http://unitsofmeasure.org",
    "SNOMED": "http://snomed.info/sct",
    "DICOM": "http://dicom.nema.org/resources/ontology/DCM",
    "OBS_CAT": "http://terminology.hl7.org/CodeSystem/observation-category",
    "ACTCODE": "http://terminology.hl7.org/CodeSystem/v3-ActCode",
    "PROV_TYPE": "http://terminology.hl7.org/CodeSystem/provenance-participant-type",
    "V2_0074": "http://terminology.hl7.org/CodeSystem/v2-0074",
    "LOCAL": f"{BASE}/fhir/CodeSystem/local",
}

# UCUM bat buoc (Muc 0): code -> display_unit
UCUM_DISPLAY = {
    "/min": "bpm", "mm[Hg]": "mmHg", "Cel": "°C", "%": "%",
    "kg": "kg", "kg/m2": "kg/m2", "U/L": "U/L", "mg/dL": "mg/dL",
    "mV": "mV", "1": "",
}


def m(key, system, code, display, unit, decimals, lo, hi, required,
      verify=False, category="vital-signs"):
    """Khai bao mot chi so (measurement spec)."""
    return {
        "key": key, "system": system, "code": code, "display": display,
        "unit": unit, "decimals": decimals, "kt_min": lo, "kt_max": hi,
        "required": required, "verify": verify, "category": category,
    }


# =====================================================================
# REGISTRY 10 THIET BI
# =====================================================================
DEVICES = {
    # --- 5 thiet bi numeric (Data Contract Muc 2) ---
    "BP-01": {
        "device_type": "blood_pressure", "serial": "SN-BP01-0001",
        "mac": "A4:C1:38:00:00:01", "connection": "ble", "device_class": "commercial",
        "message_type": "observation.vitals",
        "ble_profile": "BLE Blood Pressure 0x1810",
        "snomed_type": {"code": "23701000", "display": "Blood pressure monitor", "verify": True},
        "panel": m("bp_panel", "LOINC", "85354-9", "Blood pressure panel", "mm[Hg]", 0, None, None, True),
        "components": [
            m("systolic", "LOINC", "8480-6", "Systolic blood pressure", "mm[Hg]", 0, 40, 300, True),
            m("diastolic", "LOINC", "8462-4", "Diastolic blood pressure", "mm[Hg]", 0, 20, 200, True),
            m("map", "LOINC", "8478-0", "Mean blood pressure", "mm[Hg]", 0, 30, 250, False),
        ],
        "extra": [m("pulse", "LOINC", "8867-4", "Heart rate", "/min", 0, 20, 300, False)],
    },
    "SPO-02": {
        "device_type": "pulse_oximeter", "serial": "SN-SPO02-0001",
        "mac": "A4:C1:38:00:00:02", "connection": "ble", "device_class": "commercial",
        "message_type": "observation.vitals",
        "ble_profile": "BLE Pulse Oximeter 0x1822",
        "snomed_type": {"code": "448703006", "display": "Pulse oximeter", "verify": True},
        "measurements": [
            m("spo2", "LOINC", "59408-5", "Oxygen saturation by Pulse oximetry", "%", 0, 50, 100, True),
            m("pulse", "LOINC", "8867-4", "Heart rate", "/min", 0, 20, 300, False),
            # Perfusion Index: chua co LOINC xac nhan -> LOCAL + verify
            m("perfusion_index", "LOCAL", "perfusion-index", "Perfusion index", "%", 1, 0.0, 20.0, False, verify=True),
        ],
    },
    "TMP-07": {
        "device_type": "thermometer", "serial": "SN-TMP07-0001",
        "mac": "A4:C1:38:00:00:07", "connection": "ble", "device_class": "commercial",
        "message_type": "observation.vitals",
        "ble_profile": "BLE Health Thermometer 0x1809",
        "snomed_type": {"code": "46262006", "display": "Thermometer", "verify": True},
        "measurements": [
            m("temp", "LOINC", "8310-5", "Body temperature", "Cel", 1, 30.0, 45.0, True),
        ],
    },
    "WGT-09": {
        "device_type": "weight_scale", "serial": "SN-WGT09-0001",
        "mac": "A4:C1:38:00:00:09", "connection": "ble", "device_class": "commercial",
        "message_type": "observation.vitals",
        "ble_profile": "BLE Weight Scale 0x181D",
        "snomed_type": {"code": "5042004", "display": "Weighing scale", "verify": True},
        "measurements": [
            m("weight", "LOINC", "29463-7", "Body weight", "kg", 1, 0.5, 400, True),
        ],
    },
    "LAB-05": {
        "device_type": "chemistry_analyzer", "serial": "SN-LAB05-0001",
        "mac": "A4:C1:38:00:00:05", "connection": "lan", "device_class": "commercial",
        "message_type": "observation.lab",
        "ble_profile": "LAN / driver rieng",
        "snomed_type": {"code": "257289009", "display": "Analyzer", "verify": True},
        # DiagnosticReport panel code tam
        "report": {"system": "LOINC", "code": "24323-8", "display": "Comprehensive metabolic panel", "verify": True,
                   "category_v2": {"code": "CH", "display": "Chemistry"}},
        "measurements": [
            m("alt", "LOINC", "1742-6", "Alanine aminotransferase (ALT)", "U/L", 0, 0, 5000, True, category="laboratory"),
            m("ast", "LOINC", "1920-8", "Aspartate aminotransferase (AST)", "U/L", 0, 0, 5000, True, category="laboratory"),
            m("ggt", "LOINC", "2324-2", "Gamma glutamyl transferase (GGT)", "U/L", 0, 0, 5000, True, category="laboratory"),
            m("bilirubin", "LOINC", "1975-2", "Bilirubin total", "mg/dL", 1, 0, 50, True, category="laboratory"),
            m("glucose_plasma", "LOINC", "2345-7", "Glucose [Mass/volume] in Serum or Plasma", "mg/dL", 0, 10, 1000, True, category="laboratory"),
        ],
    },

    # --- 5 thiet bi ngoai pham vi tai lieu (cau truc khac) ---
    "ECG-03": {
        "device_type": "ecg", "serial": "SN-ECG03-0001",
        "mac": "A4:C1:38:00:00:03", "connection": "ble", "device_class": "commercial",
        "message_type": "observation.waveform",
        "ble_profile": "BLE / driver rieng (waveform)",
        "snomed_type": {"code": "29303009", "display": "Electrocardiographic monitor", "verify": True},
        # Ma waveform/panel chua xac nhan -> verify
        "report": {"system": "LOINC", "code": "11524-6", "display": "EKG study", "verify": True,
                   "category": "procedure"},
        "waveform": m("ecg_rhythm", "LOCAL", "ecg-rhythm-lead-II", "ECG rhythm strip (lead II)", "mV", 3, None, None, True,
                      verify=True, category="procedure"),
        "extra": [m("heart_rate", "LOINC", "8867-4", "Heart rate", "/min", 0, 20, 300, True, category="procedure")],
    },
    "CAM-04": {
        "device_type": "telemedicine_camera", "serial": "SN-CAM04-0001",
        "mac": "A4:C1:38:00:00:04", "connection": "wifi", "device_class": "commercial",
        "message_type": "media.video",
        "ble_profile": "WiFi / RTSP (ngoai pham vi chi tiet)",
        "snomed_type": {"code": "1162722007", "display": "Camera", "verify": True},
        "media": {
            "code": {"system": "LOCAL", "code": "telemedicine-video", "display": "Telemedicine video clip", "verify": True},
            "type": "video",  # FHIR Media.type
        },
    },
    "ECH-06": {
        "device_type": "ultrasound", "serial": "SN-ECH06-0001",
        "mac": "A4:C1:38:00:00:06", "connection": "lan", "device_class": "commercial",
        "message_type": "imaging.study",
        "ble_profile": "LAN / DICOM (ngoai pham vi chi tiet)",
        "snomed_type": {"code": "16310003", "display": "Ultrasound scanner", "verify": True},
        "modality": {"system": "DICOM", "code": "US", "display": "Ultrasound"},  # DICOM modality US (xac nhan)
        "report": {"system": "LOINC", "code": "24558-9", "display": "US Abdomen", "verify": True,
                   "category": "imaging"},
    },
    "STE-08": {
        "device_type": "stethoscope", "serial": "SN-STE08-0001",
        "mac": "A4:C1:38:00:00:08", "connection": "ble", "device_class": "commercial",
        "message_type": "media.audio",
        "ble_profile": "BLE / driver rieng (audio)",
        "snomed_type": {"code": "37325003", "display": "Stethoscope", "verify": True},
        "media": {
            "code": {"system": "LOCAL", "code": "auscultation-audio", "display": "Cardiac auscultation audio", "verify": True},
            "type": "audio",
            "body_site": {"text": "Precordium", "verify": True},
        },
    },
    "GLU-10": {
        "device_type": "glucometer", "serial": "SN-GLU10-0001",
        "mac": "A4:C1:38:00:00:10", "connection": "ble", "device_class": "commercial",
        "message_type": "observation.lab",
        "ble_profile": "BLE Glucose 0x1808",
        "snomed_type": {"code": "337414009", "display": "Blood glucose meter", "verify": True},
        "measurements": [
            # Glucose MAO MACH 41653-7 (Data Contract khang dinh) — KHAC glucose huyet tuong 2345-7
            m("glucose_capillary", "LOINC", "41653-7", "Glucose [Mass/volume] in Capillary blood by Glucometer",
              "mg/dL", 0, 10, 1000, True, category="laboratory"),
        ],
        # Ngu canh bua an: can chot cach ma hoa -> verify
        "meal_context": {"text": "fasting", "verify": True},
    },
}

ALL_DEVICE_IDS = list(DEVICES.keys())
