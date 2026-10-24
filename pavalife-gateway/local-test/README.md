# Test cục bộ — gửi lên broker của chính bạn

Chạy toàn bộ trên máy bạn, **không** cần broker PavaLife thật. Bản tin đi lên một
Mosquitto chạy local (`mqtt://localhost:1883`).

> ⚠️ `docker` báo *not recognized* nghĩa là máy **chưa cài Docker**. Dùng **Cách A
> (không cần Docker)** bên dưới — đơn giản hơn.

## 1. Khởi động broker cục bộ

### Cách 0 — Broker thuần Python (KHÔNG tải gì cả) ✅ nhanh nhất
Không cần cài Mosquitto, không cần Docker — chỉ cần Python (bạn đã có).
```powershell
cd pavalife-gateway\local-test
start_mini_broker.bat                 REM hoặc: python mini_broker.py
```
Giữ cửa sổ này chạy (broker ở `mqtt://localhost:1883`). Đây là broker tối giản
(MQTT 3.1.1, QoS 0/1, wildcard `+` `#`) chỉ để test cục bộ.

> Client vẫn cần `paho-mqtt`: `pip install -r ..\requirements.txt` (cài từ PyPI, không
> phải tải từ mosquitto.org). `pvl_send.py --local` và `pvl_subscribe.py` tự dùng MQTT 3.1.1.

### Cách A — Mosquitto bản cài đặt (nếu muốn broker đầy đủ)
Cài 1 lần (chọn 1):
```powershell
winget install EclipseFoundation.Mosquitto
# hoặc tải installer tại https://mosquitto.org/download/
```
Mở Command Prompt **mới** (để nhận PATH), rồi chạy broker:
```powershell
cd "C:\Users\admin\Downloads\Gateway_Medical\Coding_Gateway_10_Sensors\Gateway_IoT_Pi4B-\pavalife-gateway\local-test"
start_broker.bat
```
(hoặc trực tiếp: `mosquitto -c mosquitto.conf -v`). Cửa sổ này giữ broker chạy.

> Nếu `mosquitto` vẫn *not recognized*: thêm `C:\Program Files\mosquitto` vào PATH,
> hoặc chạy bằng đường dẫn đầy đủ `"C:\Program Files\mosquitto\mosquitto.exe" -c mosquitto.conf -v`.

### Cách B — Docker (nếu đã có Docker Desktop)
```bash
cd pavalife-gateway/local-test
docker compose up -d
```

## 2. Lắng nghe bản tin (cửa sổ 2)
```powershell
cd ..\        &  REM về thư mục pavalife-gateway
pip install -r requirements.txt
python tools\pvl_subscribe.py                 REM nghe mqtt://localhost:1883
```

## 3. Gửi bản tin lên broker cục bộ (cửa sổ 3)
```powershell
cd pavalife-gateway
python pvl_send.py all    --local --publish    REM status + 6 thiết bị + siêu âm
python pvl_send.py vitals --local --publish --devices blood_pressure,spo2
python pvl_send.py status --local --publish
```
Cửa sổ 2 (subscriber) sẽ in ra từng bản tin JSON nhận được.

> Kiểm tra nhanh bằng mosquitto client (đi kèm bản cài Mosquitto):
> ```powershell
> mosquitto_sub -h localhost -t "pvl/v2/gw/#" -v
> ```

## 4. 🌐 Xem dữ liệu trên TRANG HTML (live) — `web_viewer.py`
Trình duyệt không nói được MQTT/TCP thẳng, nên `web_viewer.py` làm **cầu nối**:
`broker → (MQTT/paho) → web_viewer → (HTTP+SSE) → trình duyệt`. Chạy được với
**mini_broker, Mosquitto hay production** (chỉ cần `paho-mqtt`).
```powershell
cd pavalife-gateway
python tools\web_viewer.py                    REM nghe mqtt://localhost:1883
```
Rồi mở trình duyệt vào **http://localhost:8080** — mỗi bản tin gateway publish sẽ
hiện LIVE thành thẻ (màu theo loại: vitals/lab/imaging/audio/status), có nhãn
`rule #10 ✓` và nút *Xem JSON đầy đủ*. Mở cửa sổ 3 gửi `pvl_send.py all --local --publish`
để thấy thẻ chạy vào ngay.
```powershell
python tools\web_viewer.py --broker mqtt://localhost:1883 --http-port 8080
```

## Ghi chú
- `--local` ⇒ broker = `mqtt://localhost:1883`. Bỏ `--local` và `--broker ws://localhost:9001/mqtt` để test WebSocket.
- `allow_anonymous true` chỉ dùng để test; production (PavaLife WSS) có xác thực riêng.
- `patient_id` **không** nằm trong topic (rule #10) — chỉ trong payload.
