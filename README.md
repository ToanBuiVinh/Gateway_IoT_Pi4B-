# Gateway IoT cho Raspberry Pi 4B — 10 nodes

Gateway IoT chạy trên **Raspberry Pi 4B**, thu thập dữ liệu từ **10 node khác nhau**
qua **MQTT**, lưu đệm cục bộ (SQLite) và đẩy lên **Cloud** (HTTP hoặc MQTT) có
retry khi mất mạng.

```
  [10 Node ESP32 / cảm biến]                 [Raspberry Pi 4B]                 [Cloud]
  node-01 ──┐                        ┌───────────────────────────────┐
  node-02 ──┤   WiFi / MQTT          │  Mosquitto broker (1883)       │      HTTP REST
   ...      ├──────────────────────► │       │                        │  ──►  hoặc
  node-10 ──┘   iot/nodes/<id>       │  Gateway (Python):             │       MQTT/TLS
                                     │   • giải mã & kiểm tra dữ liệu │
                                     │   • theo dõi trạng thái node   │
                                     │   • SQLite (store-and-forward) │
                                     │   • forwarder đẩy cloud + retry│
                                     └───────────────────────────────┘
```

## Tính năng
- Quản lý tập trung **10 node** qua file `config/nodes.yaml` (bật/tắt, gắn đơn vị,
  kiểm tra khoảng giá trị hợp lệ cho từng metric).
- **Store-and-forward**: mất mạng cloud vẫn giữ dữ liệu trong SQLite, tự đẩy lại.
- Theo dõi **online/offline** từng node, đếm số bản tin & lỗi.
- Đẩy cloud linh hoạt: `http`, `mqtt`, hoặc `none` (chạy cục bộ để test).
- Chạy nền bằng **systemd**, tự khởi động cùng Pi.
- Có **bộ giả lập 10 node** để test ngay cả khi chưa có phần cứng.

## Bắt đầu nhanh (trên Raspberry Pi 4B)
```bash
# 1) Cài Mosquitto broker
bash scripts/setup_mosquitto.sh

# 2) Cài gateway (tạo venv + cài thư viện)
bash scripts/install.sh
source .venv/bin/activate

# 3) Sửa cấu hình cloud trong config/gateway.yaml
#    (để cloud.mode = "none" nếu chỉ muốn test cục bộ)

# 4) Chạy gateway
python -m src.main

# 5) Mở terminal khác, chạy giả lập 10 node để thấy dữ liệu chảy về
python scripts/simulate_nodes.py
```

## Cấu trúc dự án
```
config/gateway.yaml      # cấu hình gateway, broker, cloud, logging
config/nodes.yaml        # định nghĩa 10 node
src/                     # mã nguồn gateway (Python)
firmware/esp32_node/     # firmware Arduino mẫu cho node ESP32
scripts/                 # cài đặt, cấu hình broker, giả lập node
systemd/                 # service chạy nền
docs/HUONG_DAN.md        # HƯỚNG DẪN CHI TIẾT (đọc file này)
```

👉 **Xem hướng dẫn đầy đủ (phần cứng, đấu nối, cloud, khắc phục lỗi) tại
[`docs/HUONG_DAN.md`](docs/HUONG_DAN.md).**
