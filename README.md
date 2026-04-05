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

После старта:
- dev ( `DOMAIN=localhost` или IP): `http://localhost`, `http://localhost:8000`, `https://localhost`
- production (домен): `https://<DOMAIN>`


## Docker runtime hardening и readiness
- Backend и Celery ждут готовности `postgres:5432` и `redis:6379` перед запуском (`scripts/wait_for_services.py`).
- Добавлены healthcheck для PostgreSQL и Redis в `docker-compose.yml`.
- Python-контейнер (backend/worker) запускается не от root, а от пользователя `appuser` (UID 10001).

## HTTPS через Nginx (автоматически)
Система расширена reverse proxy на Nginx:
- `80` -> redirect на `443`
- `443` -> TLS termination + proxy в `backend:8000`
- сертификаты и challenge-файлы хранятся в docker volumes (`certs`, `certbot_webroot`)

### Режимы сертификатов
1. **Dev / локально/IP** (`DOMAIN=localhost`, IP или любой непубличный хост):
   - Nginx проксирует backend на `80` и `8000` (HTTP) и поднимает `443` с self-signed сертификатом для локального HTTPS.
2. **Production** (публичный домен, например `DOMAIN=monitor.example.com`):
   - Nginx поднимает HTTPS на `443` и делает redirect с `80`.
   - если сертификата ещё нет, временно создаётся self-signed сертификат, чтобы сервис стартовал.
   - `certbot_init` запрашивает Let's Encrypt сертификат (`EMAIL` обязателен), `certbot_renew` выполняет обновления.

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

## Запуск агента как переносимого Docker-пакета (рекомендуется)
Чтобы запустить агента на отдельном сервере, теперь можно просто скопировать папку `deploy/agent-package`.

```bash
# на сервере агента
cp -r deploy/agent-package /opt/kyss-agent
cd /opt/kyss-agent
cp .env.example .env
# заполните BASE_URL и REGISTRATION_TOKEN

docker compose up -d --build
```

Логи агента:
```bash
docker compose logs -f kyss-agent
```

> Папка `agent/` теперь автономна: её можно вынести отдельно на хост (без кода backend) и запускать агент как самостоятельный компонент.

В составе `deploy/agent-package` Docker-образ теперь включает диагностические утилиты (`uptime/free`, `iproute2`, `ping`, `dnsutils`, `curl`), чтобы задачи агента не падали из-за отсутствия системных инструментов.

## Регистрация и запуск агента
### Вариант 1 (скрипт установки)
```bash
BASE_URL=https://your-domain-or-host REGISTRATION_TOKEN=... bash scripts/install.sh
```

### Вариант 2 (ручной запуск)
```bash
python agent/agent.py --base-url https://your-domain-or-host --registration-token YOUR_TOKEN --log-level INFO
```

Опционально: `--verify-tls false` только для локального self-signed окружения.

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
- `POST /api/integrations/tasks` — запуск задач из внешних систем по `X-Integration-Key`.
- `GET /api/tasks/export?format=json|csv|pdf&limit=500` — экспорт результатов задач (JWT, права просмотра).
- `GET /api/metrics/agents` — метрики по агентам (запуски за 24ч, ошибки, средняя длительность).
- `GET /api/tasks/diff?first_uid=...&second_uid=...` — сравнение результатов двух запусков по unified diff.

## Telegram интеграция (опционально)
- Для администратора доступна страница `/settings/telegram`:
  - `bot_token` бота;
  - `chat_id` группы;
  - `thread_id` (опционально, для групп с topics);
  - переключатель дублирования `online/offline` событий.
- Когда бот добавлен в группу, команда `/start` или `/chatid` покажет `chat_id`, который нужно вставить в настройки.
- Команды бота:
  - `/menu` — открыть главное инлайн-меню действий;
  - `/run` — инлайн-меню: выбор агента и затем типа проверки;
  - `/probe_offline` — поставить heartbeat-пробу для offline агентов (задачи выполнятся при восстановлении heartbeat);
  - `/events_on` и `/events_off` — включить/выключить дублирование событий в чат.
- При включённом дублировании в чат отправляются: события `online/offline` и завершение проверок (`done/failed`).
- Backend автоматически ставит периодические `check_system_info` пробы для offline агентов (с cooldown), чтобы сразу проверить их после восстановления heartbeat.

## Поддерживаемые типы задач
- `check_cpu`
- `check_ram`
- `check_disk`
- `check_ports`
- `check_system_info`
- `run_command` (только из whitelist `ALLOWED_COMMANDS`, без shell и только trusted binaries)

## Надёжность
- heartbeat каждые 5–10 сек;
- агент помечается offline при отсутствии heartbeat;
- при потере сети агент автоматически продолжает retry и восстанавливается после возвращения сети;
- при `401 Unauthorized` агент сам перерегистрируется и обновляет `agent_token`;
- базовый retry задачи при fail (`max_retries=1` по умолчанию);
- timeout выполнения задач на агенте.
- ограничение параллельных задач на одном агенте (`AGENT_MAX_PARALLEL_TASKS`, по умолчанию 1).
- в дашборде отображается рейтинг агентов по стабильности и скорости выполнения.
- пресеты ролей пользователей в UI: `observer`, `operator`, `administrator`.
- поддерживаются группы агентов (сегмент/площадка) через профиль агента и фильтр по группе в дашборде.

## Новые task types (итерация N)
### Системные
- `check_cpu_advanced`
- `check_memory_advanced`
- `check_disk_advanced`
- `check_processes_top`
- `check_uptime_reboot`

### Сеть
- `check_network_reachability`
- `check_ports_latency`
- `check_dns`
- `check_traceroute_basic`

### Сервисы/интеграции
- `check_services_status`
- `check_http_endpoint`
- `check_database_connectivity`

### Security/Snapshot/Диагностика
- `check_security_baseline`
- `system_snapshot`
- `system_snapshot_diff`
- `check_logs_keywords`
- `check_paths_sizes`

## Примеры payload для новых задач
```json
{
  "task_uid": "cpu-adv-001",
  "task_type": "check_cpu_advanced",
  "agent_uid": "agent-1"
}
```

```json
{
  "task_uid": "http-001",
  "task_type": "check_http_endpoint",
  "command": "{\"url\":\"https://example.com/health\",\"timeout\":3,\"verify_tls\":true}",
  "agent_uid": "agent-1"
}
```

```json
{
  "task_uid": "snapshot-diff-001",
  "task_type": "system_snapshot_diff",
  "command": "{\"snapshot_dir\":\"/root/.agent/snapshots\"}",
  "agent_uid": "agent-1"
}
```

## Changelog (что было / что стало)
- Было: только базовые проверки (`check_cpu/check_ram/check_disk/check_ports/check_system_info`) и статичная схема топологии.
- Стало: расширенные системные/сетевые/service/security/snapshot-проверки, JSON summary (`OK/WARN/CRIT`), diff состояния, polling топологии каждые 4 секунды с heartbeat-анимацией.
