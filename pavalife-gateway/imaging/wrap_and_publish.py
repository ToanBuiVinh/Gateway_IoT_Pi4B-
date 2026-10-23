"""wrap_and_publish.py — đóng gói pixel siêu âm RAW -> DICOM -> Orthanc -> MQTT.

Minh hoa ĐẦY ĐỦ đường DICOM thật (data plane) + thông báo (control plane):
  1) Sinh/đọc khung ảnh gray8 (ở đây sinh procedural B-mode cho dễ test).
  2) Đóng gói DICOM US Image (pydicom, Explicit VR LE - không nén, không cần codec).
  3) (tuỳ chọn) STOW-RS lên Orthanc (data plane) -> lấy StudyInstanceUID thật.
  4) (tuỳ chọn) publish imaging.study lên broker CỤC BỘ (control plane, chỉ tham chiếu).

Chay (chi dong goi + luu .dcm, khong can dich vu):
    python imaging/wrap_and_publish.py
Chay day du (can Orthanc + Mosquitto cuc bo):
    python imaging/wrap_and_publish.py --stow --publish --local
"""
from __future__ import annotations

import argparse
import datetime as dt
import math
import os
import random
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gateway import contract as C      # noqa: E402
from gateway import registry as reg    # noqa: E402

US_SOP_CLASS = "1.2.840.10008.5.1.4.1.1.6.1"   # Ultrasound Image Storage


# ---- 1) Sinh khung ảnh gray8 (B-mode sector) ----
def ultrasound_frame(w=176, h=132, seed=7) -> bytes:
    rng = random.Random(seed)
    buf = bytearray(w * h)
    apex_x, apex_y = w / 2.0, -6.0
    half, rmin, rmax = math.radians(35), 8.0, math.hypot(w / 2.0, h) + 6.0
    scx, scy, srx, sry = w * 0.52, h * 0.56, w * 0.30, h * 0.30
    hcx, hcy, hr = w * 0.46, h * 0.52, h * 0.19
    for y in range(h):
        for x in range(w):
            dx, dy = x - apex_x, y - apex_y
            r = math.hypot(dx, dy)
            if abs(math.atan2(dx, dy)) > half or not (rmin <= r <= rmax):
                continue
            depth = (r - rmin) / (rmax - rmin)
            val = 120.0 * math.exp(-1.7 * depth) + 22.0
            val *= max(0.12, rng.gauss(1.0, 0.33))
            if depth < 0.07:
                val += 55.0 * (1 - depth / 0.07)
            if ((x - scx) / srx) ** 2 + ((y - scy) / sry) ** 2 < 1.0:
                val *= 0.18 + 0.10 * rng.random()
            hd = math.hypot(x - hcx, y - hcy)
            if abs(hd - hr) < 2.2:
                val = 210 + rng.uniform(-25, 35)
            elif hd < hr:
                val = max(val, 55 + rng.uniform(-18, 30))
                if abs(x - hcx) < 1.6:
                    val = 180 + rng.uniform(-20, 25)
            buf[y * w + x] = max(0, min(255, int(val)))
    return bytes(buf)


# ---- 2) Đóng gói DICOM ----
def make_us_dataset(frames: list[bytes], rows: int, cols: int, patient_id: str,
                    study_uid: str, series_uid: str):
    import pydicom
    from pydicom.dataset import FileDataset, FileMetaDataset
    from pydicom.uid import ExplicitVRLittleEndian, generate_uid

    sop_uid = generate_uid()
    fm = FileMetaDataset()
    fm.MediaStorageSOPClassUID = US_SOP_CLASS
    fm.MediaStorageSOPInstanceUID = sop_uid
    fm.TransferSyntaxUID = ExplicitVRLittleEndian
    fm.ImplementationClassUID = generate_uid()

    ds = FileDataset(None, {}, file_meta=fm, preamble=b"\x00" * 128)
    ds.is_little_endian = True
    ds.is_implicit_VR = False

    now = dt.datetime.now()
    ds.PatientName = "TEST^PAVALIFE"
    ds.PatientID = patient_id
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.SOPInstanceUID = sop_uid
    ds.SOPClassUID = US_SOP_CLASS
    ds.Modality = "US"
    ds.StudyDate = now.strftime("%Y%m%d")
    ds.StudyTime = now.strftime("%H%M%S")
    ds.AccessionNumber = "US-001-ACC"
    ds.Manufacturer = "PavaLife"
    ds.BodyPartExamined = "ABDOMEN"
    # Pixel
    ds.SamplesPerPixel = 1
    ds.PhotometricInterpretation = "MONOCHROME2"
    ds.Rows = rows
    ds.Columns = cols
    ds.BitsAllocated = 8
    ds.BitsStored = 8
    ds.HighBit = 7
    ds.PixelRepresentation = 0
    if len(frames) > 1:
        ds.NumberOfFrames = len(frames)
        ds.FrameIncrementPointer = pydicom.tag.Tag(0x0018, 0x1063)  # FrameTime
        ds.FrameTime = "40"  # ms/khung (~25 fps)
    ds.PixelData = b"".join(frames)
    return ds


# ---- 3) STOW-RS lên Orthanc ----
def stow(ds, dicomweb_url: str, orthanc_url: str, dcm_path: str) -> None:
    try:
        from dicomweb_client.api import DICOMwebClient
        client = DICOMwebClient(url=dicomweb_url)
        client.store_instances([ds])
        print(f"  STOW-RS OK -> {dicomweb_url}/studies")
    except ImportError:
        import requests
        with open(dcm_path, "rb") as f:
            r = requests.post(orthanc_url + "/instances", data=f.read(),
                              headers={"Content-Type": "application/dicom"}, timeout=30)
        r.raise_for_status()
        print(f"  Orthanc REST /instances OK (HTTP {r.status_code})")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--frames", type=int, default=1, help="so khung (>=2 = multi-frame/cine)")
    ap.add_argument("--out", default=os.path.join(ROOT, "imaging", "out"))
    ap.add_argument("--orthanc", default="http://localhost:8042")
    ap.add_argument("--dicomweb", default="http://localhost:8042/dicom-web")
    ap.add_argument("--stow", action="store_true", help="upload DICOM len Orthanc (STOW-RS)")
    ap.add_argument("--publish", action="store_true", help="publish imaging.study len broker")
    ap.add_argument("--local", action="store_true", help="broker cuc bo mqtt://localhost:1883")
    ap.add_argument("--broker", default=reg.BROKER_URL)
    args = ap.parse_args()
    if args.local:
        args.broker = "mqtt://localhost:1883"

    from pydicom.uid import generate_uid
    W, H = 176, 132
    frames = [ultrasound_frame(W, H, seed=7 + i) for i in range(max(1, args.frames))]
    study_uid, series_uid = generate_uid(), generate_uid()
    patient_id = "BN-TEST-000001"

    ds = make_us_dataset(frames, H, W, patient_id, study_uid, series_uid)
    os.makedirs(args.out, exist_ok=True)
    dcm_path = os.path.join(args.out, "us_study.dcm")
    ds.save_as(dcm_path)
    size = os.path.getsize(dcm_path)
    print(f"DICOM da tao: {dcm_path} ({size} bytes, {len(frames)} khung {W}x{H})")
    print(f"  StudyInstanceUID = {study_uid}")

    if args.stow:
        stow(ds, args.dicomweb, args.orthanc, dcm_path)

    # 4) Thong bao imaging.study (control plane) - tham chieu study that
    et = dt.datetime.now(dt.timezone(dt.timedelta(hours=7))).isoformat(timespec="milliseconds")
    msg = C.build_imaging_study("ultrasound", et, instances=len(frames))
    msg["payload"]["study"]["study_instance_uid"] = study_uid
    msg["payload"]["series"][0]["series_instance_uid"] = series_uid
    wado = f"{args.dicomweb}/studies/{study_uid}"
    msg["payload"]["storage"]["wado_rs_study"] = wado
    msg["payload"]["storage"]["stow_rs"] = f"{args.dicomweb}/studies"
    msg["payload"]["storage"]["thumbnail_url"] = f"{wado}/thumbnail"
    msg["payload"]["storage"]["size_bytes"] = size

    if args.publish:
        from gateway.publisher import PavaLifePublisher
        pub = PavaLifePublisher(args.broker)
        pub.connect()
        pub.publish(msg)
        pub.disconnect()
        print(f"  Da publish imaging.study -> {args.broker}  (WADO: {wado})")
    else:
        import json
        print("--- imaging.study (chua publish, dung --publish de gui) ---")
        print(json.dumps(msg, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
