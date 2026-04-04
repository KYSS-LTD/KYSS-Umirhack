# Agent package (standalone)

Этот пакет можно **скопировать на сервер целиком** и запустить агент одной командой Docker Compose.

## 1) Подготовка
```bash
cp .env.example .env
# заполните BASE_URL и REGISTRATION_TOKEN
```

## 2) Запуск
```bash
docker compose up -d --build
```

## 3) Проверка логов
```bash
docker compose logs -f kyss-agent
```

## Что сделано для безопасности
- контейнер запущен от non-root пользователя;
- read-only root filesystem;
- отдельный volume `/agent-data` только для ключей и config;
- `no-new-privileges`, `cap_drop: [ALL]`, `pids_limit`, лимиты CPU/RAM;
- TLS verification включена по умолчанию (`VERIFY_TLS=true`).

## Обновление
```bash
docker compose pull && docker compose up -d
```
(или `--build`, если пакет изменён локально)
