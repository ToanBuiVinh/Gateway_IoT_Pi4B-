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

Thêm **device.status** (Phụ lục A): connectivity / battery / sensor_health.

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
├─ tools/ gen_samples.py · gen_viewer.py
├─ samples/*.json     # 9 bản tin mẫu (đã sinh)
├─ viewer/index.html  # dashboard (đã sinh)
└─ tests/test_contract.py
```

**Windows:** double-click `run_all.bat` (hoặc `RUN.bat` ở gốc repo).

**Thủ công:**
```bash
cd pavalife-gateway
pip install -r requirements.txt
python tools/gen_samples.py      # sinh 9 bản tin mẫu
python tests/test_contract.py    # validate (9/9 PASS)
python tools/gen_viewer.py       # sinh dashboard viewer/index.html
```

**Gửi bản tin (CLI, theo tài liệu):**
```bash
python pvl_send.py vitals --devices blood_pressure,spo2   # in JSON ra màn hình
python pvl_send.py lab    --devices lab_analyzer,glucose
python pvl_send.py status
# Gửi thật lên broker MQTT 5.0/WSS:
python pvl_send.py vitals --devices spo2 --publish --username <u> --password <p>
```

## Dashboard
Vitals (BP/SpO2/nhiệt độ/cân) chạy **monitor đẩy 1 điểm / 500ms**; lab (uric acid, glucose)
biểu đồ thanh theo ngưỡng; thẻ **device.status**; bảng **ví dụ thiếu dữ liệu**; mỗi thẻ có tab
**Bản tin (MQTT)** xem JSON đầy đủ. Topic hiển thị không chứa `patient_id`.

## Cần PavaLife xác nhận (trước khi dùng dữ liệu thật)
- Mã LOINC cho **axit uric máu mao mạch** (14933-6 là Serum/Plasma — rule #6).
- SpO2: dùng 2708-6 hay 59408-5 (đo qua da) — theo yêu cầu PIH.
- Trạng thái **đói/no** cho đường huyết (chưa có trường trong schema v2.1).
