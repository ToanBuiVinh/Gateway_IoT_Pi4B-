# Test cục bộ — gửi lên broker của chính bạn

Chạy toàn bộ trên máy bạn, **không** cần broker PavaLife thật. Bản tin đi lên một
Mosquitto chạy local (`mqtt://localhost:1883`).

## 1. Khởi động broker cục bộ

**Cách A — Docker (khuyên dùng):**
```bash
cd pavalife-gateway/local-test
docker compose up -d          # Mosquitto: 1883 (MQTT), 9001 (WebSocket)
```

**Cách B — Mosquitto cài sẵn:**
```bash
# Windows: tải mosquitto tại https://mosquitto.org/download/ rồi:
mosquitto -c pavalife-gateway\local-test\mosquitto.conf -v
# Linux/Pi:
sudo apt-get install -y mosquitto mosquitto-clients
mosquitto -c pavalife-gateway/local-test/mosquitto.conf -v
```

## 2. Lắng nghe bản tin (cửa sổ 1)
```bash
cd pavalife-gateway
pip install -r requirements.txt
python tools/pvl_subscribe.py                 # nghe mqtt://localhost:1883, topic pvl/v2/gw/+/up/#
```

## 3. Gửi bản tin lên broker cục bộ (cửa sổ 2)
```bash
cd pavalife-gateway
python pvl_send.py all    --local --publish    # gửi hết: status + 6 thiết bị + siêu âm
python pvl_send.py vitals --local --publish --devices blood_pressure,spo2
python pvl_send.py lab    --local --publish --devices glucose
python pvl_send.py status --local --publish
```
Cửa sổ 1 (subscriber) sẽ in ra từng bản tin JSON nhận được. Xong.

> Kiểm tra nhanh bằng mosquitto client (nếu đã cài):
> ```bash
> mosquitto_sub -h localhost -t 'pvl/v2/gw/#' -v
> ```

## Ghi chú
- `--local` ⇒ broker = `mqtt://localhost:1883`. Bỏ `--local` và dùng `--broker ws://localhost:9001/mqtt` để test WebSocket.
- `allow_anonymous true` chỉ dùng để test; production (PavaLife WSS) có xác thực riêng.
- `patient_id` **không** nằm trong topic (rule #10) — chỉ trong payload.
