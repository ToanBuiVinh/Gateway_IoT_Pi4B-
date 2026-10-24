# Báo cáo tham khảo — PavaLife Gateway (Device Data Contract v2.1)

> Tham chiếu tài liệu đính kèm: **`PVL_Device_Data_Contract_v2.1_6thietbi.docx`**
> (Contract v2.1 · DRAFT FOR REVIEW · 2026-10-21 · MQTT 5.0 over WSS · JSON Schema 2020-12).
> Broker: `wss://mqtt-hn-n1.pavalife.com:443/mqtt` · Topic: `pvl/v2/gw/GW-ROBOT-DEV-001/up/{message_type}`.

Báo cáo gồm 3 phần theo yêu cầu:
1. [Cách chạy từng file](#1-cách-chạy--từng-file)
2. [Cơ chế hoạt động: ống nghe điện tử & máy siêu âm](#2-cơ-chế-hoạt-động)
3. [Kết nối broker bên ngoài](#3-kết-nối-broker-bên-ngoài)

---

## 1. Cách chạy — từng file

Mã nguồn hiện thực đúng contract v2.1: 6 thiết bị lõi (huyết áp, SpO2, nhiệt kế, cân, xét
nghiệm axit uric, đường huyết) + mở rộng **siêu âm** (`imaging.study`) và **ống nghe**
(`observation.audio`) + `device.status` (Phụ lục A).

**Bước 0 — cài phụ thuộc:** `pip install -r requirements.txt` (jsonschema + paho-mqtt).

| # | Lệnh | File | Chức năng |
|---|---|---|---|
| 1 | `python tools/gen_samples.py` | `tools/gen_samples.py` | Sinh bản tin JSON mẫu đúng schema |
| 2 | `python tests/test_contract.py` | `tests/test_contract.py` | Validate schema 2020-12 + rule #7/#8/#10 |
| 3 | `python tools/gen_viewer.py` | `tools/gen_viewer.py` | Sinh dashboard tĩnh `viewer/index.html` |
| 4 | `python pvl_send.py <kind>` | `pvl_send.py` | In 1 bản tin ra màn hình (không gửi) |
| 5 | `python pvl_send.py <kind> --local --publish` | `pvl_send.py` + `gateway/publisher.py` | Gửi thật lên broker cục bộ |
| 6 | `python tools/pvl_subscribe.py` | `tools/pvl_subscribe.py` | Nghe & in bản tin (terminal) |
| 7 | `python tools/web_viewer.py` | `tools/web_viewer.py` | Xem LIVE trên trang HTML `http://localhost:8080` |
| 8 | `python audio/record_and_publish.py` | `audio/record_and_publish.py` | Pipeline ống nghe: WAV→FLAC lossless→(publish) |
| 9 | `python imaging/wrap_and_publish.py --stow` | `imaging/wrap_and_publish.py` | Ảnh siêu âm → DICOM → PACS → `imaging.study` |

`<kind>` ∈ `vitals · lab · imaging · audio · status · all`.

**Chạy thử cục bộ không cần gì (Windows):**
```powershell
pip install -r requirements.txt
cd local-test & start_mini_broker.bat     REM broker thuần Python
python tools\web_viewer.py                 REM cửa sổ khác -> mở http://localhost:8080
python pvl_send.py all --local --publish   REM cửa sổ khác -> thấy bản tin chạy vào
```
Chi tiết: [`../local-test/README.md`](../local-test/README.md).

---

## 2. Cơ chế hoạt động

Nguyên tắc chung cho **cả hai** thiết bị tạo dữ liệu lớn: **tách Control plane và Data plane**.
MQTT là *control plane* (bản tin nhỏ vài KB) — **không** nhồi audio/ảnh vào MQTT; dữ liệu
nặng đi *data plane* riêng (HTTP/DICOMweb/object storage/WebRTC). Bản tin MQTT chỉ mang
**tham chiếu**.

### 2.1 Ống nghe điện tử (auscultation) — `observation.audio`

**Luồng tín hiệu:**
```
Âm tim/phổi ─► [màng/piezo hoặc MEMS mic] ─► tín hiệu điện ─► [ADC ≥16-bit, ≥4kHz]
                                                                      │  (firmware KHÔNG lọc/nén mất dữ liệu — giữ RAW)
                       ┌──────────────────────────────────────────────┴───────────────┐
         LIVE (nghe ngay)                                          RECORD (lưu hồ sơ)
   đóng gói realtime ─► WebRTC/RTP (SRTP) ─► bác sĩ nghe       ghi WAV/FLAC *lossless, raw*
   codec Opus · độ trễ ~150–250 ms                            ─► sha256 ─► upload HTTP/S3 ─► URL
                       └──────────────────────────────┬───────────────────────────────┘
                                          Gateway publish observation.audio (MQTT, control plane)
                                          = metadata + tham chiếu file + live endpoint (KHÔNG có audio)
                                                       │
                                       Cloud/PIH: nghe lại (tải storage.url) | nghe trực tiếp (live.endpoint)
```

**Hai chế độ (bắt buộc tách rõ):**
- **Nghe trực tiếp (live):** độ trễ thấp là ưu tiên → **WebRTC/RTP**, chấp nhận codec nén
  cho nghe tức thời.
- **Lưu hồ sơ / phân tích:** chất lượng là ưu tiên → **file WAV/FLAC lossless, RAW (không
  lọc)**. Lý do: âm tim/phổi (murmur, ran, wheeze) nằm ở dải tần quan trọng; **nén mất dữ
  liệu (MP3/AAC/Opus) hoặc lọc sai sẽ xoá mất thông tin chẩn đoán**. Việc lọc/khử nhiễu/vẽ
  phonocardiogram là bước xử lý **trên bản sao**, không đụng bản gốc.

**Đã kiểm chứng thật** (`audio/record_and_publish.py`): WAV 192,044 B → **FLAC 139,337 B**
(giảm 27.4%) và **bit-exact** (giải mã FLAC == WAV gốc) → lossless đúng nghĩa. Bản tin
`observation.audio` mang `recording.lossless=true`, `storage.{url,sha256,size_bytes}`,
`live.{protocol,endpoint,codec,latency_target_ms}`. Chi tiết: [`AUDIO_DESIGN.md`](AUDIO_DESIGN.md).

### 2.2 Máy siêu âm (ultrasound) — `imaging.study`

**Vật lý tạo ảnh:** đầu dò (transducer) phát sóng **siêu âm** bằng tinh thể áp điện; sóng
phản xạ từ ranh giới các mô quay lại đầu dò; đo **thời gian về + cường độ phản xạ** để dựng
mỗi điểm sáng → ảnh **B-mode** (brightness) 2D. Nhiều khung liên tiếp = **cine loop** (đoạn
video siêu âm).

**Luồng dữ liệu (tách control/data plane):**
```
                 DATA PLANE (ảnh LỚN — HTTP)                       CONTROL PLANE (nhỏ — MQTT)
[Máy siêu âm] ──DICOM STOW-RS / C-STORE──► [PACS / object store]   [Gateway] ──imaging.study──► [Cloud/PIH]
      │ (hoặc đầu dò raw → gateway ghép & đóng gói DICOM)   ▲                                      │
      └──────────────────────────────────────────────────────┘                                   ▼
                                           [Cloud/PIH] ──WADO-RS GET (lazy)──► tải & hiển thị ảnh
```

**Hai kịch bản phần cứng:**
- **3A — máy US thương mại (tự xuất DICOM):** gateway chỉ **relay** (đóng vai DICOM
  C-STORE SCP) → chuyển tiếp lên PACS qua **STOW-RS** → publish `imaging.study`. Không đụng pixel.
- **3B — đầu dò/SoC chỉ xuất RAW pixel:** đầu dò số hoá B-mode + nén nhẹ, truyền lên gateway
  bằng kênh **bulk tin cậy (TCP/HTTP/WebSocket, có checksum/resume) — KHÔNG dùng MQTT**;
  gateway ghép khung → **đóng gói DICOM** (pydicom, US Image / Multi-frame IOD) → STOW-RS → publish.

**Vì sao không nhồi pixel vào MQTT:** một cine loop vài chục–vài trăm MB sẽ làm phình payload
(base64 +33%), nghẽn broker, chặn hàng đợi vitals/alarm. Nên MQTT chỉ mang `imaging.study`
nhỏ: `study.study_instance_uid`, `storage.wado_rs_study` (nơi lấy ảnh) — **không có pixel**.

**Nếu chỉ có RAW pixel — phải thống nhất 4 điểm:** `pixel_format` (gray8/gray16 LE), **kích
thước** `width×height` cố định cả loạt, **thứ tự frame** (row-major, gốc trên-trái, frame_index
tăng dần), **toàn vẹn** (`len == width×height×bytes×frames` + sha256).

**Đã kiểm chứng thật** trên Orthanc (`imaging/wrap_and_publish.py`): đóng gói cine 8 khung →
STOW-RS lên PACS → QIDO-RS liệt kê study (US) → WADO-RS render khung ra ảnh. Chi tiết:
[`IMAGING_DESIGN.md`](IMAGING_DESIGN.md).

---

## 3. Kết nối broker bên ngoài

Để chuyển từ broker test cục bộ sang **broker thật** (PavaLife `wss://…:443/mqtt`, hoặc broker
bên thứ ba), xem hướng dẫn đầy đủ: **[`EXTERNAL_BROKER.md`](EXTERNAL_BROKER.md)**. Tóm tắt:

**Cần xin bên vận hành broker:** URL+cổng+scheme, giao thức (MQTT 5), **xác thực**
(username/password hoặc mTLS hoặc token), **CA cert** (nếu CA nội bộ), **client_id**, **ACL
topic** (được publish `pvl/v2/gw/<gateway_id>/up/#`), giới hạn kích thước/QoS/rate.

**Gửi lên broker ngoài (code đã sẵn sàng):**
```bash
python pvl_send.py all \
  --broker "wss://mqtt-hn-n1.pavalife.com:443/mqtt" --mqtt-version 5 \
  --username "GW-ROBOT-DEV-001" --password "<cấp-bởi-PavaLife>" \
  --ca-cert pavalife-ca.pem \
  --publish
```
`gateway/publisher.py` tự suy ra TLS + WebSocket từ scheme `wss://`. Bản tin **đầu tiên nên
là `device.status`** (Phụ lục A: "bản tin kiểm thử kết nối đầu tiên") để xác nhận đường thông.

**Khuyến nghị production:** QoS 1 (khử trùng bằng `message_id` — rule #2); `sequence_no` tăng
dần kể cả sau reconnect (rule #3); LWT `device.status=offline`; store-and-forward khi mất mạng;
**TLS bật, bí mật trong secret manager (không hardcode/commit)**; `patient_id` **không** vào
topic/log (rule #10). Payload lớn (ảnh/audio) **không** qua broker.

---

## 4. Cần PavaLife xác nhận (Phụ lục C)
- Endpoint broker/PACS/storage thật + cơ chế xác thực (token/mTLS/username-password) + CA.
- ACL topic & client_id cấp cho gateway; giới hạn kích thước/QoS/rate.
- Mã LOINC/SNOMED còn treo (axit uric mao mạch, SpO2 2708-6 vs 59408-5, đói/no đường huyết).
- OID gốc cấp cho PavaLife để sinh UID DICOM hợp lệ; transfer syntax/nén cine.
- Tần số lấy mẫu & dải lọc chuẩn cho âm tim vs âm phổi; hạ tầng WebRTC (SFU/TURN, SRTP).
- Chính sách lưu trữ (mã hoá at-rest, thời hạn, nhật ký truy cập) cho audio & ảnh.
