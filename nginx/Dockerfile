FROM nginx:1.27-alpine

# openssl нужен для fallback self-signed сертификата
RUN apk add --no-cache bash openssl

COPY nginx-entrypoint.sh /nginx-entrypoint.sh
RUN chmod +x /nginx-entrypoint.sh

ENTRYPOINT ["/nginx-entrypoint.sh"]
