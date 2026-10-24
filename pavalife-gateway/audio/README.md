# Audio — ống nghe điện tử (observation.audio)

Hai trường hợp theo đúng yêu cầu lâm sàng (xem thiết kế đầy đủ: [`../docs/AUDIO_DESIGN.md`](../docs/AUDIO_DESIGN.md)):

1. **Nghe trực tiếp** — bác sĩ cần nghe ngay → **audio streaming độ trễ thấp** (WebRTC/Opus,
   `live.latency_target_ms ≈ 200ms`). Chỉ để nghe thời gian thực, không dùng làm hồ sơ.
2. **Lưu hồ sơ** — nghe lại / phân tích → file **WAV/FLAC lossless, raw (không nén lossy,
   không lọc)** để **bảo toàn âm tim (S1/S2) và âm phổi**. Đây là đường mà script dưới minh hoạ.

> Audio **đi ngoài MQTT** (object storage / HTTP). Bản tin `observation.audio` chỉ mang
> **tham chiếu**: `storage.url`, `sha256`, `size_bytes`, cờ `lossless`, và khối `live`.

## `record_and_publish.py` — pipeline LƯU HỒ SƠ thật

```
synth tín hiệu nghe tim (S1/S2, int16 PCM)
  → ghi WAV (gốc, PCM lossless)
  → nén FLAC  (flac --best)                         ← nén THẬT
  → kiểm chứng LOSSLESS: giải mã FLAC == WAV gốc    ← so khớp PCM bit-exact
  → sha256 + size thật (coi object storage = file local)
  → dựng bản tin observation.audio (format=flac, lossless=true)
  → (tuỳ chọn) publish lên broker
```

```bash
pip install -r audio/requirements-audio.txt     # cần `flac` CLI trên PATH
# 1) tạo FLAC + kiểm chứng lossless + summary.json (KHÔNG gửi):
python audio/record_and_publish.py
# 2) gửi thật lên broker cục bộ (xem local-test/):
python audio/record_and_publish.py --publish --local
```

Kết quả chạy mẫu (12s, 8000 Hz, 16-bit mono):

| | bytes | tỉ lệ |
|---|---|---|
| WAV gốc (PCM) | 192,044 | 100% |
| **FLAC (--best)** | **139,337** | **72.6%** (giảm 27.4%) |
| LOSSLESS | — | giải mã == gốc, **bit-exact ✓** |

## `gen_report.py` — report xem trực quan

Đọc `audio/out/summary.json` (+ `delivery.json` nếu publish) → sinh `audio/report.html`
(một trang tĩnh, tự chứa): thẻ số liệu, stepper pipeline, **dạng sóng nghe tim**, panel so
sánh nén FLAC (ratio + cờ lossless + sha256), xác nhận nhận bản tin MQTT, và JSON
`observation.audio` đầy đủ.

```bash
python audio/gen_report.py            # -> audio/report.html (mở bằng trình duyệt)
```

> Thư mục `audio/out/` (WAV/FLAC + JSON trung gian) **được .gitignore**. `report.html`
> tự chứa dữ liệu nên commit được để xem lại.
