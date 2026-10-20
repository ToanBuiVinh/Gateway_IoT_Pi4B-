"""Sinh 10 payload MQTT Canonical v2.1 -> gateway-cloud/samples/mqtt/.

Chay:  python tools/gen_samples.py
Gia tri khop dashboard; 5 thiet bi numeric theo dung Data Contract Muc 3.
"""
from __future__ import annotations

import base64
import json
import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gateway import canonical as C          # noqa: E402
from gateway import devices as reg          # noqa: E402

OUT = os.path.join(ROOT, "samples", "mqtt")


def ts(measured, received, sent):
    return C.build_timestamps(measured, received, sent, "ntp")


# ---------------------------------------------------------------------
# DU LIEU THO: ECG (PQRST) — mau tin hieu tho, factor 0.001 mV/don vi
# ---------------------------------------------------------------------
def _ecg_samples(duration_s=2.5, fs=500, hr=72, seed=42):
    rng = random.Random(seed)
    n = int(duration_s * fs)
    rr = 60.0 / hr

    def g(t, c, a, w):
        return a * math.exp(-((t - c) ** 2) / (2 * w * w))

    beats = []
    t = 0.30
    while t < duration_s:
        beats.append(t)
        t += rr
    adc = []
    for i in range(n):
        tt = i / fs
        v = 0.0
        for b in beats:
            v += g(tt, b - 0.16, 0.12, 0.025)   # P
            v += g(tt, b - 0.02, -0.10, 0.008)  # Q
            v += g(tt, b,         1.00, 0.010)  # R
            v += g(tt, b + 0.03, -0.22, 0.011)  # S
            v += g(tt, b + 0.20,  0.30, 0.045)  # T
        v += rng.uniform(-0.012, 0.012)         # nhieu nen
        adc.append(int(round(v / 0.001)))       # mV -> don vi ADC (factor 0.001)
    return adc, n


# ---------------------------------------------------------------------
# DU LIEU THO: SIEU AM — ma tran diem anh gray8 (B-mode sector), base64
# ---------------------------------------------------------------------
def _ultrasound_gray8(w=176, h=132, seed=7):
    rng = random.Random(seed)
    buf = bytearray(w * h)
    apex_x, apex_y = w / 2.0, -6.0
    half = math.radians(35)
    rmin, rmax = 8.0, math.hypot(w / 2.0, h) + 6.0

    # Cau truc thai: tui oi (anechoic) + so thai (echogenic ring) + duong giua
    sac_cx, sac_cy, sac_rx, sac_ry = w * 0.52, h * 0.56, w * 0.30, h * 0.30
    head_cx, head_cy, head_r = w * 0.46, h * 0.52, h * 0.19

    for y in range(h):
        for x in range(w):
            dx, dy = x - apex_x, y - apex_y
            r = math.hypot(dx, dy)
            ang = math.atan2(dx, dy)
            if abs(ang) > half or not (rmin <= r <= rmax):
                buf[y * w + x] = 0
                continue
            depth = (r - rmin) / (rmax - rmin)
            val = 120.0 * math.exp(-1.7 * depth) + 22.0        # suy giam theo do sau
            val *= max(0.12, rng.gauss(1.0, 0.33))             # speckle
            if depth < 0.07:                                    # dai gan (near field) sang
                val += 55.0 * (1 - depth / 0.07)
            # Tui oi: vung toi
            es = ((x - sac_cx) / sac_rx) ** 2 + ((y - sac_cy) / sac_ry) ** 2
            if es < 1.0:
                val *= 0.18 + 0.10 * rng.random()
            # So thai: vanh xuong sang
            hd = math.hypot((x - head_cx), (y - head_cy))
            if abs(hd - head_r) < 2.2:
                val = 210 + rng.uniform(-25, 35)
            elif hd < head_r:                                   # nhu mo (mid-gray)
                val = max(val, 55 + rng.uniform(-18, 30))
                if abs(x - head_cx) < 1.6:                      # duong giua
                    val = 180 + rng.uniform(-20, 25)
            buf[y * w + x] = max(0, min(255, int(val)))
    return w, h, base64.b64encode(bytes(buf)).decode("ascii")


# ---------------------------------------------------------------------
# DU LIEU THO: SONG AM TIM (envelope S1/S2) cho ong nghe
# ---------------------------------------------------------------------
def _heart_audio_envelope(duration_s=15.0, npts=360, hr=72, seed=11):
    rng = random.Random(seed)
    rr = 60.0 / hr
    out = []
    for i in range(npts):
        tt = i / npts * duration_s
        phase = tt % rr
        a = 0.0
        a += 100 * math.exp(-((phase - 0.02) ** 2) / (2 * 0.018 ** 2))   # S1 (lub)
        a += 70 * math.exp(-((phase - 0.32) ** 2) / (2 * 0.016 ** 2))    # S2 (dub)
        a += rng.uniform(0, 6)
        out.append(int(min(100, a)))
    period_ms = round(duration_s * 1000 / npts)
    return out, period_ms, npts


def build_all():
    out = {}

    # 1) BP-01
    d = reg.DEVICES["BP-01"]
    out["bp01"] = C.build_envelope(
        "BP-01", "observation.vitals",
        ts("2026-10-20T08:52:00.000+07:00", "2026-10-20T08:52:00.420+07:00", "2026-10-20T08:52:01.050+07:00"),
        [
            C.meas_panel(d["panel"], d["components"],
                         {"systolic": 122, "diastolic": 77, "map": 92},
                         device_flags={"cuff_loose": False, "motion_detected": False}),
            C.meas_numeric(d["extra"][0], 72),
        ],
        sequence_no=10234, message_id="7b3f2c10-9a4e-4f2b-8c1d-0a1b2c3d4e5f")

    # 2) SPO-02
    d = reg.DEVICES["SPO-02"]
    sp = out["spo02"] = C.build_envelope(
        "SPO-02", "observation.vitals",
        ts("2026-10-20T08:54:00.000+07:00", "2026-10-20T08:54:00.300+07:00", "2026-10-20T08:54:00.900+07:00"),
        [
            C.meas_numeric(d["measurements"][0], 96),
            C.meas_numeric(d["measurements"][1], 74),
            C.meas_numeric(d["measurements"][2], 2.4),
        ],
        sequence_no=10235, message_id="9c4d1e22-1b5f-4a7c-9d2e-1b2c3d4e5f60")
    sp["measurements"][0]["device_flags"] = {"motion_detected": False}

    # 3) TMP-07
    d = reg.DEVICES["TMP-07"]
    tm = out["tmp07"] = C.build_envelope(
        "TMP-07", "observation.vitals",
        ts("2026-10-20T08:50:00.000+07:00", "2026-10-20T08:50:00.250+07:00", "2026-10-20T08:50:00.800+07:00"),
        [C.meas_numeric(d["measurements"][0], 37.3)],
        sequence_no=10236, message_id="a1b2c3d4-2c6f-4b8d-ae3f-2c3d4e5f6071")
    tm["measurements"][0]["body_site"] = None

    # 4) WGT-09
    d = reg.DEVICES["WGT-09"]
    out["wgt09"] = C.build_envelope(
        "WGT-09", "observation.vitals",
        ts("2026-10-20T08:48:00.000+07:00", "2026-10-20T08:48:00.200+07:00", "2026-10-20T08:48:00.700+07:00"),
        [C.meas_numeric(d["measurements"][0], 64.3)],
        sequence_no=10237, message_id="b2c3d4e5-3d70-4c9e-bf40-3d4e5f607182")

    # 5) LAB-05
    d = reg.DEVICES["LAB-05"]
    vals = {"alt": 28, "ast": 24, "ggt": 30, "bilirubin": 0.8, "glucose_plasma": 114}
    lab_meas = []
    for spec in d["measurements"]:
        mm = C.meas_numeric(spec, vals[spec["key"]])
        mm["quality"] = {"signal_quality": None, "confidence": None}
        lab_meas.append(mm)
    out["lab05"] = C.build_envelope(
        "LAB-05", "observation.lab",
        ts("2026-10-20T09:02:00.000+07:00", "2026-10-20T09:02:05.000+07:00", "2026-10-20T09:02:06.000+07:00"),
        lab_meas, sequence_no=10238, message_id="c3d4e5f6-4e81-4daf-c051-4e5f60718293")

    # 6) ECG-03 — waveform: mau tin hieu THO day du (PQRST, 500Hz) + HR
    d = reg.DEVICES["ECG-03"]
    ecg_adc, ecg_n = _ecg_samples(duration_s=2.5, fs=500, hr=72)
    sampled = {
        "lead": "II", "origin_value": 0, "unit": "mV", "period_ms": 2,
        "frequency_hz": 500, "factor": 0.001, "dimensions": 1,
        "sample_count": ecg_n, "truncated": False,
        "data": " ".join(str(v) for v in ecg_adc),
    }
    out["ecg03"] = C.build_envelope(
        "ECG-03", "observation.waveform",
        ts("2026-10-20T08:56:00.000+07:00", "2026-10-20T08:56:00.600+07:00", "2026-10-20T08:56:01.200+07:00"),
        [C.meas_waveform(d["waveform"], sampled), C.meas_numeric(d["extra"][0], 72)],
        sequence_no=10239, message_id="d4e5f607-5f92-4ab0-9162-5f6071829304")

    # 7) CAM-04 — media.video
    d = reg.DEVICES["CAM-04"]
    out["cam04"] = C.build_envelope(
        "CAM-04", "media.video",
        ts("2026-10-20T08:58:00.000+07:00", "2026-10-20T08:58:02.000+07:00", "2026-10-20T08:58:03.000+07:00"),
        [C.meas_media(d["media"]["code"], {
            "content_type": "video/mp4",
            "url": "s3://clinic001-media/CLINIC001/BN-2026-000123/CAM-04/clip-10240.mp4",
            "size_bytes": 10485760, "duration_sec": 12.0,
            "width": 1280, "height": 720, "frames": 360,
            "sha256": "2c26b46b68ffc68ff99b453c1d30413413422d706483bfa0f98a5e886266e7ae",
        })],
        sequence_no=10240, message_id="e5f60718-6093-4bc1-a273-60718293a415")

    # 8) ECH-06 — imaging.study: DU LIEU DIEM ANH THO (gray8 sector) + metadata DICOM
    uw, uh, udata = _ultrasound_gray8()
    out["ech06"] = C.build_envelope(
        "ECH-06", "imaging.study",
        ts("2026-10-20T09:10:00.000+07:00", "2026-10-20T09:10:03.000+07:00", "2026-10-20T09:10:04.000+07:00"),
        [C.meas_raster(
            {"system": "LOCAL", "code": "us-frame-raw", "display": "Ultrasound frame (raw gray8)", "verify": True},
            raster={
                "pixel_format": "gray8", "width": uw, "height": uh,
                "encoding": "base64", "geometry": "sector", "depth_cm": 12,
                "frame_index": 0, "frame_count": 1, "data": udata,
            },
            media={"content_type": "application/dicom", "modality": "US",
                   "url": "dicomweb:https://clinic001.example.vn/dicomweb/studies/1.2.826.0.1.3680043.8.498.100",
                   "number_of_series": 1, "number_of_instances": 24, "body_site": "Abdomen"})],
        sequence_no=10241, message_id="f6071829-71a4-4cd2-b384-718293a4b526")

    # 9) STE-08 — media.audio (nghe tim) + duong bao song am THO de ve do thi
    d = reg.DEVICES["STE-08"]
    env, env_period, env_n = _heart_audio_envelope(duration_s=15.0, npts=360, hr=72)
    out["ste08"] = C.build_envelope(
        "STE-08", "media.audio",
        ts("2026-10-20T08:57:00.000+07:00", "2026-10-20T08:57:01.000+07:00", "2026-10-20T08:57:02.000+07:00"),
        [C.meas_media(d["media"]["code"], {
            "content_type": "audio/wav",
            "url": "s3://clinic001-media/CLINIC001/BN-2026-000123/STE-08/auscultation-10242.wav",
            "size_bytes": 1323000, "duration_sec": 15.0,
            "body_site": "Precordium",
            "sha256": "ef2d127de37b942baad06145e54b0c619a1f22327b2ebbcfbec78f5564afe39d",
        }, sampled={
            "unit": "1", "origin_value": 0, "period_ms": env_period, "factor": 1,
            "dimensions": 1, "sample_count": env_n, "truncated": False,
            "data": " ".join(str(v) for v in env),
        })],
        sequence_no=10242, message_id="07182930-82b5-4de3-8495-8293a4b5c637")

    # 10) GLU-10 — glucose mao mach 41653-7
    d = reg.DEVICES["GLU-10"]
    gl = C.meas_numeric(d["measurements"][0], 98)
    gl["method"] = "fingerstick [CAN XAC MINH]"
    out["glu10"] = C.build_envelope(
        "GLU-10", "observation.lab",
        ts("2026-10-20T08:47:00.000+07:00", "2026-10-20T08:47:00.500+07:00", "2026-10-20T08:47:01.000+07:00"),
        [gl], sequence_no=10243, message_id="18293041-93c6-4ef4-95a6-93a4b5c6d748")

    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    payloads = build_all()
    for name, payload in payloads.items():
        path = os.path.join(OUT, f"{name}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        print(f"  wrote {path}")
    print(f"=> {len(payloads)} payload MQTT.")


if __name__ == "__main__":
    main()
