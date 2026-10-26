#!/usr/bin/env bash
# Cài systemd service cho gateway, TỰ ĐIỀN user + đường dẫn của máy hiện tại.
# (Pi 5 / Raspberry Pi OS mới không còn user "pi" mặc định.)
#
#   bash scripts/install_service.sh
# Biến môi trường (tuỳ chọn):
#   SERVICE_USER=...   user chạy service (mặc định: user đang chạy lệnh)
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVICE_USER="${SERVICE_USER:-${SUDO_USER:-$(id -un)}}"
TEMPLATE="$APP_DIR/systemd/iot-gateway.service"
TARGET=/etc/systemd/system/iot-gateway.service

if [[ ! -x "$APP_DIR/.venv/bin/python" ]]; then
  echo "!! Chua co .venv - hay chay truoc: bash scripts/install.sh" >&2
  exit 1
fi

echo ">> Thu muc ung dung: $APP_DIR"
echo ">> User chay service: $SERVICE_USER"

# Thay đường dẫn /opt/iot-gateway + User=pi trong file mẫu, bỏ CR (nếu file bị
# chép từ Windows) rồi ghi vào systemd.
sed -e "s#/opt/iot-gateway#$APP_DIR#g" \
    -e "s#^User=.*#User=$SERVICE_USER#" \
    -e 's/\r$//' \
    "$TEMPLATE" | sudo tee "$TARGET" >/dev/null

if [[ ! -f /etc/iot-gateway/secrets.env ]]; then
  echo ">> Chua co /etc/iot-gateway/secrets.env - tao tu .env.example (hay sua mat khau!)"
  sudo mkdir -p /etc/iot-gateway
  sudo cp "$APP_DIR/.env.example" /etc/iot-gateway/secrets.env
  sudo chmod 600 /etc/iot-gateway/secrets.env
fi

echo ">> Bat & khoi dong service..."
sudo systemctl daemon-reload
sudo systemctl enable iot-gateway
sudo systemctl restart iot-gateway
sudo systemctl --no-pager status iot-gateway | head -n 5

echo ""
echo ">> XONG. Xem log: journalctl -u iot-gateway -f"
echo ">> Sua mat khau:  sudo nano /etc/iot-gateway/secrets.env  (roi: sudo systemctl restart iot-gateway)"
