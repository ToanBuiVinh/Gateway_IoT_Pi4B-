# Gateway IoT cho Raspberry Pi 4B — 10 nodes

Gateway IoT chạy trên **Raspberry Pi 4B**, kiến trúc **asyncio event-driven**,
thu thập dữ liệu từ **10 node khác nhau** qua **MQTT**, lưu đệm cục bộ
(SQLite + WAL) và đẩy lên **Cloud MQTT (TLS)** theo cơ chế **store-and-forward**
có retry khi mất mạng.

```
                 ┌──────────────────── Raspberry Pi 4B ────────────────────┐
  10 Nodes ─MQTT─┼─► Local MQTT Client ─► ingest_queue ─► Ingestion Worker  │
  (ESP32)        │                                            │             │
                 │                       online? ──yes──► Cloud MQTT ─TLS─► ☁ Cloud
                 │                          └──no/fail──► db_queue ─► Database Worker
                 │                                           │  (batch 10–20/3s)
                 │                                           ▼                │
                 │                              SQLite (WAL)  telemetry_buffer│
                 │       Store-and-Forward Worker ◄── online? ──► +buffered ─►☁
  Node ◄─iot/cmd─┼─ Local ◄─ Command Worker ◄─ Cloud MQTT ◄─ lệnh downlink ◄─☁
  Node ─iot/ack──┼► Local ─► Ack Worker ─► Cloud MQTT ─ phản hồi command/ack ─►☁
                 │       Network Monitor (5s) · Disk Cleanup (>85%)           │
                 └─────────────────────────────────────────────────────────────┘
```

## Tính năng
- Kiến trúc **bất đồng bộ (asyncio)**: hàng đợi RAM + các worker chuyên trách,
  I/O chặn đẩy sang thread phụ để không nghẽn event loop.
- **Hai MQTT client**: Local (nhận từ 10 node) + Cloud (TLS, publish QoS1 chờ PUBACK).
- **Store-and-forward**: mất mạng vẫn giữ dữ liệu trong SQLite (WAL), khi có mạng
  lại tự đẩy bù theo **FIFO**, gắn cờ `buffered:true`, có **throttle 50ms** và
  **exponential backoff (2→300s)**.
- **Batching ghi đĩa** (10–20 tin hoặc 3s / 1 transaction) để bảo vệ thẻ SD.
- Quản lý tập trung **10 node** qua `config/nodes.yaml` (bật/tắt, đơn vị, kiểm tra
  khoảng giá trị hợp lệ). Theo dõi **online/offline** từng node.
- **Điều khiển 2 chiều (downlink + command/ack)**: cloud gửi lệnh → gateway relay
  xuống node qua `iot/cmd/<node_id>`; node thực thi rồi **phản hồi ack** (`cmd_id`,
  `status`) → gateway relay lên cloud để xác nhận kết quả.
- **Bảo mật MQTT**: TLS/SSL (kèm mTLS) cho local & cloud, xác thực tài khoản riêng
  từng node, **ACL** phân quyền tối thiểu theo topic, mật khẩu qua biến môi trường.
- **Chống flood/rate-limiting**: token-bucket per-node + chặn payload lớn ở gateway,
  cùng giới hạn kết nối/hàng đợi/kích thước ở broker.
- **Dọn đĩa tự động** khi vượt 85%; chạy nền bằng **systemd** (tự restart sau 10s).
- Có **bộ giả lập 10 node** và **test pipeline** để chạy thử không cần phần cứng.

> 📐 Phân tích kiến trúc & logic xử lý chi tiết (ánh xạ đặc tả → code):
> [`docs/LUONG_XU_LY.md`](docs/LUONG_XU_LY.md)

## Bắt đầu nhanh (trên Raspberry Pi 4B)
> 🆕 Dùng **Raspberry Pi 5** / thẻ nhớ trống? Làm theo
> [`docs/HUONG_DAN_PI5.md`](docs/HUONG_DAN_PI5.md) (cài OS → broker → gateway → 10 ESP32 → chạy nền).
>
> ⚡ **Không cài được Mosquitto?** Dùng [`docs/CHAY_PI5_KHONG_MOSQUITTO.md`](docs/CHAY_PI5_KHONG_MOSQUITTO.md):
> chạy demo 10 node bằng **mini_broker.py (thuần Python)** — `bash scripts/run_pi5_demo.sh` — và
> gửi bản tin y tế **thẳng lên server PavaLife** qua `pavalife-gateway/pvl_send.py` (không cần broker local).

```bash
# 1) Cài Mosquitto broker
bash scripts/setup_mosquitto.sh

# 2) Cài gateway (tạo venv + cài thư viện)
bash scripts/install.sh
source .venv/bin/activate

# 3) Sửa cấu hình cloud trong config/gateway.yaml
#    (để cloud.enabled = false nếu chỉ muốn test cục bộ -> dữ liệu buffer vào SQLite)

# 4) Chạy gateway
python -m src.main

# 5) Mở terminal khác, chạy giả lập 10 node để thấy dữ liệu chảy về
python scripts/simulate_nodes.py

# (tuỳ chọn) chạy test pipeline, không cần broker/phần cứng
python scripts/test_pipeline.py
```

## Cấu trúc dự án
```
config/gateway.yaml      # cấu hình gateway, broker, cloud, pipeline, bảo trì
config/nodes.yaml        # định nghĩa 10 node
src/                     # mã nguồn gateway (asyncio)
  ├─ mqtt_local.py       # Local MQTT Client -> asyncio.Queue
  ├─ cloud_publisher.py  # Cloud MQTT Client (TLS, PUBACK)
  ├─ db.py               # SQLite + WAL, telemetry_buffer
  ├─ workers.py          # ingestion / database / store-forward / disk-cleanup
  ├─ network_monitor.py  # giám sát kết nối 5s
  ├─ state.py            # cờ online + thống kê
  └─ gateway.py, main.py # orchestrator + entrypoint
firmware/esp32_node/     # firmware Arduino mẫu cho node ESP32
scripts/                 # cài đặt, cấu hình broker, giả lập node, test pipeline
systemd/                 # service chạy nền (restart 10s)
docs/HUONG_DAN.md        # HƯỚNG DẪN CHI TIẾT (cài đặt, phần cứng, cloud)
docs/HUONG_DAN_PI5.md    # HƯỚNG DẪN A–Z cho Raspberry Pi 5 (từ thẻ nhớ trống)
docs/LUONG_XU_LY.md      # phân tích kiến trúc & logic xử lý (đặc tả -> code)
docs/BAO_MAT.md          # thiết kế & hướng dẫn bảo mật MQTT (TLS/auth/ACL/secrets)
```

👉 **Xem hướng dẫn đầy đủ (phần cứng, đấu nối, cloud, khắc phục lỗi) tại
[`docs/HUONG_DAN.md`](docs/HUONG_DAN.md).**
