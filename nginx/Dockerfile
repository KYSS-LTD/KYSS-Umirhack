FROM nginx:1.27-alpine

# Устанавливаем bash, openssl и gettext
RUN apk add --no-cache bash openssl gettext

# Копируем конфиг-шаблон и entrypoint
COPY nginx.conf.template /etc/nginx/templates/nginx.conf.template
COPY nginx-entrypoint.sh /nginx-entrypoint.sh

# Делаем скрипт исполняемым
RUN chmod +x /nginx-entrypoint.sh

# Запуск через bash entrypoint
ENTRYPOINT ["/nginx-entrypoint.sh"]