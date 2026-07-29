# Hướng dẫn chi tiết — Gateway IoT trên Raspberry Pi 4B (10 nodes)

Tài liệu này hướng dẫn từ A→Z: chọn phần cứng, cài đặt, cấu hình 10 node,
kết nối cloud, chạy nền và khắc phục sự cố.

---

## 1. Tổng quan kiến trúc

Có nhiều cách làm gateway IoT. Bản này chọn phương án **phổ biến, dễ mở rộng nhất**:

- **Node** (ESP32/ESP8266 + cảm biến) đo dữ liệu, đóng gói **JSON**, publish qua
  **WiFi/MQTT** tới Pi. Mỗi node có một `node_id` riêng và publish vào topic
  `iot/nodes/<node_id>`.
- **Raspberry Pi 4B** đóng vai trò gateway:
  1. Chạy **Mosquitto** — MQTT broker cục bộ, nơi 10 node gửi dữ liệu về.
  2. Chạy **Gateway service (Python)** — subscribe broker, giải mã & kiểm tra dữ
     liệu theo định nghĩa node, lưu vào **SQLite**, rồi **đẩy lên cloud**.
- **Cloud** — nơi lưu trữ/hiển thị lâu dài (ThingsBoard, Ubidots, AWS IoT, hoặc
  server riêng). Gateway hỗ trợ đẩy qua **HTTP REST** hoặc **MQTT/TLS**.

> **Vì sao dùng MQTT?** Nhẹ, tiết kiệm pin, hỗ trợ nhiều node, có QoS đảm bảo bản
> tin. Đây là chuẩn de-facto cho IoT.

### Node dùng giao thức khác (LoRa, Zigbee, Modbus, BLE)?
Kiến trúc vẫn giữ nguyên — chỉ cần thêm một **adapter** chuyển dữ liệu về gateway.
Ví dụ:
- **LoRa**: gắn module LoRa (RFM95) vào Pi, đọc gói LoRa rồi `mosquitto_pub` vào
  `iot/nodes/<id>` → gateway xử lý y hệt node MQTT.
- **Zigbee**: dùng dongle + [Zigbee2MQTT](https://www.zigbee2mqtt.io/) (nó tự publish MQTT).
- **Modbus RTU** (RS485): viết script đọc thanh ghi rồi publish MQTT.

Nhờ vậy phần lõi gateway **không đổi** dù node dùng công nghệ gì.

---

## 2. Phần cứng cần chuẩn bị

| Thành phần | Gợi ý | Ghi chú |
|---|---|---|
| Máy gateway | **Raspberry Pi 4B** (2–4GB RAM) | Cần nguồn 5V/3A chính hãng |
| Thẻ nhớ | microSD ≥ 16GB (Class 10) | Cài Raspberry Pi OS Lite |
| 10 node | ESP32 (khuyên dùng) / ESP8266 | Mỗi node 1 vi điều khiển + cảm biến |
| Kết nối | WiFi cùng mạng với Pi | Hoặc thêm module LoRa/Zigbee nếu xa |
| (tuỳ chọn) UPS/pin | cho Pi và node | Tránh mất dữ liệu khi cúp điện |

**Ví dụ 10 node theo `config/nodes.yaml`:** nhiệt độ–độ ẩm (DHT22 ×2), ánh sáng
(BH1750), chất lượng không khí (MQ135), độ ẩm đất, cửa/chuyển động (PIR+Reed),
điện năng (PZEM-004T), mức nước (siêu âm), nhiệt độ công nghiệp (DS18B20), áp suất
(BMP280). Bạn có thể đổi tuỳ nhu cầu.

---

## 3. Cài đặt Raspberry Pi OS

1. Dùng **Raspberry Pi Imager** ghi **Raspberry Pi OS Lite (64-bit)** ra thẻ nhớ.
2. Trong Imager, bật **SSH** và cấu hình **WiFi** trước (icon bánh răng ⚙️).
3. Cắm thẻ, cấp nguồn, SSH vào Pi:
   ```bash
   ssh pi@<IP_CUA_PI>
   sudo apt-get update && sudo apt-get upgrade -y
   ```
4. Xem IP của Pi (node sẽ trỏ MQTT tới IP này):
   ```bash
   hostname -I
   ```
   > Nên đặt **IP tĩnh** cho Pi trong router để node không mất kết nối khi Pi đổi IP.

---

## 4. Cài Mosquitto (MQTT broker)

```bash
git clone https://github.com/ToanBuiVinh/Gateway_IoT_Pi4B-.git
cd Gateway_IoT_Pi4B-
bash scripts/setup_mosquitto.sh
```

Kiểm tra broker hoạt động (mở 2 terminal):
```bash
# Terminal 1 - lắng nghe mọi node
mosquitto_sub -t 'iot/nodes/#' -v

# Terminal 2 - gửi thử một bản tin
mosquitto_pub -t 'iot/nodes/node-01' -m '{"temperature":25.5,"humidity":60}'
```
Nếu terminal 1 hiện bản tin ⇒ broker OK.

> **Bảo mật khi chạy thật:** sửa `/etc/mosquitto/conf.d/gateway.conf` đặt
> `allow_anonymous false`, tạo user:
> `sudo mosquitto_passwd -c /etc/mosquitto/passwd iotuser`, bỏ comment dòng
> `password_file`, rồi `sudo systemctl restart mosquitto`. Nhớ điền
> `username/password` tương ứng vào `config/gateway.yaml` và firmware node.

---

## 5. Cài & chạy Gateway

```bash
bash scripts/install.sh          # tạo venv + cài thư viện Python
source .venv/bin/activate
python -m src.main               # chạy gateway
```

Khi chưa có node thật, mở terminal khác chạy **giả lập 10 node**:
```bash
source .venv/bin/activate
python scripts/simulate_nodes.py
```
Bạn sẽ thấy gateway log: lưu dữ liệu, số node online, số bản ghi chờ đẩy cloud.

---

## 6. Cấu hình 10 node — `config/nodes.yaml`

Mỗi node khai báo như sau:
```yaml
- id: "node-01"              # PHẢI trùng với topic node publish: iot/nodes/node-01
  name: "Nhiet do phong 1"
  type: "DHT22"
  protocol: "mqtt"
  metrics:                   # các trường dữ liệu mong đợi
    temperature: { unit: "C", min: -40, max: 80 }   # ngoài [min,max] sẽ bị loại
    humidity:    { unit: "%", min: 0,   max: 100 }
  enabled: true              # false = tạm ngưng xử lý node này
```

**Thêm node mới**: copy một khối, đổi `id`, `metrics`, rồi nạp firmware cho node
với `NODE_ID` tương ứng. Không cần sửa mã nguồn.

---

## 7. Firmware cho node ESP32

File mẫu: [`firmware/esp32_node/esp32_node.ino`](../firmware/esp32_node/esp32_node.ino)
(dùng cảm biến DHT22 làm ví dụ).

**Các bước:**
1. Cài **Arduino IDE** + board ESP32 (Boards Manager → "esp32").
2. Cài thư viện: `PubSubClient`, `ArduinoJson`, `DHT sensor library`.
3. Mở file `.ino`, sửa các dòng cấu hình:
   - `WIFI_SSID`, `WIFI_PASS`
   - `MQTT_HOST` = **IP của Raspberry Pi**
   - `NODE_ID` = `node-01` … `node-10` (mỗi node một giá trị khác nhau!)
4. Nạp firmware. Mở Serial Monitor (115200) để xem log publish.

> Với node **không phải DHT22**, giữ nguyên phần WiFi/MQTT, chỉ thay phần đọc cảm
> biến và các trường trong JSON cho khớp `metrics` khai báo ở `nodes.yaml`.

---

## 8. Kết nối Cloud — `config/gateway.yaml`

Chọn một trong ba chế độ ở mục `cloud.mode`:

### a) `none` — chỉ chạy cục bộ (mặc định để test)
Dữ liệu vẫn được nhận và lưu SQLite, không gửi đi đâu.

### b) `http` — POST JSON lên REST endpoint
Phù hợp: **ThingsBoard, Ubidots**, hoặc server riêng.
```yaml
cloud:
  mode: "http"
  http:
    url: "https://your-cloud.example.com/api/v1/telemetry"
    method: "POST"
    headers:
      Content-Type: "application/json"
      Authorization: "Bearer TOKEN_CUA_BAN"
```
Gateway gửi mảng JSON các bản ghi:
```json
[{"node_id":"node-01","gateway_id":"gw-pi4b-01","ts":1722240000.0,
  "metrics":{"temperature":25.4,"humidity":61.0}}]
```

### c) `mqtt` — publish sang broker cloud (TLS)
Phù hợp: **AWS IoT Core, HiveMQ Cloud, EMQX Cloud**.
```yaml
cloud:
  mode: "mqtt"
  mqtt:
    host: "your-broker.example.com"
    port: 8883
    tls: true
    username: "cloud_user"
    password: "cloud_pass"
    publish_topic: "tenant/gw-pi4b-01/telemetry"
```

> **Mất mạng cloud không sao:** dữ liệu nằm trong SQLite (`data/gateway.db`),
> forwarder tự thử lại với backoff và đẩy hết khi có mạng trở lại.

---

## 9. Chạy nền tự động (systemd)

```bash
# Giả sử dự án đặt tại /opt/iot-gateway (đổi cho đúng đường dẫn của bạn)
sudo cp systemd/iot-gateway.service /etc/systemd/system/
sudo sed -i "s#/opt/iot-gateway#$(pwd)#g" /etc/systemd/system/iot-gateway.service
sudo systemctl daemon-reload
sudo systemctl enable --now iot-gateway

# Theo dõi log realtime
journalctl -u iot-gateway -f
```
Gateway sẽ tự khởi động cùng Pi và tự chạy lại nếu bị crash.

---

## 10. Khắc phục sự cố

| Hiện tượng | Nguyên nhân & cách xử lý |
|---|---|
| Node không gửi được | Sai `MQTT_HOST` (phải là IP Pi), khác mạng WiFi, hoặc broker bật auth mà firmware chưa điền user/pass. |
| Gateway báo "node LẠ" | `NODE_ID` trên firmware không khớp `id` trong `nodes.yaml`. |
| Metric bị loại bỏ | Giá trị ngoài `[min,max]`, hoặc sai kiểu (không phải số). Kiểm tra lại `nodes.yaml`. |
| Node hiện OFFLINE | Quá `node_offline_after_sec` không có bản tin. Kiểm tra node/WiFi. |
| Không đẩy được cloud | Sai URL/token/chứng chỉ. Xem log `gateway.forwarder`. Dữ liệu vẫn được giữ để gửi lại. |
| Kiểm tra broker | `mosquitto_sub -t 'iot/nodes/#' -v` để xem node có gửi về không. |

---

## 11. Mở rộng gợi ý
- **Dashboard**: cài Node-RED hoặc Grafana trên Pi để vẽ biểu đồ realtime.
- **Điều khiển 2 chiều**: subscribe thêm topic `iot/cmd/<node_id>` để gửi lệnh xuống node.
- **Bảo mật**: bật TLS cho cả broker cục bộ, xoay vòng mật khẩu, dùng client certificate.
- **Giao thức khác**: thêm adapter LoRa/Zigbee/Modbus như mục 1 đã nêu.
