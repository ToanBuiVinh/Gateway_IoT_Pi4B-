# Runbook: KẾT NỐI BROKER MQTT KHÁC (cực kỳ cụ thể)

Hướng dẫn từng bước để chuyển gateway từ broker test cục bộ sang **broker thật** (PavaLife
production hoặc bất kỳ broker bên thứ ba nào). Có công cụ **chẩn đoán tự động**
`tools/broker_check.py` để xác nhận trước khi gửi dữ liệu thật.

Mục lục:
[0. Sơ đồ](#0-sơ-đồ) · [1. Thông tin cần xin](#1-thông-tin-cần-xin-từ-bên-vận-hành-broker) ·
[2. Chuẩn bị](#2-chuẩn-bị-máy-gateway) · [3. Chẩn đoán](#3-chẩn-đoán-kết-nối-broker_checkpy) ·
[4. Kịch bản kết nối](#4-các-kịch-bản-kết-nối-copy-paste) · [5. Tích hợp code](#5-tích-hợp-vào-code) ·
[6. Tham số production](#6-tham-số-production-nên-thống-nhất) · [7. ACL topic](#7-acl-topic-cần-mở) ·
[8. Khắc phục lỗi](#8-bảng-khắc-phục-lỗi) · [9. Bảo mật](#9-checklist-bảo-mật) ·
[10. Go-live](#10-quy-trình-go-live) · [11. Mẫu cấu hình](#11-phụ-lục--mẫu-cấu-hình-điền-vào)

---

## 0. Sơ đồ
```
Gateway (PavaLifePublisher) ──scheme://host:port/path── Broker ──► các consumer (Cloud/PIH)
         │  xác thực: user/pass | mTLS | token                 │
         │  TLS: CA của broker                                   │
         └─ topic: pvl/v2/gw/<gateway_id>/up/<message_type>  (rule #10: KHÔNG patient_id)
```

Code đã sẵn sàng: `gateway/publisher.py` hiểu **`mqtt` / `mqtts` / `ws` / `wss`**, có
`username/password`, `ca_cert`, `insecure`, chọn **MQTT 5 hoặc 3.1.1**, tương thích paho 1.x & 2.x.

---

## 1. Thông tin cần xin từ bên vận hành broker

Gửi bảng này cho bên vận hành (PavaLife / IT bệnh viện) và điền giá trị thật:

| # | Mục | Ví dụ | Điền vào cờ |
|---|---|---|---|
| 1 | URL + cổng + scheme | `wss://mqtt-hn-n1.pavalife.com:443/mqtt` | `--broker` |
| 2 | Phiên bản MQTT | `5.0` (hay `3.1.1`) | `--mqtt-version 5` |
| 3 | Kiểu xác thực | username/password **hoặc** mTLS **hoặc** token/JWT | `--username/--password` hoặc cert |
| 4 | `username` + `password` (nếu dùng) | `GW-ROBOT-DEV-001` / `••••` | `--username/--password` |
| 5 | CA chứng chỉ của broker (nếu CA nội bộ) | `pavalife-ca.pem` | `--ca-cert` |
| 6 | Cặp cert client (nếu **mTLS**) | `gw-client.crt` / `gw-client.key` | (xem 4d) |
| 7 | `client_id` được cấp/quy ước | `GW-ROBOT-DEV-001` | `--client-id` |
| 8 | ACL topic được publish/subscribe | `pvl/v2/gw/GW-ROBOT-DEV-001/up/#` | quyền trên broker |
| 9 | Giới hạn | `message_size_limit`, QoS tối đa, rate | thiết kế gửi |
| 10 | Mạng | IP allow-list / VPN / mở outbound 443/8883 | hạ tầng |

---

## 2. Chuẩn bị máy gateway
```bash
cd pavalife-gateway
pip install -r requirements.txt          # jsonschema + paho-mqtt
# nếu broker dùng CA nội bộ: để file pavalife-ca.pem cạnh đây (bên vận hành cấp)
```
Bí mật (password/khoá) **không** hardcode, **không** commit — dùng biến môi trường (xem §11).

---

## 3. Chẩn đoán kết nối (`broker_check.py`)

Chạy TRƯỚC khi gửi dữ liệu thật. Công cụ kiểm 4 bước và tự gửi/nhận lại `device.status`:

```bash
python tools/broker_check.py \
  --broker wss://mqtt-hn-n1.pavalife.com:443/mqtt --mqtt-version 5 \
  --username GW-ROBOT-DEV-001 --password "$PVL_MQTT_PASSWORD" \
  --ca-cert pavalife-ca.pem
```
Kết quả mong đợi:
```
[1] TCP reachability            [OK] mở được TCP tới …:443
[2] TLS handshake + chứng chỉ   [OK] TLS TLSv1.3 … CN=… issuer=… hết hạn=…
[3] MQTT CONNECT                 [OK] CONNECT thành công (MQTT 5.0)
[4] round-trip device.status     [OK] ROUND-TRIP: tự nhận lại bản tin đã gửi
 KẾT QUẢ: TẤT CẢ PASS — broker sẵn sàng dùng.
```
Mỗi bước FAIL in kèm gợi ý `[→]`. Thoát code 0 nếu PASS (dùng được trong script/CI).

---

## 4. Các kịch bản kết nối (copy-paste)

### 4a. TCP + user/pass — test nội bộ
```bash
python pvl_send.py all --broker mqtt://10.0.0.5:1883 --mqtt-version 311 \
  --username gw --password secret --publish
```

### 4b. TLS (TCP) + user/pass
```bash
python pvl_send.py all --broker mqtts://broker.lan:8883 --mqtt-version 5 \
  --username gw --password "$PVL_MQTT_PASSWORD" --ca-cert ca.pem --publish
```

### 4c. WSS + user/pass — **production PavaLife**
```bash
python pvl_send.py all \
  --broker "wss://mqtt-hn-n1.pavalife.com:443/mqtt" --mqtt-version 5 \
  --username GW-ROBOT-DEV-001 --password "$PVL_MQTT_PASSWORD" \
  --ca-cert pavalife-ca.pem --publish
```
> `publisher.py` tự suy ra `transport=websockets`, bật TLS, và `ws_set_options(path=/mqtt)` từ `wss://…/mqtt`.

### 4d. mTLS (chứng chỉ client thay mật khẩu)
`publisher.py` gọi `tls_set(ca_certs=ca_cert)`; với mTLS bổ sung `certfile`/`keyfile`:
```python
# sửa publisher.py (nhánh self._tls) hoặc truyền qua lớp bọc:
self._client.tls_set(ca_certs="pavalife-ca.pem",
                     certfile="gw-client.crt", keyfile="gw-client.key")
```
Xin bên vận hành cấp cặp `gw-client.crt`/`gw-client.key` gắn với `client_id`.

### 4e. Token/JWT
Nhiều broker nhận **token qua trường password** (username = tên client, password = JWT):
```bash
python pvl_send.py status --broker "wss://…:443/mqtt" --mqtt-version 5 \
  --username GW-ROBOT-DEV-001 --password "$PVL_JWT" --ca-cert ca.pem --publish
```

> ⚠️ `--insecure` (bỏ xác minh TLS) **chỉ để thử tạm**, tuyệt đối không dùng production.

---

## 5. Tích hợp vào code

```python
import os, datetime as dt
from gateway.publisher import PavaLifePublisher
from gateway import contract as C

pub = PavaLifePublisher(
    "wss://mqtt-hn-n1.pavalife.com:443/mqtt",
    username="GW-ROBOT-DEV-001",
    password=os.environ["PVL_MQTT_PASSWORD"],   # bí mật từ ENV, KHÔNG hardcode
    ca_cert="pavalife-ca.pem",                  # bỏ nếu CA công cộng
    mqtt_version="5",
)
pub.connect()
et = dt.datetime.now(dt.timezone.utc).isoformat()
pub.publish(C.build_device_status(et), qos=1)   # bản tin đầu tiên = device.status
pub.publish(C.build_vitals("blood_pressure", {...}, et), qos=1)
pub.disconnect()
```

---

## 6. Tham số production nên thống nhất

| Tham số | Khuyến nghị | Lý do |
|---|---|---|
| **QoS** | **1** (at-least-once) cho vitals/lab/alarm/audio-ref/imaging-ref | Không mất bản tin; `message_id` khử trùng (rule #2) |
| **Session expiry** (MQTT5) | > 0 (vài phút) | Giữ hàng đợi khi rớt mạng ngắn |
| **clean start** | false khi muốn nối lại session | Nhận tiếp bản tin chờ |
| **keepalive** | 30–60 s | Phát hiện rớt kết nối |
| **Last Will (LWT)** | publish `device.status`=offline khi rớt | Cloud biết gateway mất kết nối |
| **retain** | **không** cho observation; có thể cho `device.status` mới nhất | Observation là sự kiện, không phải trạng thái |
| **sequence_no** | tăng dần theo (facility, gateway, source) kể cả sau reconnect | rule #3 |
| **store-and-forward** | đệm tại gateway khi mất mạng | Không mất dữ liệu đo |
| **payload lớn** | **không** qua broker | Ảnh/audio đi data plane (xem `CO_CHE_TRUYEN.md`) |

---

## 7. ACL topic cần mở

Nguyên tắc **tối thiểu quyền** — gateway chỉ cần:
| Quyền | Topic |
|---|---|
| **PUBLISH** | `pvl/v2/gw/GW-ROBOT-DEV-001/up/#` |
| SUBSCRIBE (nếu có kênh lệnh downlink) | `pvl/v2/gw/GW-ROBOT-DEV-001/down/#` |

> `patient_id` **không bao giờ** nằm trong topic (rule #10) → ACL không rò định danh bệnh nhân.

---

## 8. Bảng khắc phục lỗi

| Triệu chứng | Bước FAIL | Nguyên nhân | Cách xử lý |
|---|---|---|---|
| `getaddrinfo`/`Name or service not known` | [1] | Sai hostname / DNS | Kiểm tra URL, `/etc/hosts`, DNS |
| TCP timeout / refused | [1] | Firewall/VPN/sai cổng | Mở outbound 443/8883; xin IP allow-list |
| `CERTIFICATE_VERIFY_FAILED` | [2] | Thiếu CA nội bộ | Thêm `--ca-cert <ca>.pem` |
| `hostname mismatch` | [2] | SAN cert ≠ host | Dùng đúng hostname trong URL; xin cert đúng SAN |
| CONNECT reason 4/5 (bad auth/not authorized) | [3] | Sai user/pass/token | Kiểm tra thông tin cấp |
| CONNECT reason 133/135 | [3] | client_id trùng / bị cấm | Dùng `client_id` duy nhất được cấp |
| Treo ở `wss` | [3] | Proxy chặn 443 / sai `path` | Cấu hình proxy; path phải là `/mqtt` |
| publish không có PUBACK | [4] | ACL chặn publish | Xin mở `…/up/#` |
| publish OK nhưng không nhận lại | [4] | ACL chặn subscribe | Xin mở subscribe topic tương ứng |
| Bản tin bị broker/consumer loại | sau [4] | Sai schema | Chạy `tests/test_contract.py` trước khi gửi |

---

## 9. Checklist bảo mật
- [ ] TLS bật (`wss`/`mqtts`), xác minh CA — **không** `--insecure` ở production.
- [ ] Bí mật (password/khoá) trong **ENV / secret manager**, không hardcode, không commit.
- [ ] `client_id` duy nhất mỗi gateway; ACL tối thiểu quyền.
- [ ] `patient_id` chỉ trong payload, **không** topic/log (rule #10).
- [ ] Rate limit + store-and-forward để không spam broker khi mạng chập chờn.
- [ ] LWT `device.status=offline` để giám sát.
- [ ] Xoay (rotate) mật khẩu/cert định kỳ; thu hồi khi lộ.

---

## 10. Quy trình go-live
1. Điền §1, đặt CA/cert/secret vào ENV (§11).
2. `python tools/broker_check.py …` → **TẤT CẢ PASS**.
3. `python pvl_send.py status --publish …` → nhờ bên vận hành xác nhận nhận được
   `pvl/v2/gw/GW-ROBOT-DEV-001/up/device.status` (Phụ lục A: "bản tin kiểm thử kết nối đầu tiên").
4. Gửi thử vitals: `python pvl_send.py vitals --devices spo2 --publish …`.
5. Bật store-and-forward + LWT, chạy nền (systemd), giám sát `device.status` định kỳ (60s).

---

## 11. Phụ lục — mẫu cấu hình (điền vào)

Biến môi trường (Linux/macOS):
```bash
export PVL_BROKER="wss://mqtt-hn-n1.pavalife.com:443/mqtt"
export PVL_MQTT_USER="GW-ROBOT-DEV-001"
export PVL_MQTT_PASSWORD="•••••••"          # KHÔNG commit
export PVL_CA_CERT="/etc/pavalife/pavalife-ca.pem"
```
Windows (PowerShell):
```powershell
$env:PVL_BROKER="wss://mqtt-hn-n1.pavalife.com:443/mqtt"
$env:PVL_MQTT_USER="GW-ROBOT-DEV-001"
$env:PVL_MQTT_PASSWORD="•••••••"
$env:PVL_CA_CERT="C:\pavalife\pavalife-ca.pem"
```
Dùng:
```bash
python tools/broker_check.py --broker "$PVL_BROKER" --mqtt-version 5 \
  --username "$PVL_MQTT_USER" --password "$PVL_MQTT_PASSWORD" --ca-cert "$PVL_CA_CERT"
```

> Endpoint/chứng chỉ/ACL/giới hạn thật thuộc **Phụ lục C — Cần PavaLife xác nhận** của contract
> v2.1; phải được PavaLife duyệt trước khi dùng dữ liệu thật.
> Cơ chế gửi audio/ảnh qua data plane: [`CO_CHE_TRUYEN.md`](CO_CHE_TRUYEN.md).
