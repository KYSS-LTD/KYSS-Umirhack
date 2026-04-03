#!/bin/sh
set -e

: "${DOMAIN:=localhost}"

if [ "$DOMAIN" = "localhost" ] || ! echo "$DOMAIN" | grep -q '\\.'; then
  echo "[certbot-renew] DOMAIN=$DOMAIN looks local; renewal loop skipped."
  tail -f /dev/null
fi

while true; do
  certbot renew --webroot -w /var/www/certbot --quiet || true
  sleep 12h
done
