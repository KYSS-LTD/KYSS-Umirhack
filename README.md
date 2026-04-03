# KYSSCHECK

KYSSCHECK — защищённая распределённая система диагностики инфраструктуры (backend + агенты).

## Что реализовано
- FastAPI backend (stateless), PostgreSQL, Redis, Celery worker.
- Пользовательская аутентификация через JWT.
- Аутентификация агентов через `Authorization: Bearer <agent_token>`.
- Ed25519 подписи агентов сохранены и поддерживаются опционально (если агент отправляет подпись).
- Replay защита (`timestamp` + `nonce` Redis), rate limit, HTTPS enforcement, security headers.
- Безопасное выполнение задач агентом: whitelist типов задач + whitelist команд для `run_command`.
- Русскоязычный UI: список агентов, карточка агента, список задач, создание задач, просмотр результатов/логов.

## Быстрый запуск
```bash
cp .env.example .env
# укажите безопасные JWT_SECRET и REGISTRATION_TOKEN
# укажите DOMAIN и EMAIL

docker-compose up --build
```

## HTTPS через Nginx (автоматически)
Система расширена reverse proxy на Nginx:
- `80` -> redirect на `443`
- `443` -> TLS termination + proxy в `backend:8000`
- сертификаты и challenge-файлы хранятся в docker volumes (`certs`, `certbot_webroot`)

### Режимы сертификатов
1. **Dev / локально** (`DOMAIN=localhost` или без публичной зоны):
   - автоматически генерируется self-signed сертификат при старте Nginx.
2. **Production** (публичный домен, например `DOMAIN=monitor.example.com`):
   - `certbot_init` автоматически запрашивает Let's Encrypt сертификат (`EMAIL` обязателен).
   - `certbot_renew` выполняет периодическое обновление сертификатов.

> Для production домен должен указывать на сервер, а порты 80/443 должны быть доступны извне.

## Переменные окружения
- `DATABASE_URL`
- `REDIS_URL`
- `JWT_SECRET`
- `REGISTRATION_TOKEN`
- `JWT_ACCESS_TTL_MINUTES`
- `ALLOWED_COMMANDS`
- `ALLOWED_TASK_TYPES`
- `AGENT_OFFLINE_SECONDS`
- `DOMAIN`
- `EMAIL`
- `CORS_ORIGINS`

## Регистрация и запуск агента
### Вариант 1 (скрипт установки)
```bash
BASE_URL=https://your-domain-or-host REGISTRATION_TOKEN=... bash scripts/install.sh
```

### Вариант 2 (ручной запуск)
```bash
python agent/agent.py --base-url https://your-domain-or-host --registration-token YOUR_TOKEN
```

При регистрации backend выдаёт:
- `agent_id`
- `agent_token`

Агент сохраняет их в `~/.agent/config.json`.

### Примечание для self-signed (dev)
Если используется self-signed сертификат, Python-агенту может понадобиться отключить TLS verification (`verify=False`) или использовать доверенный локальный CA сертификат.

## API (основное)
- `POST /api/auth/login` — JWT логин пользователя.
- `POST /api/agents/register` — регистрация агента по `registration_token`.
- `POST /api/agents/heartbeat` — heartbeat агента (Bearer token + опциональная Ed25519 подпись).
- `POST /api/agents/tasks/next` — получение задачи агентом.
- `POST /api/tasks/result` — отправка результата задачи агентом.
- `POST /api/tasks` — создание задачи пользователем (JWT).

## Поддерживаемые типы задач
- `check_cpu`
- `check_ram`
- `check_disk`
- `check_ports`
- `check_system_info`
- `run_command` (только из whitelist `ALLOWED_COMMANDS`)

## Надёжность
- heartbeat каждые 5–10 сек;
- агент помечается offline при отсутствии heartbeat;
- базовый retry задачи при fail (`max_retries=1` по умолчанию);
- timeout выполнения задач на агенте.
