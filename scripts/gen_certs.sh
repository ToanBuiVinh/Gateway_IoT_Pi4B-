#!/usr/bin/env bash
# Sinh chứng chỉ TLS tự ký cho broker cục bộ (Mosquitto) + mTLS cho gateway/node.
# Dùng cho môi trường tự quản (LAN). Với cloud thật, dùng CA của nhà cung cấp.
#
#   bash scripts/gen_certs.sh [BROKER_CN]
# BROKER_CN = IP hoặc hostname của Pi mà client sẽ kết nối (mặc định: raspberrypi.local)
set -euo pipefail

CERT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/certs"
BROKER_CN="${1:-raspberrypi.local}"
DAYS=3650
mkdir -p "$CERT_DIR"
cd "$CERT_DIR"

echo ">> Thu muc chung chi: $CERT_DIR"
echo ">> Broker CN/hostname: $BROKER_CN"

# 1) CA nội bộ ------------------------------------------------------------
if [[ ! -f ca.key ]]; then
  openssl genrsa -out ca.key 4096
  openssl req -x509 -new -nodes -key ca.key -sha256 -days "$DAYS" \
    -subj "/O=IoT-Gateway/CN=IoT-Gateway-CA" -out ca.crt
  echo ">> Da tao CA: ca.crt"
fi

# 2) Chứng chỉ SERVER cho broker -----------------------------------------
openssl genrsa -out broker.key 2048
openssl req -new -key broker.key -subj "/O=IoT-Gateway/CN=${BROKER_CN}" -out broker.csr
# SAN để client kiểm tra hostname đúng chuẩn
cat > broker.ext <<EOF
subjectAltName = DNS:${BROKER_CN}, DNS:localhost, IP:127.0.0.1
extendedKeyUsage = serverAuth
EOF
openssl x509 -req -in broker.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out broker.crt -days "$DAYS" -sha256 -extfile broker.ext
rm -f broker.csr broker.ext
echo ">> Da tao chung chi broker: broker.crt / broker.key"

# 3) Chứng chỉ CLIENT cho gateway (mTLS, tuỳ chọn) -----------------------
openssl genrsa -out gateway-client.key 2048
openssl req -new -key gateway-client.key \
  -subj "/O=IoT-Gateway/CN=gateway" -out gateway-client.csr
echo "extendedKeyUsage = clientAuth" > client.ext
openssl x509 -req -in gateway-client.csr -CA ca.crt -CAkey ca.key -CAcreateserial \
  -out gateway-client.crt -days "$DAYS" -sha256 -extfile client.ext
rm -f gateway-client.csr client.ext
echo ">> Da tao chung chi client gateway: gateway-client.crt / gateway-client.key"

chmod 600 ./*.key
echo ""
echo ">> XONG. Cac file trong $CERT_DIR:"
ls -1 "$CERT_DIR"
echo ""
echo ">> Broker Mosquitto dung: ca.crt, broker.crt, broker.key"
echo ">> Gateway (TLS 1 chieu) dung: certs/ca.crt (tls_ca_cert)"
echo ">> Gateway (mTLS) them: certs/gateway-client.crt + certs/gateway-client.key"
echo ">> LUU Y: thu muc certs/ da duoc .gitignore — KHONG commit khoa rieng (*.key)!"
