"""verify_dicomweb.py — kiem tra Orthanc da nhan study (QIDO-RS) va lay lai anh (WADO).

Chay sau khi da STOW anh len Orthanc:
    python imaging/verify_dicomweb.py
    python imaging/verify_dicomweb.py --orthanc http://localhost:8042
In danh sach study (QIDO-RS) va luu 1 khung ra PNG qua Orthanc REST.
"""
from __future__ import annotations

import argparse
import os
import sys

import requests


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--orthanc", default="http://localhost:8042")
    ap.add_argument("--out", default=os.path.join(os.path.dirname(__file__), "out", "retrieved_frame.png"))
    args = ap.parse_args()
    base = args.orthanc.rstrip("/")
    s = requests.Session()
    s.trust_env = False   # bo qua HTTP(S)_PROXY cho localhost

    # QIDO-RS: liet ke study
    r = s.get(f"{base}/dicom-web/studies", timeout=15)
    r.raise_for_status()
    studies = r.json()
    print(f"QIDO-RS: {len(studies)} study tren Orthanc")
    for st in studies:
        uid = st.get("0020000D", {}).get("Value", ["?"])[0]
        mod = st.get("00080061", {}).get("Value", ["?"])
        ninst = st.get("00201208", {}).get("Value", ["?"])[0]
        print(f"  - {uid}  modalities={mod}  instances={ninst}")
    if not studies:
        print("Chua co study. Chay wrap_and_publish.py --stow truoc.")
        return 1

    # Lay 1 instance, render khung 0 -> PNG (chung minh WADO/REST lay anh duoc)
    iid = s.get(f"{base}/instances", timeout=15).json()[0]
    info = s.get(f"{base}/instances/{iid}", timeout=15).json()
    png = s.get(f"{base}/instances/{iid}/frames/0/preview", timeout=15)
    png.raise_for_status()
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "wb") as f:
        f.write(png.content)
    print(f"\nInstance {iid}: da luu khung 0 -> {args.out} ({len(png.content)} bytes)")
    print("Mo file PNG do, hoac xem truc tiep tai Orthanc Explorer:", base)
    return 0


if __name__ == "__main__":
    sys.exit(main())
