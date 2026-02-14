#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-/home/polat/Desktop/Projects/drone_app/backend/certs/mqtt}"
CN="${2:-localhost}"

mkdir -p "$OUT_DIR"

cat > "$OUT_DIR/openssl.cnf" <<CONF
[req]
prompt = no
distinguished_name = dn
req_extensions = req_ext

[dn]
CN = ${CN}

[req_ext]
subjectAltName = @alt_names

[alt_names]
DNS.1 = ${CN}
DNS.2 = localhost
IP.1 = 127.0.0.1
CONF

# CA
openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$OUT_DIR/ca.key" \
  -out "$OUT_DIR/ca.crt" \
  -days 3650 \
  -subj "/CN=aegis-mqtt-ca"

# Server key + CSR
openssl req -newkey rsa:2048 -nodes \
  -keyout "$OUT_DIR/server.key" \
  -out "$OUT_DIR/server.csr" \
  -config "$OUT_DIR/openssl.cnf"

# Sign server cert with CA
openssl x509 -req \
  -in "$OUT_DIR/server.csr" \
  -CA "$OUT_DIR/ca.crt" \
  -CAkey "$OUT_DIR/ca.key" \
  -CAcreateserial \
  -out "$OUT_DIR/server.crt" \
  -days 3650 \
  -sha256 \
  -extensions req_ext \
  -extfile "$OUT_DIR/openssl.cnf"

rm -f "$OUT_DIR/server.csr" "$OUT_DIR/openssl.cnf" "$OUT_DIR/ca.srl"

echo "MQTT TLS certs generated:"
echo "  CA:     $OUT_DIR/ca.crt"
echo "  Server: $OUT_DIR/server.crt"
echo "  Key:    $OUT_DIR/server.key"
