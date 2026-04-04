import asyncio
import uuid
from datetime import datetime

import httpx
from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal, engine
from app.models.models import Agent, AgentProfile, Task, TaskStatus, TelegramIntegrationSettings

settings = get_settings()


class TelegramService:
    def __init__(self):
        self._offset = 0
        self._prepared_token: str | None = None
        self._schema_checked = False

    def _ensure_schema(self) -> None:
        if self._schema_checked:
            return
        insp = inspect(engine)
        if 'telegram_integration_settings' not in insp.get_table_names():
            self._schema_checked = True
            return
        cols = {c['name'] for c in insp.get_columns('telegram_integration_settings')}
        if 'events_thread_id' not in cols:
            with engine.begin() as conn:
                conn.execute(text('ALTER TABLE telegram_integration_settings ADD COLUMN events_thread_id INTEGER'))
        self._schema_checked = True

    def get_or_create_config(self, db: Session) -> TelegramIntegrationSettings:
        self._ensure_schema()
        cfg = db.query(TelegramIntegrationSettings).first()
        if cfg:
            return cfg
        cfg = TelegramIntegrationSettings()
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
        return cfg

    @staticmethod
    async def send_message(
        bot_token: str,
        chat_id: str,
        text: str,
        message_thread_id: int | None = None,
        reply_markup: dict | None = None,
    ) -> bool:
        if not bot_token or not chat_id:
            return False
        url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
        payload = {'chat_id': chat_id, 'text': text}
        if isinstance(message_thread_id, int):
            payload['message_thread_id'] = message_thread_id
        if reply_markup:
            payload['reply_markup'] = reply_markup
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                response = await client.post(url, json=payload)
                data = response.json() if 'application/json' in response.headers.get('content-type', '') else {}
                return bool(response.status_code == 200 and data.get('ok'))
        except Exception:
            return False

    @staticmethod
    async def edit_message(
        bot_token: str,
        chat_id: str,
        message_id: int,
        text: str,
        reply_markup: dict | None = None,
    ) -> None:
        url = f'https://api.telegram.org/bot{bot_token}/editMessageText'
        payload = {'chat_id': chat_id, 'message_id': message_id, 'text': text}
        if reply_markup:
            payload['reply_markup'] = reply_markup
        async with httpx.AsyncClient(timeout=8.0) as client:
            await client.post(url, json=payload)

    @staticmethod
    async def answer_callback(bot_token: str, callback_query_id: str) -> None:
        url = f'https://api.telegram.org/bot{bot_token}/answerCallbackQuery'
        async with httpx.AsyncClient(timeout=8.0) as client:
            await client.post(url, json={'callback_query_id': callback_query_id})

    def reload_config(self) -> None:
        self._offset = 0
        self._prepared_token = None

    async def send_config_saved_message(self, bot_token: str, chat_id: str) -> None:
        await self.send_message(bot_token, chat_id, '✅ Настройки Telegram обновлены. Бот перезапущен и готов к работе.')

    @staticmethod
    def _fmt_event(event_type: str, agent_label: str, details: str | None) -> str:
        ts = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        details_text = f' ({details})' if details else ''
        icon = '🟢' if event_type == 'online' else '🔴' if event_type == 'offline' else 'ℹ️'
        return f'{icon} [{ts}] Агент {agent_label}: {event_type}{details_text}'

    @staticmethod
    def _resolve_agent_label(db: Session, agent_uid: str) -> str:
        agent = db.query(Agent).filter(Agent.agent_uid == agent_uid).first()
        if not agent:
            return agent_uid
        profile = db.query(AgentProfile).filter(AgentProfile.agent_id == agent.id).first()
        base = profile.custom_name if profile and profile.custom_name else agent.hostname
        return f'{base} ({agent.agent_uid})'

    async def notify_agent_event(self, agent_uid: str, event_type: str, details: str | None = None) -> None:
        db = SessionLocal()
        try:
            cfg = self.get_or_create_config(db)
            if not (cfg.bot_token and cfg.chat_id and cfg.events_enabled):
                return
            await self.send_message(
                cfg.bot_token,
                cfg.chat_id,
                self._fmt_event(event_type, self._resolve_agent_label(db, agent_uid), details),
                message_thread_id=cfg.events_thread_id,
            )
        finally:
            db.close()

    async def notify_task_result(
        self,
        agent_uid: str,
        task_uid: str,
        task_type: str,
        status: str,
        details: str | None = None,
    ) -> None:
        db = SessionLocal()
        try:
            cfg = self.get_or_create_config(db)
            if not (cfg.bot_token and cfg.chat_id and cfg.events_enabled):
                return
            icon = '✅' if status == 'done' else '❌'
            details_text = f'\nРезультат: {details[:500]}' if details else ''
            text = (
                f'{icon} Проверка завершена\n'
                f'Агент: {self._resolve_agent_label(db, agent_uid)}\n'
                f'Task: {task_uid}\n'
                f'Тип: {task_type}\n'
                f'Статус: {status}'
                f'{details_text}'
            )
            await self.send_message(cfg.bot_token, cfg.chat_id, text, message_thread_id=cfg.events_thread_id)
        finally:
            db.close()

    async def _handle_command(self, bot_token: str, message: dict) -> None:
        text = (message.get('text') or '').strip()
        chat = message.get('chat') or {}
        chat_id = str(chat.get('id', ''))
        message_thread_id = message.get('message_thread_id')
        if not text or not chat_id:
            return
        command = text.split()[0].split('@')[0].lower()

        db = SessionLocal()
        try:
            cfg = self.get_or_create_config(db)
            if command == '/start':
                intro = (
                    'KYSSCHECK bot активен.\n'
                    f'ID этого чата: {chat_id}\n'
                    'Команды:\n'
                    '/chatid - показать chat id\n'
                    '/events_on - включить дублирование событий\n'
                    '/events_off - выключить дублирование событий\n'
                    '/run - запустить проверку через инлайн-меню\n'
                    '/probe_offline - поставить heartbeat-пробу offline агентам'
                )
                await self.send_message(bot_token, chat_id, intro, message_thread_id=message_thread_id)
                return

            if command == '/chatid':
                await self.send_message(bot_token, chat_id, f'ID этого чата: {chat_id}', message_thread_id=message_thread_id)
                return

            if command == '/events_on':
                cfg.chat_id = chat_id
                cfg.events_thread_id = message_thread_id if isinstance(message_thread_id, int) else None
                cfg.events_enabled = True
                db.commit()
                await self.send_message(bot_token, chat_id, 'Дублирование событий включено для этого чата.', message_thread_id=message_thread_id)
                return

            if command == '/events_off':
                cfg.events_enabled = False
                cfg.events_thread_id = None
                db.commit()
                await self.send_message(bot_token, chat_id, 'Дублирование событий выключено.', message_thread_id=message_thread_id)
                return

            if command == '/run':
                agents = db.query(Agent).order_by(Agent.hostname.asc()).limit(20).all()
                if not agents:
                    await self.send_message(bot_token, chat_id, 'Нет зарегистрированных агентов.', message_thread_id=message_thread_id)
                    return
                keyboard = [
                    [{'text': f'{a.hostname} ({a.agent_uid[:8]})', 'callback_data': f'pick_agent:{a.id}'}]
                    for a in agents
                ]
                await self.send_message(
                    bot_token,
                    chat_id,
                    'Выберите агента:',
                    message_thread_id=message_thread_id,
                    reply_markup={'inline_keyboard': keyboard},
                )
                return

            if command == '/probe_offline':
                offline_agents = db.query(Agent).filter((Agent.is_online.is_(False)) | (Agent.revoked.is_(True))).all()
                if not offline_agents:
                    await self.send_message(bot_token, chat_id, 'Сейчас offline-агентов нет.', message_thread_id=message_thread_id)
                    return
                task_type = 'check_system_info' if 'check_system_info' in settings.allowed_task_type_set else sorted(settings.allowed_task_type_set)[0]
                created = 0
                for agent in offline_agents:
                    db.add(Task(task_uid=uuid.uuid4().hex, task_type=task_type, command=None, status=TaskStatus.pending, agent_id=agent.id))
                    created += 1
                db.commit()
                await self.send_message(
                    bot_token,
                    chat_id,
                    f'Поставил heartbeat-пробу для {created} offline агентов. Как только они включатся и пришлют heartbeat, задачи выполнятся.',
                    message_thread_id=message_thread_id,
                )
                return
        finally:
            db.close()

    async def _handle_callback_query(self, bot_token: str, callback_query: dict) -> None:
        callback_query_id = str(callback_query.get('id') or '')
        data = str(callback_query.get('data') or '')
        message = callback_query.get('message') or {}
        chat = message.get('chat') or {}
        chat_id = str(chat.get('id', ''))
        message_id = message.get('message_id')
        if not callback_query_id or not data or not chat_id or not isinstance(message_id, int):
            return
        await self.answer_callback(bot_token, callback_query_id)

        db = SessionLocal()
        try:
            if data.startswith('pick_agent:'):
                agent_id = int(data.split(':', 1)[1])
                agent = db.query(Agent).filter(Agent.id == agent_id).first()
                if not agent:
                    return
                keyboard = [
                    [{'text': task_type, 'callback_data': f'run_task:{agent.id}:{task_type}'}]
                    for task_type in sorted(settings.allowed_task_type_set)
                ]
                await self.edit_message(
                    bot_token,
                    chat_id,
                    message_id,
                    f'Агент: {agent.hostname} ({agent.agent_uid}). Выберите задачу:',
                    reply_markup={'inline_keyboard': keyboard[:20]},
                )
                return
            if data.startswith('run_task:'):
                _, agent_id_raw, task_type = data.split(':', 2)
                agent_id = int(agent_id_raw)
                agent = db.query(Agent).filter(Agent.id == agent_id).first()
                if not agent or task_type not in settings.allowed_task_type_set:
                    return
                db.add(Task(task_uid=uuid.uuid4().hex, task_type=task_type, command=None, status=TaskStatus.pending, agent_id=agent.id))
                db.commit()
                await self.edit_message(bot_token, chat_id, message_id, f'✅ Запущена задача {task_type} для {agent.hostname} ({agent.agent_uid}).')
        finally:
            db.close()

    async def _handle_member_update(self, bot_token: str, payload: dict) -> None:
        chat = payload.get('chat') or {}
        chat_id = str(chat.get('id', ''))
        if not chat_id:
            return
        old_status = ((payload.get('old_chat_member') or {}).get('status') or '').lower()
        new_status = ((payload.get('new_chat_member') or {}).get('status') or '').lower()
        if old_status in {'left', 'kicked'} and new_status in {'member', 'administrator'}:
            await self.send_message(
                bot_token,
                chat_id,
                f'Спасибо за добавление! ID этой группы: {chat_id}\n'
                'Вставьте его в настройки KYSSCHECK (/settings/telegram).',
            )

    async def _ensure_polling_ready(self, bot_token: str) -> None:
        if self._prepared_token == bot_token:
            return
        url = f'https://api.telegram.org/bot{bot_token}/deleteWebhook'
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json={'drop_pending_updates': False})
        self._offset = 0
        self._prepared_token = bot_token

    async def _poll_once(self, bot_token: str) -> None:
        await self._ensure_polling_ready(bot_token)
        url = f'https://api.telegram.org/bot{bot_token}/getUpdates'
        async with httpx.AsyncClient(timeout=25.0) as client:
            response = await client.get(url, params={'timeout': 20, 'offset': self._offset})
            data = response.json() if response.headers.get('content-type', '').startswith('application/json') else {}
            if not data.get('ok'):
                return
            for upd in data.get('result', []):
                upd_id = upd.get('update_id')
                if isinstance(upd_id, int):
                    self._offset = max(self._offset, upd_id + 1)
                message = upd.get('message') or upd.get('channel_post')
                if not message:
                    member_update = upd.get('my_chat_member')
                    if member_update:
                        await self._handle_member_update(bot_token, member_update)
                    callback_query = upd.get('callback_query')
                    if callback_query:
                        await self._handle_callback_query(bot_token, callback_query)
                    continue
                await self._handle_command(bot_token, message)

    async def polling_loop(self) -> None:
        while True:
            db = SessionLocal()
            try:
                cfg = self.get_or_create_config(db)
                bot_token = cfg.bot_token or ''
            finally:
                db.close()

            if not bot_token:
                await asyncio.sleep(5)
                continue
            try:
                await self._poll_once(bot_token)
            except Exception:
                await asyncio.sleep(5)


telegram_service = TelegramService()
