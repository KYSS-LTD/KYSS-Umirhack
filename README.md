# KYSSCHECK

KYSSCHECK — защищённая распределённая система диагностики инфраструктуры:
- **Backend**: FastAPI (stateless), PostgreSQL, Redis, Celery
- **Agent**: внешний клиент с подписью запросов Ed25519
- **UI**: русскоязычная панель мониторинга

## Ключевая безопасность
- Разделение аутентификации: агенты (Ed25519), пользователи (JWT)
- Canonical JSON + `*timestamp` для подписи
- Защита от replay (30 сек + nonce в Redis)
- Только HTTPS (HTTP отклоняется)
- Заголовки: HSTS, X-Frame-Options, X-Content-Type-Options
- Белый список команд для `run_command`
- Rate limiting через Redis
- Маскирование и ограничение выводов (до 4000 символов)

## Быстрый запуск
```bash
cp .env.example .env
# ВАЖНО: задайте безопасные JWT_SECRET и REGISTRATION_TOKEN

docker-compose up --build
```

## Переменные окружения
- `DATABASE_URL`
- `REDIS_URL`
- `JWT_SECRET`
- `REGISTRATION_TOKEN`
- `JWT_ACCESS_TTL_MINUTES`
- `ALLOWED_COMMANDS`

## Основные маршруты
- `POST /api/auth/login`
- `POST /api/agents/register`
- `POST /api/agents/heartbeat`
- `POST /api/agents/tasks/next`
- `POST /api/tasks`
- `POST /api/tasks/result`
- `GET /` — UI (русский интерфейс)

## Агент
### Установка (вариант 1)
```bash
BASE_URL=https://your-server REGISTRATION_TOKEN=... bash scripts/install.sh
```

### Ручной запуск
```bash
python agent/agent.py --base-url https://your-server --registration-token YOUR_TOKEN
```

## Модель задач
Типы:
- `check_cpu`
- `check_ram`
- `check_disk`
- `check_service`
- `run_command` (строго из whitelist)

Статусы: `pending -> assigned -> running -> done/failed`

## Security checklist
- [x] HTTPS enforced
- [x] Agent request signing
- [x] JWT for users
- [x] No unsafe shell execution pattern (`shell=True` не используется)
- [x] Rate limiting
- [x] Replay protection
- [x] Revocable agents
- [x] Stateless backend
