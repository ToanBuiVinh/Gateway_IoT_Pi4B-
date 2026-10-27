# Chạy trên Pi 5 — KHÔNG cần Mosquitto

Hướng dẫn chạy nhánh `Gateway_Pi_5_10_Devices` trên Raspberry Pi 5, **mô phỏng**, gồm 2 phần:

- **Phần A — Gửi lên SERVER PavaLife** (`pavalife-gateway/`): đẩy bản tin thiết bị y tế
  **thẳng** lên `wss://mqtt-hn-n1.pavalife.com:443/mqtt`. **KHÔNG cần broker local** (kết nối
  ra ngoài tới broker PavaLife). Đây là phần "publish lên server".
- **Phần B — Gateway 10 node** (`src/`): thu dữ liệu 10 node ESP32 (mô phỏng) → kiểm tra →
  SQLite → store-and-forward. Phần này cần **1 broker local** cho node publish về → ta dùng
  **`mini_broker.py` (thuần Python) thay Mosquitto** (không cài gì, không `setup_mosquitto.sh`).

> Vì sao không cần Mosquitto: Phần A nối **ra** broker PavaLife (outbound), không cần broker trên Pi.
> Phần B chỉ cần **một** broker local để 10 node publish về — `mini_broker.py` làm việc đó bằng
> Python thuần. (Mosquitto chỉ là tuỳ chọn; `setup_mosquitto.sh` báo lỗi thì bỏ qua.)

---

## 0. Lấy code + cài thư viện (1 lần)
```bash
cd ~/gateway-app                      # thư mục đã clone repo
git fetch origin
git checkout Gateway_Pi_5_10_Devices
git pull

python3 -m pip install -r requirements.txt                    # cho gateway 10 node (src/)
python3 -m pip install -r pavalife-gateway/requirements.txt    # cho bộ gửi PavaLife
```
> Pi 5 OS mới dùng Python 3.13 — cả hai file đã pin bản có wheel cho 3.13.

---

## PHẦN A — Gửi lên server PavaLife (không broker)

```bash
cd ~/gateway-app/pavalife-gateway
python3 tools/broker_check.py            # chẩn đoán kết nối server (user/pass/client_id đã cấu hình sẵn)
python3 pvl_send.py status --publish     # gửi device.status (bản tin kiểm thử đầu tiên)
python3 pvl_send.py all --publish        # gửi tất cả bản tin thiết bị y tế
# gửi lặp để thấy dữ liệu "chạy": 10 lần, mỗi 5 giây, dao động nhẹ giá trị
python3 pvl_send.py vitals --count 10 --interval 5 --randomize --publish
```
Thấy `CONNECT thành công` + `PUBLISH ... THÀNH CÔNG` là server đã nhận. Thông tin đăng nhập
(host/user/password/client_id) nằm trong `pavalife-gateway/gateway/registry.py`.

---

## PHẦN B — Gateway 10 node (mini_broker thay Mosquitto)

### Cách nhanh nhất — 1 lệnh
```bash
cd ~/gateway-app
bash scripts/run_pi5_demo.sh
```
Script tự: bật `mini_broker` (127.0.0.1:1883) → chạy gateway `src.main` → giả lập 10 node ESP32,
rồi hiển thị log gateway. **Ctrl+C để dừng tất cả.** Log ở `logs/`.

### Hoặc chạy tay (3 cửa sổ SSH)
```bash
# Cửa sổ 1 — broker thuần Python (thay Mosquitto):
cd ~/gateway-app && python3 pavalife-gateway/local-test/mini_broker.py

# Cửa sổ 2 — gateway:
cd ~/gateway-app && python3 -m src.main

# Cửa sổ 3 — giả lập 10 node:
cd ~/gateway-app && python3 scripts/simulate_nodes.py
```
Cửa sổ 2 sẽ in dữ liệu từ `node-01..node-10` chảy về, được kiểm tra ngưỡng rồi ghi SQLite.

### Dữ liệu node lưu ở đâu
Gateway đệm vào SQLite `data/gateway.db` (store-and-forward). Xem nhanh:
```bash
sqlite3 data/gateway.db "SELECT COUNT(*) FROM telemetry_buffer;"              # tổng bản ghi đã nhận
sqlite3 data/gateway.db "SELECT node_id, payload FROM telemetry_buffer ORDER BY id DESC LIMIT 5;"
```
(Nếu chưa có `sqlite3`: `sudo apt install -y sqlite3`, hoặc xem trực tiếp trong `logs/gateway.log`.)

### Lưu ý về "cloud" của phần B
`config/gateway.yaml` có `cloud.host = your-cloud-broker.example.com` (chỉ là **placeholder**).
Khi `cloud.enabled: true`, gateway sẽ thử nối cloud đó, **không nối được thì đệm vào SQLite**
(đúng cơ chế store-and-forward — không phải lỗi). Nếu muốn chạy **thuần cục bộ, không báo lỗi
cloud**, sửa trong `config/gateway.yaml`:
```yaml
cloud:
  enabled: false
```

> **Quan trọng:** "cloud" của Phần B là broker IoT chung (dữ liệu môi trường temp/ẩm/ánh sáng),
> **khác** server PavaLife ở Phần A (bản tin y tế theo contract v2.1). Việc "publish lên server
> PavaLife" do **Phần A** đảm nhiệm. Hai phần độc lập, chạy song song được.

---

## Chạy nền tự khởi động (tuỳ chọn)
Phần B có thể chạy nền bằng systemd — xem [`HUONG_DAN_PI5.md`](HUONG_DAN_PI5.md) (thay bước cài
Mosquitto bằng mini_broker, hoặc tạo thêm 1 service cho mini_broker). Phần A gửi theo lịch thì
dùng `cron`/`systemd timer` gọi `pvl_send.py all --publish`.
