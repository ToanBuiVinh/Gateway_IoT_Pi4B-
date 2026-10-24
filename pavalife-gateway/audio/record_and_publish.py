"""record_and_publish.py — đường LƯU HỒ SƠ ống nghe: synth -> WAV -> FLAC lossless -> publish.

Minh hoa "server -> publish" cho observation.audio:
  1) Tổng hợp tín hiệu nghe tim (S1/S2) — int16 PCM, mono.
  2) Ghi WAV (gốc) rồi nén FLAC **lossless** (flac CLI).
  3) Kiểm chứng lossless: giải mã FLAC -> so khớp PCM với WAV gốc (bit-exact).
  4) (coi object storage = thư mục local) tính sha256 + size thật.
  5) Dựng bản tin observation.audio (format=flac) và (tuỳ chọn) publish lên broker.

Chạy:
    python audio/record_and_publish.py                     # tạo FLAC + summary.json
    python audio/record_and_publish.py --publish --local   # publish len mqtt://localhost:1883
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import wave

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gateway import contract as C      # noqa: E402
from gateway import registry as reg    # noqa: E402


def synth_auscultation(duration_s: float, fs: int, hr: int = 72, seed: int = 3):
    """Sinh tin hieu nghe tim int16: S1 ('lub') + S2 ('dub') moi chu ky + nhieu nhe."""
    rng = random.Random(seed)
    n = int(duration_s * fs)
    rr = 60.0 / hr
    out = []
    for i in range(n):
        t = i / fs
        ph = t % rr
        # S1 ~ 40-150 Hz, S2 ~ 50-120 Hz (burst co envelope Gauss)
        s1 = math.exp(-((ph - 0.04) ** 2) / (2 * 0.018 ** 2)) * math.sin(2 * math.pi * 55 * ph)
        s2 = 0.7 * math.exp(-((ph - 0.34) ** 2) / (2 * 0.016 ** 2)) * math.sin(2 * math.pi * 75 * ph)
        v = 0.6 * (s1 + s2) + rng.uniform(-0.02, 0.02)
        out.append(max(-32768, min(32767, int(v * 30000))))
    return out


def write_wav(path: str, samples, fs: int):
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)   # 16-bit
        w.setframerate(fs)
        w.writeframes(b"".join(int(s).to_bytes(2, "little", signed=True) for s in samples))


def pcm_of_wav(path: str) -> bytes:
    with wave.open(path, "rb") as w:
        return w.readframes(w.getnframes())


def encode_flac(wav_path: str, flac_path: str):
    subprocess.run(["flac", "--silent", "--best", "-f", "-o", flac_path, wav_path], check=True)


def verify_lossless(wav_path: str, flac_path: str, tmp_wav: str) -> bool:
    subprocess.run(["flac", "--silent", "-d", "-f", "-o", tmp_wav, flac_path], check=True)
    return pcm_of_wav(wav_path) == pcm_of_wav(tmp_wav)


def envelope(samples, points=400):
    """Rut gon tin hieu thanh |peak| tung cua so de ve dang song."""
    step = max(1, len(samples) // points)
    env = []
    for i in range(0, len(samples), step):
        chunk = samples[i:i + step]
        env.append(max(abs(x) for x in chunk) if chunk else 0)
    return env


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--duration", type=float, default=12.0)
    ap.add_argument("--fs", type=int, default=8000)
    ap.add_argument("--hr", type=int, default=72)
    ap.add_argument("--out", default=os.path.join(ROOT, "audio", "out"))
    ap.add_argument("--publish", action="store_true")
    ap.add_argument("--local", action="store_true")
    ap.add_argument("--broker", default=reg.BROKER_URL)
    args = ap.parse_args()
    if args.local:
        args.broker = "mqtt://localhost:1883"
    os.makedirs(args.out, exist_ok=True)

    steps = []
    # 1-2) synth + WAV + FLAC
    samples = synth_auscultation(args.duration, args.fs, args.hr)
    wav_path = os.path.join(args.out, "auscultation.wav")
    flac_path = os.path.join(args.out, "auscultation.flac")
    tmp_wav = os.path.join(args.out, "_decoded.wav")
    write_wav(wav_path, samples, args.fs)
    encode_flac(wav_path, flac_path)
    wav_size = os.path.getsize(wav_path)
    flac_size = os.path.getsize(flac_path)
    steps.append({"step": "Tổng hợp tín hiệu nghe tim", "ok": True,
                  "detail": f"{len(samples)} mẫu · {args.fs} Hz · 16-bit mono · {args.duration:.0f}s · ~{args.hr} nhịp/phút"})
    steps.append({"step": "Ghi WAV (gốc, lossless PCM)", "ok": True, "detail": f"{wav_size:,} bytes"})
    steps.append({"step": "Nén FLAC (--best)", "ok": True,
                  "detail": f"{flac_size:,} bytes · tỉ lệ {flac_size/wav_size*100:.1f}% (giảm {(1-flac_size/wav_size)*100:.1f}%)"})

    # 3) verify lossless
    lossless = verify_lossless(wav_path, flac_path, tmp_wav)
    steps.append({"step": "Kiểm chứng LOSSLESS (giải mã FLAC == WAV gốc)", "ok": lossless,
                  "detail": "PCM bit-exact ✓" if lossless else "KHÁC NHAU ✗"})
    os.remove(tmp_wav)

    # 4) sha256 + 'object storage' = file local
    sha = hashlib.sha256(open(flac_path, "rb").read()).hexdigest()
    storage_url = f"{reg.AUDIO_STORAGE_BASE}/STE-001/auscultation.flac"
    steps.append({"step": "Lưu object storage (demo: file local)", "ok": True,
                  "detail": f"sha256={sha[:16]}…  url={storage_url}"})

    # 5) bản tin observation.audio (FLAC, lossless, kích thước & sha256 thật)
    et = dt.datetime.now(dt.timezone(dt.timedelta(hours=7))).isoformat(timespec="milliseconds")
    msg = C.build_audio_recording("stethoscope", et, fmt="flac", codec="flac",
                                  sample_rate_hz=args.fs, bit_depth=16, channels=1,
                                  duration_sec=args.duration)
    msg["payload"]["storage"].update({"url": storage_url, "sha256": sha, "size_bytes": flac_size})
    msg_path = os.path.join(args.out, "message.json")
    json.dump(msg, open(msg_path, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    published = False
    if args.publish:
        from gateway.publisher import PavaLifePublisher
        pub = PavaLifePublisher(args.broker, mqtt_version="311" if args.local else "5")
        pub.connect(); published = pub.publish(msg); pub.disconnect()
    steps.append({"step": "Publish observation.audio" + ("" if args.publish else " (bỏ qua --publish)"),
                  "ok": published or not args.publish,
                  "detail": (f"-> {reg.topic_for('observation.audio')}" if args.publish else "chưa gửi")})

    # summary cho report
    summary = {
        "generated_at": et, "device_id": "STE-001",
        "signal": {"fs": args.fs, "bit_depth": 16, "channels": 1, "duration_sec": args.duration,
                   "samples": len(samples)},
        "flac": {"wav_bytes": wav_size, "flac_bytes": flac_size,
                 "ratio_pct": round(flac_size / wav_size * 100, 1), "lossless": lossless, "sha256": sha},
        "envelope": envelope(samples), "env_max": 32768,
        "steps": steps, "message": msg, "topic": reg.topic_for("observation.audio"),
    }
    json.dump(summary, open(os.path.join(args.out, "summary.json"), "w", encoding="utf-8"), ensure_ascii=False)

    print("=== PIPELINE LƯU HỒ SƠ ỐNG NGHE ===")
    for s in steps:
        print(f"  [{'OK' if s['ok'] else 'FAIL'}] {s['step']}: {s['detail']}")
    print(f"  FLAC lossless: {lossless} | WAV {wav_size:,} -> FLAC {flac_size:,} bytes")
    print(f"  Files: {flac_path}  |  {msg_path}  |  summary.json")
    return 0 if lossless else 1


if __name__ == "__main__":
    raise SystemExit(main())
