# Medical IoT Gateway → Cloud — Data Contract (MVP, 10 thiết bị)

Hiện thực **hợp đồng dữ liệu** cho gateway y tế: Canonical JSON **v2.1** → **FHIR R4**,
transport **MQTT over TLS**. Module này **sinh và kiểm thử** payload + Bundle FHIR cho
**đủ 10 thiết bị** để đội firmware/Gateway/Cloud thống nhất trước khi code.

> Đây là module **cloud contract** của repo, tách khỏi gateway ESP32 ở `../src/`
> (vốn là gateway IoT môi trường tổng quát). Dữ liệu **giả lập** nhưng đúng chuẩn.

## 10 thiết bị

| # | device_id | Loại | message_type | FHIR | Nguồn |
|---|---|---|---|---|---|
| 1 | BP-01 | blood_pressure | observation.vitals | Observation + component | Data Contract |
| 2 | SPO-02 | pulse_oximeter | observation.vitals | Observation (+PI) | Data Contract |
| 3 | TMP-07 | thermometer | observation.vitals | Observation | Data Contract |
| 4 | WGT-09 | weight_scale | observation.vitals | Observation | Data Contract |
| 5 | LAB-05 | chemistry_analyzer | observation.lab | Observation[] + DiagnosticReport | Data Contract |
| 6 | ECG-03 | ecg | observation.waveform | Observation (SampledData) + DiagnosticReport | mở rộng v2.1 |
| 7 | CAM-04 | telemedicine_camera | media.video | Media (video) | mở rộng v2.1 |
| 8 | ECH-06 | ultrasound | imaging.study | ImagingStudy + DiagnosticReport | mở rộng v2.1 |
| 9 | STE-08 | stethoscope | media.audio | Media (audio) | mở rộng v2.1 |
| 10 | GLU-10 | glucometer | observation.lab | Observation (glucose mao mạch 41653-7) | mở rộng v2.1 |

**Canonical v2.1** mở rộng v2.0 (tương thích ngược): thêm message_type
`observation.waveform` · `imaging.study` · `media.audio` · `media.video` và trường
`sampled_data` / `media` trong `measurements[]`. 5 thiết bị numeric giữ nguyên hợp đồng.

## Cấu trúc

```
gateway-cloud/
├─ schema/canonical-v2.schema.json   # JSON Schema v2.1 (validate payload MQTT)
├─ gateway/
│  ├─ devices.py        # REGISTRY 10 thiết bị: LOINC/UCUM/SNOMED/DICOM + khoảng KT + cờ verify
│  ├─ canonical.py      # dựng envelope v2.1 (message_id, seq, timestamps)
│  ├─ validator.py      # JSON Schema + khoảng hợp lệ KT + UCUM
│  ├─ mapper_fhir.py    # Canonical → FHIR R4 transaction Bundle (6 message_type)
│  └─ publisher_mqtt.py # topic + QoS/retain + LWT + publish TLS
├─ tools/
│  ├─ gen_samples.py    # sinh 10 payload MQTT → samples/mqtt/
│  └─ gen_fhir.py       # 10 payload → 10 Bundle FHIR → samples/fhir/
├─ samples/mqtt/*.json  # 10 payload MQTT (đã sinh)
├─ samples/fhir/*.bundle.json  # 10 Bundle FHIR transaction (đã sinh)
└─ tests/test_contract.py  # validate + smoke-test mapper (không cần broker/HAPI)
```

## Chạy

**Windows (1 cú đúp chuột):** chạy `run_all.bat` — tự cài thư viện, sinh 10 payload
MQTT + 10 Bundle FHIR, validate, sinh dashboard rồi mở `viewer\index.html` trên trình duyệt.

**Thủ công (mọi nền tảng):**
```bash
cd gateway-cloud
pip install -r requirements.txt

python tools/gen_samples.py     # sinh 10 payload MQTT
python tools/gen_fhir.py        # sinh 10 Bundle FHIR
python tests/test_contract.py   # validate 10 payload + mapper (10/10 PASS)
python tools/gen_viewer.py      # sinh trang web viewer/index.html (tự đóng gói, offline)
```

**Trang web dashboard** (`viewer/index.html`): nhúng sẵn dữ liệu 10 thiết bị — mở bằng
double-click, không cần server. **Phần hiển thị tự xử lý dữ liệu thô thành hình ảnh/đồ thị**:
- Số liệu (BP/SpO2/nhiệt độ/cân/LAB/glucose) → **biểu đồ thanh** theo khoảng hợp lệ.
- **ECG** → **đồ thị sóng** PQRST vẽ từ mẫu tín hiệu thô (SampledData) trên lưới giấy đỏ.
- **Siêu âm** → **ảnh tái tạo** trên canvas từ ma trận điểm ảnh thô (gray8 base64, sector B-mode).
- **Camera** → **video phát được** ghép từ nhiều khung điểm ảnh thô (rgb888, từng khung).
- **Ống nghe** → **đồ thị sóng âm** từ đường bao S1/S2.
Bấm vào thẻ để xem lớn (tab Trực quan) + raw JSON (MQTT + FHIR).

### Triết lý "đẩy dữ liệu thô"
Thiết bị đẩy **dữ liệu thô** lên (ví dụ siêu âm = từng điểm ảnh `raster.data` base64,
ECG = mảng mẫu `sampled_data.data`); phía hiển thị mới **xử lý kết hợp thành hình ảnh/đồ thị**.
Validator kiểm tra toàn vẹn raster (số byte giải mã = `width×height`).

Validate sâu hơn với HAPI FHIR R4 (tuỳ chọn):
```bash
# POST từng Bundle transaction lên HAPI đang chạy ở localhost:8080
curl -sS -X POST -H 'Content-Type: application/fhir+json' \
  --data @samples/fhir/bp01.bundle.json http://localhost:8080/fhir
```

## Nguyên tắc mã hoá (không bịa mã)

Mọi mã chuẩn nằm tập trung trong `gateway/devices.py`, kèm cờ `verify`:
- `verify=False` → mã đã được Data Contract xác nhận (LOINC các chỉ số numeric, UCUM, DICOM `US`).
- `verify=True` → **[CẦN XÁC MINH]**, display tự gắn hậu tố `[CAN XAC MINH]`, **không dùng với bệnh nhân thật**.

### Checklist `[CẦN XÁC MINH]` (16 mục) — chốt trước khi chạy data thật

| Hạng mục | Vị trí | Bên chốt |
|---|---|---|
| Domain `system` URI thật của phòng khám (`clinic001.example.vn`) | `devices.BASE` | Cloud/Backend |
| `manufacturer` + SNOMED `Device.type` cho **cả 10 máy** | `devices[*].snomed_type` | Phần cứng |
| LOINC Perfusion Index (SPO-02) | `SPO-02` (đang `LOCAL`) | Lâm sàng + Terminology |
| LOINC panel DiagnosticReport LAB-05 (`24323-8`) | `LAB-05.report` | Lâm sàng |
| Mã waveform ECG + panel `11524-6` + category `procedure` | `ECG-03` | Lâm sàng |
| LOINC report siêu âm (`24558-9`) + procedureCode | `ECH-06.report` | Lâm sàng |
| Mã auscultation + body_site ống nghe | `STE-08.media` | Lâm sàng |
| Mã video telemedicine | `CAM-04.media` | Lâm sàng |
| Ngữ cảnh bữa ăn (glucose đói/no) | `GLU-10.meal_context` | Lâm sàng |
| Cách mã hoá `Attachment.hash` (sha256 hex vs base64) | `mapper_fhir` | Cloud |
| Ngưỡng **lâm sàng** (cảnh báo/nguy kịch) | ngoài contract này | **Bác sĩ phụ trách** |

> **Phân biệt glucose:** GLU-10 là glucose **mao mạch** `41653-7`; LAB-05 là glucose
> **huyết tương** `2345-7`. Hai mã KHÁC nhau, không trộn.

## Trạng thái kiểm thử

- 10/10 payload MQTT pass JSON Schema v2.1 + khoảng hợp lệ KT + UCUM.
- 10/10 map sang FHIR Bundle `transaction` đúng loại resource kỳ vọng.
- `patient_id` được kiểm tra **không** xuất hiện trong topic MQTT.
