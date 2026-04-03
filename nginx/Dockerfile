FROM nginx:1.27-alpine

RUN apk add --no-cache openssl gettext

COPY nginx.conf.template /etc/nginx/templates/nginx.conf.template
COPY nginx-entrypoint.sh /nginx-entrypoint.sh
RUN chmod +x /nginx-entrypoint.sh

ENTRYPOINT ["/nginx-entrypoint.sh"]
