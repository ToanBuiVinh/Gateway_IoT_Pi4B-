# Đường DICOM thật — pydicom + Orthanc

End-to-end **đóng gói ảnh siêu âm → DICOM → PACS (Orthanc, DICOMweb) → thông báo MQTT**.
Minh hoạ đúng thiết kế [`docs/IMAGING_DESIGN.md`](../docs/IMAGING_DESIGN.md): pixel đi
**data plane** (STOW-RS/HTTP), thông báo đi **control plane** (MQTT, chỉ tham chiếu).

## 1. Cài thư viện
```bash
cd pavalife-gateway
pip install -r imaging/requirements-imaging.txt
```

## 2. Chạy Orthanc (PACS có DICOMweb)
```bash
cd pavalife-gateway/imaging
docker compose up -d
# REST + DICOMweb: http://localhost:8042  (DICOMweb: http://localhost:8042/dicom-web)
# Giao diện: mở http://localhost:8042  trên trình duyệt
```

## 3. (Tuỳ chọn) Broker cục bộ để nhận thông báo
Xem [`../local-test/README.md`](../local-test/README.md): `docker compose up -d` trong
`local-test/`, rồi mở subscriber:
```bash
python tools/pvl_subscribe.py
```

## 4. Đóng gói → upload → thông báo

**Chỉ đóng gói + lưu .dcm (không cần dịch vụ):**
```bash
python imaging/wrap_and_publish.py
# -> imaging/out/us_study.dcm  + in ra bản tin imaging.study (chưa publish)
```

**Đầy đủ (Orthanc + broker cục bộ đang chạy):**
```bash
python imaging/wrap_and_publish.py --stow --publish --local
# 1) tạo DICOM US  2) STOW-RS lên Orthanc  3) publish imaging.study -> mqtt://localhost:1883
```

**Cine (nhiều khung):**
```bash
python imaging/wrap_and_publish.py --frames 8 --stow --publish --local
```

## 5. Xem lại ảnh (tầng Application)
- Mở **http://localhost:8042** (Orthanc Explorer) → thấy study vừa STOW.
- Lấy qua **WADO-RS**: `GET http://localhost:8042/dicom-web/studies/<StudyInstanceUID>`
  (đúng URL nằm trong `storage.wado_rs_study` của bản tin `imaging.study`).
- Viewer web thật: trỏ **OHIF Viewer** vào DICOMweb root `http://localhost:8042/dicom-web`.

## Luồng
```
wrap_and_publish.py
  ├─ pydicom: pixel gray8 -> US Image (Explicit VR LE, uncompressed)
  ├─ STOW-RS  -> Orthanc  (DATA plane: ảnh)
  └─ MQTT publish imaging.study -> broker  (CONTROL plane: StudyUID + WADO URL, KHÔNG pixel)
Application: subscribe imaging.study -> WADO-RS GET -> hiển thị
```

> Đây là **PACS/broker cục bộ để test**. Khi lên thật: thay Orthanc bằng PACS của
> PavaLife, dùng OID gốc được cấp, bật xác thực (token/mTLS), và nén cine (JPEG2000/HEVC).
