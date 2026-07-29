#!/usr/bin/env bash
# Cấu hình Mosquitto BẢO MẬT: tắt anonymous, tài khoản riêng từng node + ACL,
# và (tuỳ chọn) TLS trên cổng 8883.
#
#   bash scripts/setup_mosquitto_secure.sh
# Biến môi trường:
#   ENABLE_TLS=1        bật listener TLS 8883 (cần chạy gen_certs.sh trước)
#   GATEWAY_PASS=...     mật khẩu tài khoản gateway (mặc định sinh ngẫu nhiên)
#   NODE_PASS_PREFIX=... tiền tố mật khẩu node (mặc định: sinh ngẫu nhiên mỗi node)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PW_FILE=/etc/mosquitto/passwd
ACL_FILE=/etc/mosquitto/acl
CONF=/etc/mosquitto/conf.d/gateway-secure.conf
CRED_OUT="$REPO_DIR/mqtt_credentials.txt"   # đã .gitignore
NODES=(node-01 node-02 node-03 node-04 node-05 node-06 node-07 node-08 node-09 node-10)

echo ">> Cai Mosquitto (neu chua co)..."
sudo apt-get update && sudo apt-get install -y mosquitto mosquitto-clients openssl

# 1) Tài khoản: gateway + 10 node -------------------------------------------
GATEWAY_USER=gateway
GATEWAY_PASS="${GATEWAY_PASS:-$(openssl rand -base64 18)}"

echo ">> Tao tai khoan gateway + 10 node..."
sudo touch "$PW_FILE"
# Tạo/ghi đè tài khoản gateway (cờ -c tạo file mới ở lần đầu)
sudo mosquitto_passwd -b -c "$PW_FILE" "$GATEWAY_USER" "$GATEWAY_PASS"

: > "$CRED_OUT"
{
  echo "# Thong tin dang nhap MQTT (GIU BI MAT - da .gitignore)"
  echo "gateway : $GATEWAY_USER / $GATEWAY_PASS"
} >> "$CRED_OUT"

for n in "${NODES[@]}"; do
  NPASS="${NODE_PASS_PREFIX:+${NODE_PASS_PREFIX}-${n}}"
  NPASS="${NPASS:-$(openssl rand -base64 12)}"
  sudo mosquitto_passwd -b "$PW_FILE" "$n" "$NPASS"
  echo "$n : $n / $NPASS" >> "$CRED_OUT"
done
chmod 600 "$CRED_OUT"
echo ">> Da ghi thong tin dang nhap vao: $CRED_OUT"

# 2) ACL: phân quyền theo topic --------------------------------------------
# - gateway: toàn quyền iot/#
# - mỗi node (username = node id): chỉ pub nodes/<id> & ack/<id>, sub cmd/<id>
echo ">> Ghi ACL: $ACL_FILE"
sudo tee "$ACL_FILE" >/dev/null <<'EOF'
# Gateway: toan quyen
user gateway
topic readwrite iot/#

# Moi node (username = node id) chi thao tac tren topic cua chinh no.
# %u = username. Node KHONG the doc/ghi topic cua node khac.
pattern write iot/nodes/%u
pattern write iot/ack/%u
pattern read  iot/cmd/%u
EOF

# 3) Cấu hình broker --------------------------------------------------------
echo ">> Ghi cau hinh: $CONF"
{
  echo "# --- Bao mat co ban ---"
  echo "allow_anonymous false"
  echo "password_file $PW_FILE"
  echo "acl_file $ACL_FILE"
  echo "persistence true"
  echo "persistence_location /var/lib/mosquitto/"
  echo ""
  echo "# Listener khong TLS (LAN tin cay) - bo neu chi dung TLS"
  echo "listener 1883 127.0.0.1"
} | sudo tee "$CONF" >/dev/null

if [[ "${ENABLE_TLS:-0}" == "1" ]]; then
  echo ">> Bat listener TLS 8883..."
  sudo mkdir -p /etc/mosquitto/certs
  sudo cp "$REPO_DIR/certs/ca.crt" "$REPO_DIR/certs/broker.crt" \
          "$REPO_DIR/certs/broker.key" /etc/mosquitto/certs/
  sudo chown mosquitto:mosquitto /etc/mosquitto/certs/*
  sudo chmod 600 /etc/mosquitto/certs/broker.key
  sudo tee -a "$CONF" >/dev/null <<'EOF'

# --- Listener TLS ---
listener 8883
cafile   /etc/mosquitto/certs/ca.crt
certfile /etc/mosquitto/certs/broker.crt
keyfile  /etc/mosquitto/certs/broker.key
tls_version tlsv1.2
# require_certificate true   # bo comment de bat buoc mTLS (client phai co cert)
EOF
fi

echo ">> Khoi dong lai Mosquitto..."
sudo systemctl enable mosquitto
sudo systemctl restart mosquitto
sudo systemctl --no-pager status mosquitto | head -n 5

echo ""
echo ">> XONG. Buoc tiep theo:"
echo "   1) Dat bien moi truong cho gateway (xem .env.example):"
echo "      export LOCAL_MQTT_USER=gateway LOCAL_MQTT_PASS='<mat khau gateway>'"
echo "   2) Firmware node: dat MQTT_USER = node id (vd 'node-01') + mat khau tuong ung."
echo "   3) Thong tin dang nhap day du: $CRED_OUT"
