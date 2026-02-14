#!/usr/bin/env bash
set -euo pipefail

OUT_DIR="${1:-/home/polat/Desktop/Projects/drone_app/backend/certs/opcua}"
CN="${2:-drone-opcua}"

mkdir -p "$OUT_DIR"

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$OUT_DIR/opcua_key.pem" \
  -out "$OUT_DIR/opcua_cert.pem" \
  -days 3650 \
  -subj "/CN=${CN}"

openssl x509 -outform der \
  -in "$OUT_DIR/opcua_cert.pem" \
  -out "$OUT_DIR/opcua_cert.der"

echo "OPC UA cert generated:"
echo "  Cert (DER): $OUT_DIR/opcua_cert.der"
echo "  Key  (PEM): $OUT_DIR/opcua_key.pem"
