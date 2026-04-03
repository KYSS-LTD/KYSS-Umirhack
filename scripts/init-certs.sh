#!/bin/sh
set -e

: "${DOMAIN:=localhost}"
: "${EMAIL:=admin@localhost}"

if [ "$DOMAIN" = "localhost" ] || ! echo "$DOMAIN" | grep -q '\\.'; then
  echo "[certbot-init] DOMAIN=$DOMAIN looks local; Let's Encrypt skipped."
  exit 0
fi

echo "[certbot-init] Requesting Let's Encrypt certificate for $DOMAIN"
certbot certonly \
  --webroot \
  -w /var/www/certbot \
  --email "$EMAIL" \
  --agree-tos \
  --non-interactive \
  --keep-until-expiring \
  -d "$DOMAIN"
