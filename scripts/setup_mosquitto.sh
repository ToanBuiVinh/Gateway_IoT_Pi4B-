#!/usr/bin/env bash
# Cài & cấu hình Mosquitto MQTT broker trên Raspberry Pi 4B
set -euo pipefail

echo ">> Cai dat Mosquitto..."
sudo apt-get update
sudo apt-get install -y mosquitto mosquitto-clients

echo ">> Cau hinh listener (port 1883)..."
CONF=/etc/mosquitto/conf.d/gateway.conf
sudo tee "$CONF" >/dev/null <<'EOF'
listener 1883
# CHO PHEP anonymous de test nhanh. KHI CHAY THAT hay dat allow_anonymous false
# va tao user bang: sudo mosquitto_passwd -c /etc/mosquitto/passwd <user>
allow_anonymous true
# password_file /etc/mosquitto/passwd
persistence true
persistence_location /var/lib/mosquitto/
EOF

echo ">> Bat & khoi dong Mosquitto..."
sudo systemctl enable mosquitto
sudo systemctl restart mosquitto

echo ">> Kiem tra trang thai:"
sudo systemctl --no-pager status mosquitto | head -n 5

echo ">> Xong. Test thu (mo 2 terminal):"
echo "   mosquitto_sub -t 'iot/nodes/#' -v"
echo "   mosquitto_pub -t 'iot/nodes/node-01' -m '{\"temperature\":25.5,\"humidity\":60}'"
