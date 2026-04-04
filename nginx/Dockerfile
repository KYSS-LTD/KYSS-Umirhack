FROM nginx:1.27-alpine

# bash + openssl: runtime generation of nginx config and temporary self-signed cert
RUN apk add --no-cache bash openssl

COPY nginx-entrypoint.sh /nginx-entrypoint.sh
# protect against CRLF in git checkout (common on Windows/WSL hosts)
RUN sed -i 's/\r$//' /nginx-entrypoint.sh && chmod +x /nginx-entrypoint.sh

ENTRYPOINT ["bash", "/nginx-entrypoint.sh"]
