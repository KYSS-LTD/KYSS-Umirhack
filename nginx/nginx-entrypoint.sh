#!/usr/bin/env bash
set -eu

: "${DOMAIN:=localhost}"

is_public_domain="false"
if [[ "$DOMAIN" == "localhost" ]]; then
  is_public_domain="false"
elif [[ "$DOMAIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  is_public_domain="false"
elif [[ "$DOMAIN" =~ \. ]]; then
  is_public_domain="true"
fi

mkdir -p /etc/nginx/conf.d

if [[ "$is_public_domain" == "true" ]]; then
  cert_dir="/certs/live/${DOMAIN}"
  cert_file="${cert_dir}/fullchain.pem"
  key_file="${cert_dir}/privkey.pem"

  if [[ ! -f "$cert_file" || ! -f "$key_file" ]]; then
    echo "[nginx-entrypoint] No TLS certs for ${DOMAIN}; creating temporary self-signed certificate."
    mkdir -p "$cert_dir"
    openssl req -x509 -nodes -newkey rsa:2048 -days 7 \
      -subj "/CN=${DOMAIN}" \
      -keyout "$key_file" \
      -out "$cert_file"
  fi

  cat > /etc/nginx/conf.d/default.conf <<NGINX_CONF
server {
    listen 80;
    server_name ${DOMAIN};

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    server_name ${DOMAIN};

    ssl_certificate ${cert_file};
    ssl_certificate_key ${key_file};
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;

    add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
    add_header X-Frame-Options "DENY" always;
    add_header X-Content-Type-Options "nosniff" always;

    client_max_body_size 5m;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_connect_timeout 30s;
        proxy_read_timeout 60s;
    }
}
NGINX_CONF
else
  echo "[nginx-entrypoint] DOMAIN=${DOMAIN} is local/IP; starting dev reverse proxy on ports 80, 443 and 8000."

  cert_dir="/certs/local"
  cert_file="${cert_dir}/fullchain.pem"
  key_file="${cert_dir}/privkey.pem"
  if [[ ! -f "$cert_file" || ! -f "$key_file" ]]; then
    mkdir -p "$cert_dir"
    openssl req -x509 -nodes -newkey rsa:2048 -days 365 \
      -subj "/CN=localhost" \
      -keyout "$key_file" \
      -out "$cert_file"
  fi

  cat > /etc/nginx/conf.d/default.conf <<NGINX_CONF
server {
    listen 80;
    listen 8000;
    server_name _;

    client_max_body_size 5m;

    location / {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_connect_timeout 30s;
        proxy_read_timeout 60s;
    }
}

server {
    listen 443 ssl http2;
    server_name _;

    ssl_certificate ${cert_file};
    ssl_certificate_key ${key_file};
    ssl_protocols TLSv1.2 TLSv1.3;

    client_max_body_size 5m;

    location / {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_connect_timeout 30s;
        proxy_read_timeout 60s;
    }
}
NGINX_CONF
fi

nginx -t
exec nginx -g 'daemon off;'
