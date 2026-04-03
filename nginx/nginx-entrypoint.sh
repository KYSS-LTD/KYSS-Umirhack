#!/usr/bin/env bash
set -eu

# Переменные окружения
: "${DOMAIN:=localhost}"
: "${EMAIL:=admin@localhost}"

# Если локальный домен, пропускаем Let's Encrypt
if [[ "$DOMAIN" == "localhost" ]] || ! [[ "$DOMAIN" =~ \. ]]; then
  echo "[certbot-init] DOMAIN=$DOMAIN looks local; Let's Encrypt skipped."
  exec nginx -g 'daemon off;'
fi

echo "[certbot-init] Requesting Let's Encrypt certificate for $DOMAIN"

# Создаём директорию для certbot, если нет
mkdir -p /var/www/certbot

# Запрос сертификата
certbot certonly \
  --webroot \
  -w /var/www/certbot \
  --email "$EMAIL" \
  --agree-tos \
  --non-interactive \
  --keep-until-expiring \
  -d "$DOMAIN"

# Запускаем nginx после получения сертификата
exec nginx -g 'daemon off;'