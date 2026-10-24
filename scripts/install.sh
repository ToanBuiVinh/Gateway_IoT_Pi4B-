#!/usr/bin/env bash
# Cai dat Gateway IoT tren Raspberry Pi 4B
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

echo ">> Thu muc ung dung: $APP_DIR"

echo ">> Cai goi he thong (python3, pip, venv)..."
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv

echo ">> Tao moi truong ao & cai thu vien Python..."
python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ">> Tao thu muc du lieu & log..."
mkdir -p data logs

echo ""
echo ">> Xong! Chay thu bang:"
echo "   source .venv/bin/activate"
echo "   python -m src.main"
echo ""
echo ">> De chay nen (tu dong khoi dong cung Pi), cai systemd service:"
echo "   sudo cp systemd/iot-gateway.service /etc/systemd/system/"
echo "   sudo sed -i \"s#/opt/iot-gateway#$APP_DIR#g\" /etc/systemd/system/iot-gateway.service"
echo "   sudo systemctl daemon-reload && sudo systemctl enable --now iot-gateway"
