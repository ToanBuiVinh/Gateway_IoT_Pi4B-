# Hướng dẫn từ A–Z — Gateway 10 node trên Raspberry Pi 5

Bắt đầu từ **thẻ nhớ trống** đến khi gateway **tự chạy nền** và nhận dữ liệu từ
10 node ESP32. Code giống bản Pi 4B; các điểm khác của Pi 5 đánh dấu ⚠️.
Chi tiết kiến trúc / cloud / downlink xem [`HUONG_DAN.md`](HUONG_DAN.md),
bảo mật xem [`BAO_MAT.md`](BAO_MAT.md).

| Khác biệt Pi 5 so với Pi 4B | Repo đã xử lý |
|---|---|
| ⚠️ Không còn user `pi` mặc định | `scripts/install_service.sh` tự điền user + đường dẫn |
| ⚠️ OS mới dùng Python 3.13 | `PyYAML==6.0.2` (có wheel cho 3.13) |
| ⚠️ Mạng do NetworkManager quản lý | Đặt IP tĩnh bằng `nmcli` (bước 4) |
| ⚠️ Nguồn 5V **5A** (27W) | Dùng nguồn chính hãng, tránh báo thiếu nguồn |

---

## Bước 0 — Chuẩn bị
- Raspberry Pi 5 + nguồn **USB‑C 5V 5A (27W)** + tản nhiệt/quạt Active Cooler.
- Thẻ microSD **≥ 32GB, A1/A2**, nên loại *High Endurance* (gateway ghi liên tục).
- Đầu đọc thẻ, dây LAN (khuyến nghị LAN thay vì WiFi cho ổn định).
- 10 ESP32 + cảm biến.

## Bước 1 — Ghi hệ điều hành (trên Windows)
1. Cài **Raspberry Pi Imager** (raspberrypi.com/software).
2. Chọn: Device **Raspberry Pi 5** → OS **Raspberry Pi OS (other) → Raspberry Pi OS Lite (64-bit)** → thẻ nhớ.
3. **Next → Edit settings**:
   - Hostname: `gateway`
   - Username/password: tự đặt (vd `admin`). ⚠️ Ghi nhớ username.
   - WiFi (nếu không dùng LAN), Locale: `Asia/Ho_Chi_Minh`
   - Tab **Services**: **Enable SSH** (password authentication).
4. **Save → Yes**, chờ ghi xong.

## Bước 2 — Khởi động & SSH
Cắm thẻ + LAN + nguồn, chờ 1–2 phút. Trên PowerShell của Windows:
```bash
ssh admin@gateway.local
```
Không được thì xem IP của Pi trong trang quản trị router và dùng `ssh admin@<IP>`.

## Bước 3 — Cập nhật hệ thống
```bash
sudo apt update && sudo apt full-upgrade -y && sudo apt install -y git
sudo reboot
```

## Bước 4 — IP tĩnh cho Pi
10 ESP32 ghi cứng IP này trong firmware nên IP **không được đổi**. Cách dễ nhất:
đặt *DHCP reservation* trên router. Hoặc đặt ngay trên Pi:
```bash
nmcli con show                       # xem tên kết nối, vd "Wired connection 1"
sudo nmcli con mod "Wired connection 1" ipv4.method manual \
     ipv4.addresses 192.168.1.10/24 ipv4.gateway 192.168.1.1 ipv4.dns 8.8.8.8
sudo nmcli con up "Wired connection 1"   # SSH sẽ rớt -> đăng nhập lại bằng IP mới
```
Đổi dải IP cho đúng mạng của bạn.

## Bước 5 — Tải code
```bash
cd ~ && git clone https://github.com/ToanBuiVinh/Gateway_IoT_Pi4B-.git gateway-app
cd ~/gateway-app
```
Repo private → GitHub hỏi đăng nhập, dùng *Personal Access Token* thay mật khẩu.

## Bước 6 — Mosquitto bản thử nhanh (chưa bảo mật)
```bash
bash scripts/setup_mosquitto.sh
```
Kiểm tra bằng 2 cửa sổ SSH:
```bash
mosquitto_sub -t 'iot/nodes/#' -v                                          # cửa sổ 1
mosquitto_pub -t 'iot/nodes/node-01' -m '{"temperature":25.5,"humidity":60}' # cửa sổ 2
```
Cửa sổ 1 hiện bản tin → broker chạy tốt.

## Bước 7 — Cài gateway Python
```bash
bash scripts/install.sh
```

## Bước 8 — Cấu hình
- `config/gateway.yaml`: lúc đầu để **`cloud.enabled: false`** (dữ liệu đệm vào SQLite).
- `config/nodes.yaml`: sửa tên/loại/khoảng giá trị cho đúng 10 thiết bị thật.
  `id` phải **trùng** `NODE_ID` trong firmware.

Sửa file: `nano config/nodes.yaml` (Ctrl+O lưu, Ctrl+X thoát).

## Bước 9 — Chạy thử với 10 node giả lập
```bash
# cửa sổ 1
source .venv/bin/activate && python -m src.main
# cửa sổ 2
source .venv/bin/activate && python scripts/simulate_nodes.py
```
Log gateway thấy node-01 … node-10 → phần mềm OK. Ctrl+C để dừng.

## Bước 10 — Bật bảo mật broker
```bash
bash scripts/setup_mosquitto_secure.sh
```
Script sẽ:
- **Tự sao lưu & xoá** cấu hình bản nhanh `/etc/mosquitto/conf.d/gateway.conf`
  (thành `gateway.conf.bak`) để không trùng cổng / không còn đăng nhập ẩn danh.
- Tạo tài khoản `gateway` + `node-01` … `node-10`, ACL theo topic.
- Mở cổng **1883 cho cả LAN** (bắt buộc user/pass) để ESP32 kết nối được.
  Muốn chỉ cho máy Pi dùng 1883 và node vào bằng TLS:
  `LISTEN_ADDR=127.0.0.1 ENABLE_TLS=1 bash scripts/setup_mosquitto_secure.sh`
  (chạy `scripts/gen_certs.sh` trước).
- Ghi mật khẩu vào `~/gateway-app/mqtt_credentials.txt`.

> Sau bước này `simulate_nodes.py` bị từ chối (nó kết nối ẩn danh) — đúng như mong muốn.

## Bước 11 — Firmware 10 ESP32
1. Arduino IDE + board ESP32 + thư viện `PubSubClient`, `ArduinoJson`.
2. Mở `firmware/esp32_node/esp32_node.ino`, sửa:
   - `WIFI_SSID`, `WIFI_PASS`
   - `MQTT_HOST = "192.168.1.10"` (IP ở bước 4)
   - `NODE_ID` và `MQTT_USER`: `node-01`, `node-02`, … (**mỗi board một số**)
   - `MQTT_PASS`: lấy trong `mqtt_credentials.txt`
3. Nạp lần lượt cho 10 board.

## Bước 12 — Cloud & chạy nền tự động
1. Cài service (tự điền user + đường dẫn, tạo `/etc/iot-gateway/secrets.env` nếu chưa có):
   ```bash
   bash scripts/install_service.sh
   ```
2. Điền mật khẩu (`LOCAL_MQTT_PASS` = mật khẩu `gateway` trong `mqtt_credentials.txt`,
   cùng tài khoản cloud):
   ```bash
   sudo nano /etc/iot-gateway/secrets.env
   ```
3. Trong `config/gateway.yaml` đặt `cloud.enabled: true`, điền `host`/topic cloud.
4. Khởi động lại và xem log:
   ```bash
   sudo systemctl restart iot-gateway
   journalctl -u iot-gateway -f
   ```
Từ giờ gateway tự chạy khi Pi bật và tự restart sau 10s nếu lỗi.

---

## Khắc phục sự cố
| Hiện tượng | Nguyên nhân thường gặp |
|---|---|
| `ssh gateway.local` không được | Dùng IP; kiểm tra đã bật SSH ở bước 1 |
| Mosquitto không khởi động | Xem lỗi: `sudo journalctl -u mosquitto -n 50` |
| ESP32 báo `rc=5` | Sai user/mật khẩu node |
| ESP32 báo `rc=-2` | Sai IP, khác mạng WiFi với Pi, hoặc broker chỉ nghe `127.0.0.1` |
| Node "offline" trên gateway | `NODE_ID` firmware ≠ `id` trong `nodes.yaml` |
| Service lỗi `status=217/USER` | User không tồn tại → chạy lại `bash scripts/install_service.sh` |
| `install.sh` lỗi khi cài PyYAML | Chưa `git pull` bản mới (cần `PyYAML==6.0.2`) |
| Pi báo thiếu nguồn / tự khởi động lại | Nguồn yếu → dùng nguồn 5V 5A chính hãng |
