#!/usr/bin/env bash
set -euo pipefail

: "${DOMAIN:=localhost}"
CERT_DIR="/certs/live/${DOMAIN}"
mkdir -p /etc/nginx/conf.d /var/www/certbot "$CERT_DIR"

if [ ! -f "$CERT_DIR/fullchain.pem" ] || [ ! -f "$CERT_DIR/privkey.pem" ]; then
  echo "[nginx] No certificate found for ${DOMAIN}, generating self-signed fallback..."
  openssl req -x509 -nodes -newkey rsa:2048 -days 30 \
    -keyout "$CERT_DIR/privkey.pem" \
    -out "$CERT_DIR/fullchain.pem" \
    -subj "/CN=${DOMAIN}" >/dev/null 2>&1
fi

envsubst '${DOMAIN}' < /etc/nginx/templates/nginx.conf.template > /etc/nginx/conf.d/default.conf

echo "[nginx] Starting with domain: ${DOMAIN}"
exec nginx -g 'daemon off;'
