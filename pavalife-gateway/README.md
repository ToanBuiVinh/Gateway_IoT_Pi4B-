# PavaLife — Device Data Contract v2.1 (6 thiết bị)

Hiện thực **hợp đồng dữ liệu PavaLife v2.1**: 6 thiết bị y tế → Gateway → Cloud, bản
tin JSON chuẩn **MQTT 5.0 over WSS**, kiểm tra bằng **JSON Schema 2020-12**. Sinh bản
tin mẫu, validate, và một dashboard xem trực quan.

> Module này **follow đúng** `device_data_contract_v2_1.schema.json` trong tài liệu
> `PVL_Device_Data_Contract_v2.1_6thietbi.docx`. Dữ liệu là mô phỏng nhưng đúng cấu trúc.

## 6 thiết bị

| # | Thiết bị | device_id | message_type | source_type | Phép đo (LOINC) |
|---|---|---|---|---|---|
| 1 | Huyết áp | BP-001 | observation.vitals | robot_doctor | nibp panel **85354-9** (systolic 8480-6 / diastolic 8462-4 / mean 8478-0) + pulse_rate 8867-4 |
| 2 | SpO2 | SPO2-001 | observation.vitals | robot_doctor | spo2 **2708-6** · heart_rate 8867-4 |
| 3 | Nhiệt kế | TEMP-001 | observation.vitals | robot_doctor | temperature **8310-5** (Cel) |
| 4 | Cân | SCALE-001 | observation.vitals | robot_doctor | body_weight **29463-7** (kg) |
| 5 | Xét nghiệm (axit uric) | LAB-001 | observation.lab | lab_analyzer | uric_acid **14933-6** (umol/L) + specimen + report |
| 6 | Đường huyết | GLU-001 | observation.lab | lab_analyzer | blood_glucose **14743-9** (mmol/L) + specimen + report |
| 7 | Siêu âm *(mở rộng)* | US-001 | imaging.study | imaging_device | DICOM (US) — chỉ tham chiếu, pixel qua DICOMweb |
| 8 | Ống nghe điện tử *(mở rộng)* | STE-001 | observation.audio | auscultation_device | WAV/FLAC lossless (lưu) + live WebRTC |

Thêm **device.status** (Phụ lục A): connectivity / battery / sensor_health.

> **Ảnh siêu âm (imaging.study):** không nhồi pixel vào MQTT — tách control plane (metadata)
> và data plane (DICOM qua DICOMweb/WADO-RS). Nếu thiết bị chỉ xuất **raw pixel array**:
> thống nhất định dạng/kích thước/thứ tự frame/toàn vẹn rồi gateway ghép → DICOM.
> Chi tiết: [`docs/IMAGING_DESIGN.md`](docs/IMAGING_DESIGN.md).
>
> **Ống nghe điện tử (observation.audio):** 2 trường hợp — **live** (streaming độ trễ thấp
> WebRTC) và **lưu hồ sơ** (file **WAV/FLAC lossless, raw/không lọc** bảo toàn âm tim/phổi).
> Audio đi ngoài MQTT; bản tin chỉ tham chiếu. Chi tiết: [`docs/AUDIO_DESIGN.md`](docs/AUDIO_DESIGN.md).

## Cấu trúc bản tin (v2.1)

```
{ schema_version, message_id, message_type, event_time, sequence_no,
  facility{facility_id}, gateway{gateway_id, software_version, received_at, published_at, clock_source},
  source{source_id, source_type, connection},
  patient_context{patient_id, …, binding{method,status,bound_at}},   ← bắt buộc với observation.*
  payload{ measurements[…] } }                                        ← lab thêm specimen + report
```
Mỗi `measurement`: `observation_id, local_code, code{loinc}, measured_at, status, quality{status}` và
**đúng 1 trong 3**: `value+unit` | `components[]` | `data_absent_reason`.

## Quy tắc đã tuân thủ
- **#7** Không bao giờ gửi `value: null` → thiếu dữ liệu dùng `data_absent_reason` + `quality.status=unavailable`.
- **#8** `observation.lab` bắt buộc `specimen` + `report`, `source_type=lab_analyzer|lis`.
- **#10** `patient_id` **không** nằm trong topic MQTT (chỉ trong payload).
- Ngưỡng kỹ thuật (kiểm tra tại gateway) → ngoài khoảng đánh dấu `quality.status=suspect`, **không loại** bản tin.

## Cấu trúc & chạy

```
pavalife-gateway/
├─ schema/device_data_contract_v2_1.schema.json   # JSON Schema 2020-12
├─ gateway/ registry.py · contract.py · validator.py · publisher.py
├─ pvl_send.py        # CLI gửi bản tin (vitals/lab/status)
├─ tools/ gen_samples.py · gen_viewer.py · pvl_subscribe.py · web_viewer.py (xem HTML live)
├─ samples/*.json     # 9 bản tin mẫu (đã sinh)
├─ viewer/ index.html · gen_live_dashboard.py → live_dashboard.html (đồ thị + nghe tim + cine siêu âm)
└─ tests/test_contract.py
```

### ▶️ Hướng dẫn chạy — từng file làm gì

> **Windows (nhanh nhất):** double-click `run_all.bat` (hoặc `RUN.bat` ở gốc repo) —
> nó cài phụ thuộc, sinh mẫu, validate và tạo dashboard.

**Bước 0 — cài phụ thuộc (1 lần):**
```bash
cd pavalife-gateway
pip install -r requirements.txt            # jsonschema + paho-mqtt
```

**Chạy từng file — mỗi file một việc:**

| Thứ tự | Lệnh chạy | File | Làm gì | Kết quả |
|---|---|---|---|---|
| 1 | `python tools/gen_samples.py` | `tools/gen_samples.py` | Sinh bản tin mẫu đúng contract v2.1 | `samples/*.json` (9 bản tin) |
| 2 | `python tests/test_contract.py` | `tests/test_contract.py` | Validate schema 2020-12 + rule #7/#8/#10 | in `TẤT CẢ … PASS` |
| 3 | `python tools/gen_viewer.py` | `tools/gen_viewer.py` | Sinh dashboard tĩnh | `viewer/index.html` (mở bằng trình duyệt) |
| 4 | `python pvl_send.py <kind>` | `pvl_send.py` | In 1 bản tin JSON ra màn hình (không gửi) | JSON trên stdout |
| 5 | `python pvl_send.py <kind> --local --publish` | `pvl_send.py` + `gateway/publisher.py` | **Gửi thật** lên broker cục bộ | bản tin lên `mqtt://localhost:1883` |
| 6 | `python tools/pvl_subscribe.py` | `tools/pvl_subscribe.py` | Nghe & in bản tin nhận được (terminal) | JSON mỗi bản tin |
| 7 | `python tools/web_viewer.py` | `tools/web_viewer.py` | **Xem dữ liệu LIVE trên trang HTML** | mở `http://localhost:8080` |
| 8 | `python audio/record_and_publish.py` | `audio/record_and_publish.py` | Pipeline ống nghe: WAV→**FLAC lossless**→(publish) | `audio/out/*` + `audio/report.html` |
| 9 | `python imaging/wrap_and_publish.py --stow` | `imaging/wrap_and_publish.py` | Đóng gói ảnh siêu âm → **DICOM** → PACS | DICOM + `imaging.study` (MQTT) |

`<kind>` ∈ `vitals · lab · imaging · audio · status · all`. Ví dụ:
```bash
python pvl_send.py vitals --devices blood_pressure,spo2   # in JSON ra màn hình
python pvl_send.py all                                     # tất cả bản tin (in)
python pvl_send.py all --local --publish                   # gửi tất cả lên broker cục bộ
```

> 📘 **Báo cáo tham khảo** (cách chạy + cơ chế ống nghe/siêu âm + kết nối broker ngoài):
> [`docs/BAO_CAO_v2.1.md`](docs/BAO_CAO_v2.1.md). Kết nối **broker bên ngoài**:
> [`docs/EXTERNAL_BROKER.md`](docs/EXTERNAL_BROKER.md).

### ⚡ Một cú click: publish + xem dữ liệu trên web (Windows)
Double-click **`publish_and_view.bat`** — tự bật broker (mini_broker), bật web viewer,
mở trình duyệt `http://localhost:8080`, rồi publish toàn bộ bản tin. Nhấn phím để **gửi lại**;
đóng 2 cửa sổ *mini_broker* / *web_viewer* để dừng.

### 🧪 Test cục bộ — gửi lên broker của chính bạn
Không cần broker PavaLife thật, **không cần Docker, không cần tải gì**. Xem [`local-test/README.md`](local-test/README.md):
```powershell
pip install -r requirements.txt               REM cài paho-mqtt (từ PyPI)
REM 1) broker thuần Python (không tải gì):
cd local-test  &  start_mini_broker.bat       REM hoặc: python mini_broker.py
REM 2) nghe (cửa sổ khác):
python tools\pvl_subscribe.py
REM 3) gửi (cửa sổ khác):
python pvl_send.py all --local --publish      REM -> mqtt://localhost:1883
```
**Xem dữ liệu trên trang HTML (live):** `python tools\web_viewer.py` rồi mở
`http://localhost:8080` — bản tin hiện trực tiếp thành thẻ (cầu nối broker→HTTP/SSE,
chạy với cả mini_broker lẫn Mosquitto).

### 🖼️ Đường DICOM thật (pydicom + Orthanc)
Đóng gói ảnh siêu âm → DICOM → Orthanc (DICOMweb) → thông báo MQTT. Xem
[`imaging/README.md`](imaging/README.md):
```bash
pip install -r imaging/requirements-imaging.txt
cd imaging && docker compose up -d               # Orthanc (PACS + DICOMweb) :8042
python imaging/wrap_and_publish.py --stow --publish --local
```

### 🎧 Đường LƯU HỒ SƠ ống nghe (FLAC lossless thật)
Synth tín hiệu nghe tim → WAV → **nén FLAC `--best`** → **kiểm chứng lossless (bit-exact)** →
bản tin `observation.audio` → publish. Có **report HTML** xem trực quan. Xem
[`audio/README.md`](audio/README.md):
```bash
pip install -r audio/requirements-audio.txt      # cần `flac` CLI trên PATH
python audio/record_and_publish.py                # FLAC + kiểm chứng lossless (192,044→139,337 B, giảm 27.4%)
python audio/gen_report.py                        # -> audio/report.html (mở bằng trình duyệt)
python audio/record_and_publish.py --publish --local   # gửi thật lên broker cục bộ
```

## Dashboard

### 📈 Live Monitor — đồ thị chạy liên tục + nghe tim + cine siêu âm
`viewer/live_dashboard.html` (sinh từ `viewer/gen_live_dashboard.py`): **đồ thị vitals cuộn
liên tục** (HR/SpO2/nhiệt độ/HA, chu kỳ ~10 giá trị lặp), **nghe được âm tim** (WAV nhúng,
phát loop + sóng chạy), và **cine siêu âm B-mode** (canvas). Mở trực tiếp bằng trình duyệt.

Khi chạy **`python tools/web_viewer.py`** thì trang `http://localhost:8080` chính là Live
Monitor này, nhưng **lấy dữ liệu THẬT từ broker** (đồ thị hút giá trị từ bản tin
`observation.vitals/lab`), phát WAV phục vụ tại `/audio.wav`, và hiển thị **ảnh/cine siêu âm
thật từ Wikimedia Commons (CC BY-SA)** — nếu không tải được sẽ tự chuyển sang cine mô phỏng.
`http://localhost:8080/log` là danh sách bản tin dạng thẻ.
```bash
python viewer/gen_live_dashboard.py     # sinh viewer/live_dashboard.html (xem offline)
python tools/web_viewer.py              # -> http://localhost:8080 (LIVE từ broker)
```

### Dashboard tĩnh (bản cũ)
`viewer/index.html`: vitals (BP/SpO2/nhiệt độ/cân) **monitor đẩy 1 điểm / 500ms**; lab biểu đồ
thanh theo ngưỡng; thẻ **device.status**; mỗi thẻ có tab **Bản tin (MQTT)**. Topic không chứa `patient_id`.

## Cần PavaLife xác nhận (trước khi dùng dữ liệu thật)
- Mã LOINC cho **axit uric máu mao mạch** (14933-6 là Serum/Plasma — rule #6).
- SpO2: dùng 2708-6 hay 59408-5 (đo qua da) — theo yêu cầu PIH.
- Trạng thái **đói/no** cho đường huyết (chưa có trường trong schema v2.1).
