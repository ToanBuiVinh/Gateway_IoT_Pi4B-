# Thiết kế âm thanh ống nghe điện tử (Auscultation)

Trả lời cho: nghe trực tiếp vs lưu hồ sơ; bảo toàn chất lượng âm tim/phổi.

---

## 1. Hai trường hợp (tách rõ, như bạn nêu)

| Trường hợp | Mục tiêu | Giải pháp |
|---|---|---|
| **Nghe trực tiếp (live)** | Bác sĩ nghe real-time | **Audio streaming độ trễ thấp** (WebRTC/RTP), ưu tiên độ trễ |
| **Lưu hồ sơ / phân tích** | Nghe lại, phân tích, AI | **File WAV/FLAC lossless, RAW (không lọc)** để bảo toàn tín hiệu gốc |

Cả hai đi **ngoài MQTT** (data plane). MQTT chỉ mang một bản tin `observation.audio`
nhỏ (control plane): tham chiếu file đã lưu + endpoint live — **không nhồi audio vào MQTT**.

```
             DATA PLANE (âm thanh)                          CONTROL PLANE (metadata)
Ống nghe ─live(WebRTC/RTP)──► Bác sĩ nghe real-time
        └─record(WAV/FLAC)──► Object storage (S3)   Gateway ─observation.audio(MQTT)─► Cloud/PIH
                                     ▲                                                   │
                                     └──────────── tải file khi cần nghe lại ◄───────────┘
```

## 2. Bảo toàn chất lượng — nguyên tắc bắt buộc

Âm tim và âm phổi mang thông tin ở dải tần quan trọng; **nén mất dữ liệu (lossy) hoặc
lọc sai có thể xoá mất murmur, ran, wheeze**. Vì vậy:

- **File lưu = LOSSLESS**: WAV PCM (`pcm_s16le`/`pcm_s24le`) hoặc **FLAC** (nén *không mất
  dữ liệu*, giảm ~40-60% dung lượng mà vẫn khôi phục bit-chính-xác). **Không** dùng
  MP3/AAC/Opus cho bản lưu chẩn đoán.
- **RAW, không lọc** (`filter_mode: raw`): giữ nguyên tín hiệu ADC. Việc lọc (ví dụ dải
  tim 20–200 Hz, dải phổi 100–2000 Hz) là **bước xử lý/hiển thị ở phía sau**, làm trên
  **bản sao**, không ghi đè bản gốc.
- **Lấy mẫu đủ**: khuyến nghị **≥ 4 kHz** (bắt được tới ~2 kHz cho âm phổi; mẫu v2.1 dùng
  **8 kHz / 16-bit / mono**). Ghi rõ `sample_rate_hz`, `bit_depth`, `channels` để phía
  sau tái tạo đúng.
- **Toàn vẹn**: `storage.sha256` để kiểm tra file không hỏng khi tải lại.
- **Live** có thể dùng codec độ trễ thấp (Opus bitrate cao, hoặc PCM qua LAN) — chấp
  nhận cho *nghe tức thời*; nhưng **bản chẩ​n đoán luôn là file lossless** ở trên.

## 3. Tầng dưới — thiết bị / "dưới mạch"
- MEMS mic / piezo → ADC (≥16-bit, ≥4 kHz). Firmware **không lọc/nén mất dữ liệu**.
- **Record**: ghi WAV/FLAC, tính sha256, **upload qua HTTP/S3** (bulk, không MQTT) → lấy URL.
- **Live**: mở phiên **WebRTC/RTP** tới gateway/cloud (SRTP), độ trễ mục tiêu ~150–250 ms.
- Gắn `body_site` (vị trí nghe: mỏm tim/van 2 lá, đáy phổi…), thời điểm đo.
- Gateway publish `observation.audio` (tham chiếu file + live endpoint).

## 4. Tầng Application — Cloud / PIH
- Nhận `observation.audio` → biết có bản ghi mới cho bệnh nhân/encounter.
- **Nghe lại**: tải file WAV/FLAC từ `storage.url`, phát nguyên bản; lọc/khử nhiễu/vẽ
  phonocardiogram-spectrogram **trên bản sao** để phân tích.
- **Nghe trực tiếp**: kết nối `live.endpoint` (WebRTC) khi bác sĩ bấm "nghe".
- AI phân tích (murmur, ran…) chạy trên **file lossless gốc**.

## 5. Bản tin `observation.audio` (đã thêm vào schema)

```jsonc
{
  "message_type": "observation.audio",
  "source": { "source_type": "auscultation_device", ... },
  "patient_context": { ... },                      // patient_id KHÔNG vào topic (rule #10)
  "payload": {
    "recording": {
      "recording_id": "STE-001-REC-000108",
      "modality": "auscultation",
      "format": "wav", "codec": "pcm_s16le",
      "sample_rate_hz": 8000, "bit_depth": 16, "channels": 1,
      "duration_sec": 15.0, "lossless": true       // ⬅ bản lưu LUÔN lossless
    },
    "acquisition": { "body_site": "mitral (heart apex)", "filter_mode": "raw", "gain_db": 0 },
    "storage": { "type": "s3", "url": "s3://.../STE-001-REC-000108.wav",
                 "sha256": "...", "size_bytes": 240000 },   // tham chiếu, không nhồi audio
    "live": { "enabled": true, "protocol": "webrtc",
              "endpoint": "wss://media.pavalife.com/live/ste-001",
              "codec": "opus", "latency_target_ms": 200 }    // nghe trực tiếp độ trễ thấp
  }
}
```
Test `test_contract.py` kiểm tra: `recording.lossless == true`, `format ∈ {wav,flac}`,
và có `storage.url` (tham chiếu, không nhồi audio vào MQTT).

## 6. Cần PavaLife xác nhận
- Dải tần & tần số lấy mẫu chuẩn cho âm tim vs âm phổi (4 kHz vs 8 kHz).
- Bộ lọc hiển thị (nếu có) áp **sau**, không đụng bản gốc.
- Hạ tầng streaming live (WebRTC SFU/TURN) + mã hoá SRTP.
- Chính sách lưu trữ audio (mã hoá at-rest, thời hạn, nhật ký truy cập).
