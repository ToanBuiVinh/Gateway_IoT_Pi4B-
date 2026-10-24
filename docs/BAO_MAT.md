# Bảo mật MQTT — Thiết kế & Hướng dẫn

Tài liệu này mô tả lớp bảo mật của gateway và cách bật từng phần. Nguyên tắc:
**mã hoá đường truyền (TLS)** + **xác thực danh tính (auth)** + **phân quyền tối
thiểu (ACL)** + **quản lý bí mật (không hardcode)**.

---

## 1. Mô hình đe doạ & đối sách

| Nguy cơ | Không bảo mật | Đối sách |
|---|---|---|
| Nghe lén (sniffing) trong LAN/Internet | MQTT plaintext lộ dữ liệu & mật khẩu | **TLS/SSL** cho local (8883) và cloud |
| Kẻ lạ kết nối broker | `allow_anonymous true` | Tắt anonymous, **tài khoản + mật khẩu** |
| Node bị chiếm giả mạo node khác | Ai cũng pub/sub mọi topic | **ACL** theo `%u`: node chỉ chạm topic của mình |
| Lộ mật khẩu qua Git | Mật khẩu nằm trong YAML bị commit | **Biến môi trường `${VAR}`** + `.gitignore` |
| Giả mạo server/broker | Client không kiểm tra danh tính broker | Kiểm tra **CA cert**; mTLS xác thực 2 chiều |

---

## 2. Lớp 1 — Mã hoá TLS/SSL

### 2.1. Cloud (khuyến nghị luôn bật)
`config/gateway.yaml` → `cloud`:
```yaml
cloud:
  tls: true
  ca_cert: ""            # trống = dùng CA hệ thống (đa số cloud dùng cert công khai)
  client_cert: ""        # mTLS: bắt buộc với AWS IoT Core
  client_key: ""
  tls_insecure: false    # KHÔNG bật ở môi trường thật
```

### 2.2. Broker cục bộ (tuỳ chọn, nên bật nếu WiFi không tin cậy)
1. Sinh chứng chỉ tự ký:
   ```bash
   bash scripts/gen_certs.sh <IP_hoac_hostname_cua_Pi>
   ```
2. Bật TLS cho Mosquitto (listener 8883):
   ```bash
   ENABLE_TLS=1 bash scripts/setup_mosquitto_secure.sh
   ```
3. Trỏ gateway sang TLS trong `config/gateway.yaml` → `local_broker`:
   ```yaml
   local_broker:
     port: 8883
     tls_enabled: true
     tls_ca_cert: "certs/ca.crt"
   ```
4. Node ESP32: đặt `#define USE_TLS 1` và dán nội dung `certs/ca.crt` vào `CA_CERT`.

> **mTLS (xác thực 2 chiều):** thêm `tls_client_cert`/`tls_client_key` cho gateway
> và bỏ comment `require_certificate true` trong cấu hình broker.

---

## 3. Lớp 2 — Xác thực (Authentication)

Tắt anonymous, mỗi thực thể một tài khoản:
```bash
bash scripts/setup_mosquitto_secure.sh
```
Script tạo:
- Tài khoản **`gateway`** (mật khẩu ngẫu nhiên) cho gateway.
- 10 tài khoản **`node-01` … `node-10`** (mỗi node một mật khẩu ngẫu nhiên).
- Ghi toàn bộ vào `mqtt_credentials.txt` (đã `.gitignore`, chmod 600).

> **Quan trọng:** username của node **phải bằng `node_id`** để khớp ACL (mục 4).

---

## 4. Lớp 3 — Phân quyền tối thiểu (ACL)

File `/etc/mosquitto/acl` do script sinh:
```
# Gateway: toàn quyền
user gateway
topic readwrite iot/#

# Mỗi node (username = node id) chỉ chạm topic của chính nó (%u = username)
pattern write iot/nodes/%u     # publish telemetry
pattern write iot/ack/%u       # publish ack
pattern read  iot/cmd/%u       # nhận lệnh
```
Kết quả: `node-03` **không thể** đọc lệnh của `node-05` hay giả mạo dữ liệu node
khác — dù có mật khẩu hợp lệ của chính nó.

---

## 5. Lớp 4 — Quản lý bí mật (Secrets)

**Không** ghi mật khẩu trực tiếp vào `config/gateway.yaml`. Config hỗ trợ cú pháp
`${TEN_BIEN}` và `${TEN_BIEN:-mac_dinh}`, lấy giá trị từ **biến môi trường**:
```yaml
local_broker:
  username: "${LOCAL_MQTT_USER:-gateway}"
  password: "${LOCAL_MQTT_PASS:-}"
cloud:
  username: "${CLOUD_MQTT_USER:-}"
  password: "${CLOUD_MQTT_PASS:-}"
```

Nạp biến môi trường:
```bash
cp .env.example .env          # rồi điền mật khẩu thật (.env đã .gitignore)
set -a; . ./.env; set +a
python -m src.main
```

Với **systemd** (production), tách bí mật khỏi unit file:
```ini
# /etc/systemd/system/iot-gateway.service
[Service]
EnvironmentFile=/etc/iot-gateway/secrets.env   # chmod 600, root
```

**Không bao giờ commit**: `certs/`, `*.key`, `*.pem`, `.env`, `mqtt_credentials.txt`
(đều đã có trong `.gitignore`).

---

## 6. Checklist khi lên Production

- [ ] `allow_anonymous false`, mỗi node một tài khoản riêng.
- [ ] ACL bật, đã kiểm chứng node không chạm được topic node khác.
- [ ] TLS bật cho cloud (bắt buộc) và cho local nếu WiFi không tin cậy.
- [ ] `tls_insecure: false` ở mọi nơi; đã kiểm tra CA cert hợp lệ.
- [ ] Mật khẩu chỉ nằm trong biến môi trường / EnvironmentFile (chmod 600).
- [ ] Khoá riêng `*.key` quyền 600, không nằm trong Git.
- [ ] Đổi mật khẩu định kỳ; cân nhắc mTLS cho các node quan trọng.
- [ ] Firewall: chỉ mở cổng MQTT cần thiết; broker cục bộ nên bind `127.0.0.1`
      nếu gateway và broker cùng máy.

---

## 7. Kiểm thử nhanh phân quyền

```bash
# Node-01 pub topic cua chinh no -> OK
mosquitto_pub -h <PI> -p 8883 --cafile certs/ca.crt \
  -u node-01 -P '<pass_node01>' -t 'iot/nodes/node-01' -m '{"temperature":25}'

# Node-01 co gang pub topic cua node-02 -> BI TU CHOI (ACL chan)
mosquitto_pub -h <PI> -p 8883 --cafile certs/ca.crt \
  -u node-01 -P '<pass_node01>' -t 'iot/nodes/node-02' -m 'gia mao'
```

---

## 8. Chống flood / Rate-limiting

Một node lỗi (hoặc bị chiếm quyền) có thể phát tràn dữ liệu, làm nghẽn pipeline,
đầy RAM queue và bào mòn thẻ SD. Phòng thủ **2 tầng**:

### 8.1. Tầng broker (Mosquitto) — giảm tác động
`scripts/setup_mosquitto_secure.sh` ghi sẵn các giới hạn:
```
message_size_limit 4096       # bỏ bản tin > 4KB
max_connections 200           # trần kết nối đồng thời
max_inflight_messages 20      # bản tin QoS>0 chờ ACK mỗi client
max_queued_messages 100       # hàng đợi tối đa mỗi client
max_keepalive 120
```
> Lưu ý: Mosquitto **không** giới hạn *tốc độ publish/giây* cho từng client — đó là
> lý do cần tầng gateway.

### 8.2. Tầng gateway (thực thi được) — token-bucket per-node
`FloodGuard` (`src/ratelimit.py`) chặn ngay tại `ingestion_worker`, **trước khi**
dữ liệu vào pipeline:
```yaml
# config/gateway.yaml
security:
  flood_guard:
    enabled: true
    max_msgs_per_sec: 5        # tốc độ trung bình mỗi node
    burst: 10                  # cho phép cụm ngắn (token-bucket)
    max_payload_bytes: 2048    # payload lớn hơn -> loại
    warn_interval_sec: 10      # giới hạn tần suất log cảnh báo
```
- **Token-bucket per-node**: mỗi node có ngân sách riêng; node flood chỉ tự chặn
  chính nó, **không ảnh hưởng** 9 node còn lại.
- **Chặn payload lớn** ngay lập tức (đếm `oversized`).
- Chỉ cấp bucket cho **node đã khai báo** (node lạ không tạo bucket → chống phình
  bộ nhớ do id ngẫu nhiên).
- Log cảnh báo được **giới hạn tần suất** (bản thân log không bị flood).
- Số liệu hiển thị ở heartbeat: `flood(rl=<rate_limited>, big=<oversized>)`.
