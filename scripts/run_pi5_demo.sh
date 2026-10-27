#!/usr/bin/env bash
# =====================================================================
#  Chạy DEMO gateway 10 node trên Pi 5 — KHÔNG cần Mosquitto
#  Thay Mosquitto bằng mini_broker.py (thuần Python, không cài gì).
#
#    mini_broker (127.0.0.1:1883)  <-- 10 node giả lập publish iot/nodes/#
#          ^
#          └── src.main (gateway: nhận -> kiểm tra -> SQLite -> store&forward)
#
#  Dùng:  bash scripts/run_pi5_demo.sh        (Ctrl+C để dừng tất cả)
#  Phần gửi lên SERVER PavaLife chạy riêng — xem docs/CHAY_PI5_KHONG_MOSQUITTO.md
# =====================================================================
set -euo pipefail
cd "$(dirname "$0")/.."

# Ưu tiên python trong venv (.venv) nếu có — tránh lỗi PEP 668 externally-managed.
if [ -x ".venv/bin/python" ]; then
  PY=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
else
  echo "[LOI] chua co python3"; exit 1
fi
echo ">> Python: $PY"
# Kiểm tra thư viện cần thiết (paho, yaml). Thiếu -> gợi ý tạo venv.
"$PY" -c "import paho.mqtt.client, yaml" 2>/dev/null || {
  echo "[LOI] thiếu thư viện (paho-mqtt/PyYAML). Tạo venv rồi cài:"
  echo "      python3 -m venv .venv && source .venv/bin/activate"
  echo "      pip install -r requirements.txt -r pavalife-gateway/requirements.txt"
  echo "      (hoặc nhanh: pip install --break-system-packages -r requirements.txt)"
  exit 1
}

# Nạp .env nếu có (biến bí mật). Với mini_broker thì không bắt buộc (bỏ qua auth).
[ -f .env ] && { set -a; . ./.env; set +a; }
mkdir -p data logs

BROKER="pavalife-gateway/local-test/mini_broker.py"
[ -f "$BROKER" ] || { echo "[LOI] khong thay $BROKER"; exit 1; }

echo ">> [1/3] Bật mini_broker (thuần Python) thay Mosquitto -> 127.0.0.1:1883"
"$PY" "$BROKER" --host 127.0.0.1 --port 1883 >logs/mini_broker.log 2>&1 &
BROKER_PID=$!

# chờ broker mở cổng 1883
for _ in $(seq 1 25); do
  "$PY" - <<'PY' 2>/dev/null && break || sleep 0.2
import socket; s=socket.socket(); s.settimeout(1); s.connect(("127.0.0.1",1883)); s.close()
PY
done

echo ">> [2/3] Chạy gateway (src.main) — nhận & xử lý dữ liệu node"
"$PY" -m src.main >logs/gateway.out 2>&1 &
GW_PID=$!
sleep 3

echo ">> [3/3] Giả lập 10 node ESP32 publish về gateway"
"$PY" scripts/simulate_nodes.py >logs/simulate.log 2>&1 &
SIM_PID=$!

cleanup() {
  echo; echo ">> Dừng demo..."
  kill "$BROKER_PID" "$GW_PID" "$SIM_PID" 2>/dev/null || true
  wait 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo
echo "=============================================================="
echo " Demo đang chạy. Log:"
echo "   gateway   : logs/gateway.log  (hoặc logs/gateway.out)"
echo "   broker    : logs/mini_broker.log"
echo "   giả lập   : logs/simulate.log"
echo " Nhấn Ctrl+C để dừng TẤT CẢ."
echo "=============================================================="
echo " --- theo dõi gateway (tail) ---"
# hiển thị log gateway theo thời gian thực; Ctrl+C -> cleanup
sleep 1
tail -n 40 -f logs/gateway.log 2>/dev/null || tail -n 80 -f logs/gateway.out
