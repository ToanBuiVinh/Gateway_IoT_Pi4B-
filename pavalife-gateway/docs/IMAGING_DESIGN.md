# Thiết kế gửi ảnh siêu âm (Imaging) — DICOM

Trả lời cho: *gửi ảnh siêu âm lên như thế nào? Dùng DICOM? Lập trình ở tầng dưới
(thiết bị) và tầng Application ra sao?*

---

## 1. Nguyên tắc cốt lõi: tách Control plane và Data plane

Ảnh siêu âm **rất lớn** so với số đo (một ảnh B-mode JPEG ~0.2–2 MB, một **cine
loop** vài chục–vài trăm MB). **KHÔNG nhồi pixel vào MQTT** vì:

- MQTT là control plane, bản tin nên nhỏ (vài KB). Broker thường giới hạn kích thước
  (`message_size_limit`), QoS/retry với payload lớn gây nghẽn, trùng lặp tốn băng thông.
- Nhồi base64 làm phình 33%, chặn hàng đợi các bản tin vitals/alarm quan trọng.

👉 **Giải pháp chuẩn:** 2 mặt phẳng tách biệt.

```
                 DATA PLANE (ảnh lớn, HTTP)                         CONTROL PLANE (metadata nhỏ, MQTT)
  [Máy siêu âm] ──DICOM STOW-RS / C-STORE──► [PACS / Object store]   [Gateway] ──imaging.study──► [Cloud/PIH]
       │  (hoặc đầu dò raw -> Gateway đóng gói DICOM)      ▲                                   │
       └───────────────────────────────────────────────────┘                                  ▼
                                                   [Cloud/PIH] ──WADO-RS GET──► lấy & hiển thị ảnh
```

- **Data plane:** ảnh (DICOM) đi thẳng từ thiết bị/gateway lên **PACS** hoặc **object
  storage** qua HTTP (**DICOMweb STOW-RS**) hoặc DICOM cổ điển (**C-STORE/DIMSE**).
- **Control plane:** gateway chỉ publish một bản tin MQTT **`imaging.study`** nhỏ, chứa
  **định danh + đường dẫn** (StudyInstanceUID, WADO-RS URL), **không có pixel**.
- **Application** nhận thông báo → **GET ảnh qua WADO-RS** khi cần hiển thị.

---

## 2. Có nên dùng DICOM? — Có.

DICOM là chuẩn de-facto cho ảnh y tế. Lý do:

| Tiêu chí | Vì sao DICOM |
|---|---|
| Tương thích | PACS, máy siêu âm, viewer (OHIF, Weasis), PIH/HIS đều nói DICOM. |
| Metadata gắn liền ảnh | Patient/Study/Series/Instance UID, modality, probe, depth, gain, khung hình, pixel spacing… nằm trong chính file. |
| Multi-frame / cine | US Multi-frame Image IOD lưu cả đoạn cine, kèm frame rate. |
| Truyền tải web | **DICOMweb** (STOW-RS gửi, WADO-RS lấy, QIDO-RS truy vấn) chạy trên HTTPS — hợp với gateway + cloud. |
| Nén | Transfer syntax JPEG Baseline / JPEG 2000 / **HEVC** cho cine, giảm dung lượng. |

**Khi nào KHÔNG cần DICOM đầy đủ:** nếu chỉ cần ảnh tham khảo nhanh (telemedicine, lưu
JPEG/MP4 vào object storage) có thể bỏ qua PACS. Nhưng để vào PIH/bệnh án thì nên DICOM.
Thiết kế dưới đây hỗ trợ **cả hai** qua `storage.type` (`dicomweb` | `s3` | `pacs` | `dimse`).

---

## 3. Tầng dưới — Thiết bị / "dưới mạch" (lập trình)

Có 2 kịch bản tuỳ phần cứng:

### 3A. Máy siêu âm thương mại (đã có DICOM)
Hầu hết máy US lâm sàng tự xuất DICOM. Gateway chỉ làm **cầu/relay**, không đụng pixel:
1. Cấu hình máy US gửi ảnh tới gateway (đóng vai **DICOM C-STORE SCP**) hoặc thẳng tới PACS.
2. Gateway chuyển tiếp lên **PACS qua STOW-RS** (hoặc C-STORE), lấy được `StudyInstanceUID`.
3. Gateway **publish `imaging.study`** (MQTT) tham chiếu study.

→ Lập trình gateway: dùng `pynetdicom` (C-STORE SCP) + `dicomweb-client` (STOW-RS).

### 3B. Đầu dò/SoC tự phát triển (dữ liệu RAW)
Đầu dò yếu (ESP32/MCU/SBC nhỏ) **không nên** tự làm DICOM. Phân vai:

- **Dưới mạch (firmware đầu dò):** số hoá B-mode, **nén nhẹ tại chỗ** (JPEG từng khung,
  hoặc H.264/H.265 cho cine nếu có encoder phần cứng), gắn metadata thu nhận (probe id,
  depth_cm, gain, frame_rate, timestamp, patient_binding id). Truyền lên gateway bằng
  **kênh bulk tin cậy** — **KHÔNG dùng MQTT** cho pixel: dùng **TCP/HTTP(S) POST** hoặc
  **WebSocket**, chia khối (chunked) + checksum + resume. BLE quá chậm cho cine → chỉ hợp
  ảnh tĩnh nhỏ; ưu tiên WiFi/USB/Ethernet.
- **Gateway (Raspberry Pi) làm nặng:** nhận khung raw → ghép/nén → **đóng gói DICOM**
  (US Image hoặc US Multi-frame IOD), sinh UID, điền metadata → **STOW-RS** lên PACS/S3 →
  **publish `imaging.study`**.

→ Lập trình gateway: `pydicom` (tạo DICOM từ pixel) + `dicomweb-client` (STOW-RS).

**Phác thảo code gateway (3B) — đóng gói raw → DICOM → upload → notify:**
```python
# gateway: wrap_and_publish.py (phac thao, khong chay trong repo nay)
import pydicom, numpy as np
from pydicom.uid import generate_uid, JPEGBaseline8Bit
from dicomweb_client.api import DICOMwebClient
from gateway import contract as C, registry as reg
from gateway.publisher import PavaLifePublisher

def raw_to_dicom(frames_u8, rows, cols, patient_id, study_uid, series_uid):
    ds = pydicom.Dataset()
    ds.PatientID = patient_id
    ds.StudyInstanceUID = study_uid
    ds.SeriesInstanceUID = series_uid
    ds.SOPInstanceUID = generate_uid()
    ds.SOPClassUID = "1.2.840.10008.5.1.4.1.1.6.1"   # US Image Storage
    ds.Modality = "US"
    ds.Rows, ds.Columns = rows, cols
    ds.SamplesPerPixel = 1; ds.PhotometricInterpretation = "MONOCHROME2"
    ds.BitsAllocated = 8; ds.BitsStored = 8; ds.HighBit = 7; ds.PixelRepresentation = 0
    ds.NumberOfFrames = len(frames_u8)                # multi-frame (cine)
    ds.PixelData = np.asarray(frames_u8, dtype=np.uint8).tobytes()
    # ... FileMetaInformation + transfer syntax (nén JPEG/HEVC nếu cần) ...
    return ds

def on_study_done(frames, patient_id, event_time):
    study_uid, series_uid = generate_uid(), generate_uid()
    ds = raw_to_dicom(frames, 132, 176, patient_id, study_uid, series_uid)
    web = DICOMwebClient(url=reg.DICOMWEB_BASE)       # PACS DICOMweb
    web.store_instances([ds])                         # STOW-RS: đẩy pixel (DATA plane)
    msg = C.build_imaging_study("ultrasound", event_time, instances=len(frames))
    msg["payload"]["study"]["study_instance_uid"] = study_uid
    PavaLifePublisher().publish(msg)                  # MQTT: chỉ metadata (CONTROL plane)
```

---

## 4. Tầng Application — Cloud / PIH (dùng ra sao)

Application **không** nhận pixel qua MQTT. Luồng:

1. **Subscribe** topic `pvl/v2/gw/+/up/imaging.study` (MQTT 5.0/WSS).
2. Nhận `imaging.study` → đọc `patient_context`, `study.study_instance_uid`,
   `storage.wado_rs_study`. Đối chiếu bệnh nhân với HIS (rule #5).
3. **Lấy ảnh khi cần** (lazy): gọi **WADO-RS** `GET {wado_rs_study}` để tải DICOM, hoặc
   `.../thumbnail` để xem nhanh. Không tải ngay lúc nhận thông báo → tiết kiệm băng thông.
4. **Hiển thị** bằng viewer DICOM web: **OHIF Viewer** hoặc **Cornerstone.js** (đọc thẳng
   WADO-RS). Cine loop phát như video.
5. Lưu liên kết study ↔ encounter trong bệnh án.

**Phác thảo code application (consumer):**
```python
# cloud: on_imaging_study(msg)
study = msg["payload"]["study"]; storage = msg["payload"]["storage"]
link_study_to_encounter(msg["patient_context"]["encounter_id"], study["study_instance_uid"])
# Lazy fetch khi bác sĩ mở:
#   GET storage["thumbnail_url"]              -> xem nhanh
#   GET storage["wado_rs_study"]              -> tải DICOM đầy đủ (OHIF/cornerstone render)
```

---

## 5. Mở rộng contract: message_type `imaging.study`

Đã thêm vào schema (JSON Schema 2020-12) và builder. Bản tin **chỉ tham chiếu**, pixel ở
DICOMweb. Ví dụ `samples/ultrasound.json`:

```jsonc
{
  "message_type": "imaging.study",
  "source": { "source_type": "imaging_device", ... },
  "patient_context": { ... },               // bắt buộc; patient_id KHÔNG vào topic (rule #10)
  "payload": {
    "study": {
      "study_instance_uid": "1.2.826.0.1.3680043.8.498.100.107",
      "modality": "US", "number_of_instances": 24, "body_site": "Abdomen"
    },
    "series": [ { "series_instance_uid": "...", "modality": "US" } ],
    "storage": {
      "type": "dicomweb",
      "wado_rs_study": "https://pacs.pavalife.com/dicom-web/studies/<uid>",  // lấy ảnh
      "stow_rs": "https://pacs.pavalife.com/dicom-web/studies",              // nơi đã lưu
      "thumbnail_url": ".../thumbnail",
      "transfer_syntax": "1.2.840.10008.1.2.4.50"                            // JPEG Baseline
    }
  }
}
```
Test `test_contract.py` kiểm tra: **không có trường `data` (pixel) trong MQTT** + phải có
tham chiếu DICOMweb.

---

## 6. So sánh lựa chọn truyền tải data plane

| Cách | Giao thức | Khi nào dùng | Ghi chú |
|---|---|---|---|
| **DICOMweb STOW/WADO-RS** | HTTPS | Khuyến nghị — có PACS, cần vào PIH | Hợp gateway↔cloud, qua proxy/firewall dễ |
| **DICOM C-STORE (DIMSE)** | TCP 104 | Máy US ↔ PACS trong LAN bệnh viện | Cổ điển, cần cấu hình AE Title |
| **Object storage + presigned URL** | HTTPS (S3) | Telemedicine, ảnh/clip tham khảo | Rẻ, nhưng cần tự quản metadata/UID |
| ❌ Nhồi base64 vào MQTT | MQTT | **Không dùng** cho ảnh | Phình payload, nghẽn broker |

---

## 7. Cần PavaLife xác nhận (trước khi dùng thật)
- **OID gốc** cấp cho PavaLife để sinh UID hợp lệ (đang dùng OID ví dụ).
- Endpoint **PACS/DICOMweb** thật + xác thực (token/mTLS).
- Mã **thủ tục/‌body_site** (SNOMED/LOINC) cho từng loại siêu âm.
- Transfer syntax & mức nén cho cine (JPEG2000 vs HEVC) theo yêu cầu lưu trữ/chất lượng.
- Chính sách lưu ảnh ở cloud (thời hạn, mã hoá at-rest, nhật ký truy cập).
