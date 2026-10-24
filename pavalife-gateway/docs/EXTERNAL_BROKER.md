# Kết nối broker MQTT bên ngoài (production / bên thứ ba)

Hướng dẫn chuyển từ broker test cục bộ (`mqtt://localhost:1883`) sang **broker thật**,
ví dụ broker PavaLife trong contract v2.1:

> **Broker:** `wss://mqtt-hn-n1.pavalife.com:443/mqtt` — **MQTT 5.0 over WSS**
> **Topic:** `pvl/v2/gw/GW-ROBOT-DEV-001/up/{message_type}`

Code đã sẵn sàng: `gateway/publisher.py` hiểu cả `mqtt/mqtts/ws/wss`, có username/password,
CA cert, và chọn MQTT 5 hay 3.1.1.

---

## 1. Cần XIN gì từ bên vận hành broker

Trước khi kết nối, hãy yêu cầu bên vận hành broker (PavaLife / IT bệnh viện) cung cấp:

| # | Thông tin | Ví dụ | Dùng ở đâu |
|---|---|---|---|
| 1 | **URL + cổng + scheme** | `wss://mqtt-hn-n1.pavalife.com:443/mqtt` | `--broker` |
| 2 | **Giao thức** | MQTT 5.0 (hay 3.1.1) | `--mqtt-version` |
| 3 | **Xác thực** | username/password, hoặc **mTLS** (client cert), hoặc **JWT/token** | `--username/--password` hoặc cert |
| 4 | **CA chứng chỉ** của broker (nếu CA nội bộ) | `pavalife-ca.pem` | `--ca-cert` |
| 5 | **client_id** được cấp / quy ước | `GW-ROBOT-DEV-001-pub` | `publisher.py` |
| 6 | **ACL topic** — được publish/subscribe topic nào | `pvl/v2/gw/GW-ROBOT-DEV-001/up/#` | quyền trên broker |
| 7 | **Giới hạn** | `message_size_limit`, QoS tối đa, rate limit | thiết kế gửi |
| 8 | **IP allow-list / VPN** (nếu có) | mở firewall cho IP gateway | hạ tầng |

> ⚠️ **Không** đưa `patient_id` vào topic hay log (rule #10). ACL chỉ nên cho gateway
> publish nhánh `up/` của chính nó, và subscribe nhánh lệnh (nếu có) — nguyên tắc tối thiểu quyền.

---

## 2. Cấu hình kết nối trong code

`gateway/publisher.py` nhận `broker_url` theo scheme — tự suy ra cổng, TLS, WebSocket:

| Scheme | Nghĩa | Cổng mặc định | TLS | Transport |
|---|---|---|---|---|
| `mqtt://`  | TCP thường (chỉ test cục bộ) | 1883 | không | tcp |
| `mqtts://` | TCP + TLS | 8883 | có | tcp |
| `ws://`    | WebSocket | 9001 | không | websockets |
| `wss://`   | **WebSocket + TLS (production PavaLife)** | 443 | có | websockets |

### 2a. Gửi bằng CLI `pvl_send.py`
```bash
# Production PavaLife (WSS + MQTT 5.0), có username/password:
python pvl_send.py all \
  --broker "wss://mqtt-hn-n1.pavalife.com:443/mqtt" \
  --mqtt-version 5 \
  --username "GW-ROBOT-DEV-001" --password "<cấp-bởi-PavaLife>" \
  --publish
```
> `pvl_send.py` mặc định `--mqtt-version 5`; chỉ khi `--local` mới tự hạ xuống 3.1.1
> (vì mini_broker/Mosquitto test dùng 3.1.1). Với broker ngoài, **giữ MQTT 5** theo contract.

### 2b. Gọi trực tiếp `PavaLifePublisher` (trong code tích hợp)
```python
from gateway.publisher import PavaLifePublisher
from gateway import contract as C
import datetime as dt

pub = PavaLifePublisher(
    "wss://mqtt-hn-n1.pavalife.com:443/mqtt",
    username="GW-ROBOT-DEV-001",
    password="…",
    ca_cert="pavalife-ca.pem",   # nếu broker dùng CA nội bộ; bỏ nếu CA công cộng
    mqtt_version="5",
)
pub.connect()
msg = C.build_vitals("blood_pressure", dt.datetime.now(dt.timezone.utc).isoformat())
pub.publish(msg, qos=1)          # QoS 1 = ít nhất một lần (khuyến nghị)
pub.disconnect()
```

### 2c. Xác thực bằng chứng chỉ client (mTLS)
Nếu broker yêu cầu **mutual TLS** thay cho mật khẩu, cấu hình paho qua `tls_set` (cần bổ
sung 2 tham số `certfile`/`keyfile` — hiện `publisher.py` đã có chỗ `tls_set`, mở rộng:
```python
self._client.tls_set(ca_certs=ca_cert, certfile="gw-client.crt", keyfile="gw-client.key")
```
Xin bên vận hành cấp cặp `gw-client.crt` / `gw-client.key` gắn với `client_id` của gateway.

---

## 3. Tham số kết nối nên thống nhất (production)

| Tham số | Khuyến nghị | Lý do |
|---|---|---|
| **QoS** | **1** (at-least-once) cho vitals/lab/alarm | không mất bản tin; `message_id` để khử trùng (rule #2) |
| **clean session / session expiry** | session bền (MQTT5 `session-expiry-interval` > 0) | giữ hàng đợi khi rớt mạng ngắn |
| **keepalive** | 30–60 s | phát hiện rớt kết nối |
| **Last Will (LWT)** | publish `device.status`=offline khi rớt | cloud biết gateway mất kết nối |
| **retain** | **không** cho observation; có thể dùng cho `device.status` mới nhất | observation là sự kiện, không phải trạng thái |
| **Thứ tự & sequence_no** | tăng dần theo (facility, gateway, source) kể cả sau reconnect | rule #3 |
| **store-and-forward** | đệm tại gateway khi mất mạng, gửi lại khi có mạng | không mất dữ liệu đo |

> **Payload lớn (ảnh siêu âm, audio) KHÔNG đi qua broker.** MQTT chỉ mang bản tin nhỏ
> tham chiếu; ảnh đi DICOMweb, audio đi object storage/WebRTC. Xem `IMAGING_DESIGN.md`,
> `AUDIO_DESIGN.md`.

---

## 4. Kiểm tra kết nối (theo thứ tự)

1. **Mạng/DNS/cổng:** `openssl s_client -connect mqtt-hn-n1.pavalife.com:443` → thấy chứng chỉ TLS.
2. **Bản tin đầu tiên = `device.status`** (Phụ lục A của contract: "bản tin kiểm thử kết
   nối đầu tiên"). Gửi:
   ```bash
   python pvl_send.py status --broker "wss://…:443/mqtt" --mqtt-version 5 \
          --username … --password … --publish
   ```
3. Nhờ bên vận hành xác nhận đã nhận trên topic `pvl/v2/gw/GW-ROBOT-DEV-001/up/device.status`.
4. Khi `device.status` thông, mới gửi observation thật.

### Lỗi thường gặp
| Triệu chứng | Nguyên nhân | Cách xử lý |
|---|---|---|
| `CERTIFICATE_VERIFY_FAILED` | thiếu CA nội bộ | thêm `--ca-cert pavalife-ca.pem` |
| Rớt ngay sau connect | sai username/password hoặc client_id trùng | kiểm tra thông tin cấp; client_id phải **duy nhất** |
| `Not authorized` khi publish | ACL chưa mở topic | xin mở `pvl/v2/gw/<gateway_id>/up/#` |
| Kết nối treo ở `wss` | proxy/firewall chặn 443 | mở outbound 443 / cấu hình proxy |
| Bản tin bị loại | sai schema | chạy `tests/test_contract.py` trước khi gửi |

---

## 5. Bảo mật (checklist bàn giao)
- [ ] TLS bật (wss/mqtts), xác minh CA — **không** `--insecure` ở production.
- [ ] Bí mật (password/kkey) lưu ở biến môi trường / secret manager, **không** hardcode, **không** commit.
- [ ] `client_id` duy nhất cho mỗi gateway; ACL tối thiểu quyền.
- [ ] `patient_id` chỉ trong payload, **không** trong topic/log (rule #10).
- [ ] Rate limit / store-and-forward để không spam broker khi mạng chập chờn.
- [ ] LWT `device.status=offline` để giám sát.

> Các mục cấu hình thật (endpoint, chứng chỉ, ACL, giới hạn) thuộc **Phụ lục C — Cần
> PavaLife xác nhận** của contract v2.1; phải được PavaLife duyệt trước khi dùng dữ liệu thật.
