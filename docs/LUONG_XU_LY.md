# Luồng xử lý & Kiến trúc kỹ thuật (asyncio event-driven)

Tài liệu này phân tích **logic xử lý** của gateway và ánh xạ từng mục đặc tả kỹ
thuật sang mã nguồn cụ thể trong `src/`.

---

## 1. Sơ đồ tổng thể

```
                 ┌──────────────────────── Raspberry Pi 4B ────────────────────────┐
                 │                                                                  │
  10 Nodes       │   Local MQTT Client            asyncio.Queue                     │
  (ESP32) ──MQTT─┼─►  (mqtt_local.py) ──put──►  ingest_queue                        │
                 │        [thread paho]             │                               │
                 │                                  ▼                               │
                 │                          Ingestion Worker (workers.py)           │
                 │                                  │                               │
                 │              online? ───yes──► Cloud MQTT Client ──TLS──►  ☁ Cloud
                 │                  │             (cloud_publisher.py)   PUBACK Broker
                 │                  └──no/fail──►  db_queue                          │
                 │                                  │                               │
                 │                                  ▼                               │
                 │                          Database Worker  ──batch(10–20/3s)──┐    │
                 │                                                              ▼    │
                 │                                              SQLite (WAL)  telemetry_buffer
                 │                                                    ▲  status=0     │
                 │   Store-and-Forward Worker ◄── online? ───────────┘               │
                 │     đọc FIFO, +buffered:true, throttle 50ms, PUBACK→status=1 ──►☁  │
                 │                                                                  │
                 │   ── DOWNLINK (điều khiển 2 chiều) ──                              │
  Node ◄─iot/cmd─┼── Local MQTT ◄── Command Worker ◄── cmd_queue ◄── Cloud MQTT ◄─☁ Cloud
                 │                                                                  │
                 │   Network Monitor (5s)   Disk Cleanup (>85%)   Heartbeat (30s)   │
                 └──────────────────────────────────────────────────────────────────┘
```

Mọi tác vụ chạy trên **một event loop asyncio** duy nhất. Việc I/O chặn (SQLite,
chờ PUBACK) được đẩy sang thread phụ bằng `asyncio.to_thread(...)` để **không
khoá event loop**. Hai MQTT client dùng `paho` ở chế độ `loop_start()` (có thread
mạng riêng, tự reconnect) và bắc cầu về event loop bằng `call_soon_threadsafe`.

---

## 2. Ánh xạ Đặc tả → Mã nguồn

| Đặc tả | Thành phần | File | Điểm chính |
|---|---|---|---|
| **§1** Khởi tạo: WAL, 2 MQTT client, Network Monitor 5s | `Database`, `LocalMqttClient`, `CloudPublisher`, `network_monitor_worker` | `db.py`, `mqtt_local.py`, `cloud_publisher.py`, `network_monitor.py` | `PRAGMA journal_mode=WAL`; hai client khởi động trong `Gateway.run()` |
| **§2** Ingestion: callback→Queue→online publish / offline→DB | `LocalMqttClient._on_message`, `ingestion_worker` | `mqtt_local.py`, `workers.py` | Quyết định dựa trên `state.online` (asyncio.Event) |
| **§3** Batching 10–20 msg hoặc 3s → 1 transaction | `database_worker`, `Database.insert_batch` | `workers.py`, `db.py` | `executemany` + 1 `COMMIT` cho cả lô |
| **§4** Store-and-Forward: backoff 2→300s, chunk 20–50 FIFO, buffered, throttle 50ms, PUBACK→update | `store_and_forward_worker`, `Backoff` | `workers.py` | `ORDER BY id ASC WHERE status=0`; `mark_sent` sau PUBACK |
| **§5** Systemd restart 10s, dọn đĩa >85% | `iot-gateway.service`, `disk_cleanup_worker` | `systemd/`, `workers.py` | `RestartSec=10`; `shutil.disk_usage` |
| **Downlink** điều khiển 2 chiều | `CloudPublisher` (subscribe), `command_worker`, `LocalMqttClient.publish_command` | `cloud_publisher.py`, `workers.py`, `mqtt_local.py` | cloud→`cmd/<id>`→relay→`iot/cmd/<id>`→node |

---

## 3. Chi tiết từng luồng

### 3.1. Khởi tạo (`Gateway.run` — `src/gateway.py`)
1. Mở SQLite, bật **WAL** + `synchronous=NORMAL` (ghi nhanh, ít hao mòn thẻ SD).
2. Tạo `AppState` (cờ `online` + bộ đếm thống kê) và 2 hàng đợi RAM:
   `ingest_queue` (có `maxsize` chống tràn RAM) và `db_queue`.
3. Khởi động **Cloud MQTT Client** (TLS) và **Local MQTT Client**.
4. `asyncio.gather` chạy song song 6 task: ingestion, database, store-and-forward,
   network-monitor, disk-cleanup, heartbeat.

### 3.2. Ingestion Pipeline (§2)
- `LocalMqttClient._on_message` (chạy trong thread paho) đóng gói
  `(node_id, payload, recv_ts)` và `call_soon_threadsafe(put_nowait)` vào
  `ingest_queue` — **an toàn luồng**, không chặn thread mạng.
- `ingestion_worker` lấy từ queue, gọi `NodeManager.handle_payload` để **giải mã
  JSON + kiểm tra khoảng giá trị** (payload hỏng/node lạ → `stats.dropped`).
  - **Online** (`state.is_online`): `await publisher.publish(...)` gửi thẳng.
    Thành công → `published_direct++`.
  - **Offline / publish lỗi**: `await db_queue.put(...)` → chuyển cho Database Worker.

### 3.3. Batching & lưu SQLite (§3)
`database_worker` gom lô để **giảm số lần COMMIT** (bảo vệ thẻ SD):
- Chờ tin đầu tiên (blocking), rồi gom tiếp tới khi **đủ `db_batch_max` (20)**
  **hoặc** hết `db_batch_timeout_sec` (3s). Nếu đã đạt `db_batch_min` (10) mà hàng
  đợi tạm rỗng thì ghi ngay (giảm độ trễ).
- Ghi cả lô bằng **một transaction** (`Database.insert_batch` → `executemany` +
  `commit`). Mỗi bản ghi: `id, node_id, payload(JSON), created_at, status=0`.

### 3.4. Store-and-Forward & Retry (§4)
`store_and_forward_worker`:
1. `await state.online.wait()` — **ngủ hoàn toàn khi offline** (0% CPU polling).
2. Đọc lô **FIFO**: `fetch_pending(chunk)` = `WHERE status=0 ORDER BY id ASC`.
3. Với mỗi bản ghi: chèn cờ `"buffered": true` rồi `await publisher.publish(...)`.
   - Nhận **PUBACK** → thêm vào `sent_ids`.
   - Lỗi/rớt mạng → dừng lô.
4. `mark_sent(sent_ids)` cập nhật `status=1` sau khi đã có PUBACK.
5. **Rate limiting**: `sleep(throttle_ms)` giữa các bản ghi và giữa các lô.
6. Nếu lô có lỗi → **Exponential backoff** (`Backoff`: 2→4→8…→300s) trước khi thử
   lại; thành công thì `reset()`.

### 3.5. Network Monitor (§1)
`network_monitor_worker` mỗi 5s thăm dò TCP tới cloud broker
(`asyncio.open_connection` có timeout). Nếu không tới được mà cờ đang ONLINE →
`state.set_offline()`. Việc chuyển sang ONLINE do callback `on_connect` của paho
đảm nhiệm (chỉ báo online khi **đã bắt tay MQTT thật**, tránh online giả).

### 3.6. Điều khiển 2 chiều — Downlink (`command_worker`)
Chiều ngược lại của telemetry: gửi lệnh từ cloud xuống node.
1. **Cloud** publish lệnh (JSON) vào `<cloud.command_topic>/<node_id>`
   (vd `tenant/gw-pi4b-01/cmd/node-06`, payload `{"cmd":"relay","state":1}`).
2. **Cloud MQTT Client** đã `subscribe("<command_topic>/+")` (tự subscribe lại sau
   mỗi lần reconnect) → `on_message` bắc cầu `(node_id, payload)` vào `cmd_queue`.
3. **Command Worker** lấy từ `cmd_queue`, kiểm tra `node_id` hợp lệ + payload là JSON
   (lệnh rác/node lạ → `commands_dropped`), rồi `LocalMqttClient.publish_command`
   relay xuống broker cục bộ tại `<local.command_topic>/<node_id>` (vd `iot/cmd/node-06`).
4. **Node** (ESP32) đã `subscribe("iot/cmd/<NODE_ID>")` → nhận và thực thi (bật/tắt
   relay, đổi chu kỳ gửi, hiệu chỉnh...). Xem `onCommand()` trong firmware mẫu.

> Lệnh là **realtime, không buffer**: nếu cloud offline thì lệnh không tới gateway;
> khác với telemetry (được store-and-forward). Muốn đảm bảo lệnh tới nơi, node nên
> **phản hồi trạng thái** qua uplink để cloud xác nhận (cơ chế command/ack).

### 3.7. Kháng lỗi & Bảo trì (§5)
- **Systemd** (`iot-gateway.service`): `Restart=always`, `RestartSec=10` — crash là
  tự bật lại sau 10s. `main.py` bắt `SIGINT/SIGTERM` để dừng gọn gàng.
- **Disk cleanup** (`disk_cleanup_worker`): mỗi `disk_check_interval_sec`, nếu
  `disk_usage_percent >= 85%` → xoá lô bản ghi `status=1` cũ nhất
  (`cleanup_sent`) rồi `PRAGMA wal_checkpoint(TRUNCATE)` để trả lại dung lượng.
- **Chống tràn**: `insert_batch` gọi `_enforce_row_limit` — vượt `max_buffer_rows`
  thì xoá bản ghi đã gửi cũ nhất trước.

---

## 4. Các quyết định thiết kế đáng chú ý

- **asyncio + `to_thread` cho I/O chặn**: giữ một event loop gọn nhẹ, phù hợp Pi,
  nhưng không để SQLite/PUBACK làm nghẽn toàn hệ thống.
- **`state.online` là `asyncio.Event`**: worker chờ mạng chỉ cần `await ...wait()`,
  **không polling** → tiết kiệm CPU đúng như đặc tả.
- **Cờ `buffered:true`**: cloud phân biệt dữ liệu realtime và dữ liệu gửi bù lịch sử.
- **`status` (0/1) thay vì xoá ngay**: giữ lịch sử ngắn cho chẩn đoán; disk-cleanup
  mới là nơi giải phóng dung lượng — cân bằng giữa an toàn dữ liệu và tuổi thọ thẻ.

---

## 5. Kiểm thử

`scripts/test_pipeline.py` chạy pipeline với **publisher/local client giả** (không
cần broker), xác minh 5 kịch bản: OFFLINE→buffer, ONLINE→store-and-forward (+cờ
buffered), ONLINE→publish thẳng (không buffer), dữ liệu lỗi→bị loại, và
**downlink→relay lệnh xuống node** (node lạ/lệnh hỏng→bị loại).

```bash
python scripts/test_pipeline.py
```
