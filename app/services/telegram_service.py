import asyncio
import uuid
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.models.models import Agent, Task, TaskStatus, TelegramIntegrationSettings

settings = get_settings()


class TelegramService:
    def __init__(self):
        self._offset = 0
        self._prepared_token: str | None = None

    @staticmethod
    def get_or_create_config(db: Session) -> TelegramIntegrationSettings:
        cfg = db.query(TelegramIntegrationSettings).first()
        if cfg:
            return cfg
        cfg = TelegramIntegrationSettings()
        db.add(cfg)
        db.commit()
        db.refresh(cfg)
        return cfg

    @staticmethod
    async def send_message(bot_token: str, chat_id: str, text: str, message_thread_id: int | None = None) -> None:
        if not bot_token or not chat_id:
            return
        url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
        payload = {'chat_id': chat_id, 'text': text}
        if isinstance(message_thread_id, int):
            payload['message_thread_id'] = message_thread_id
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                await client.post(url, json=payload)
        except Exception:
            return

    @staticmethod
    def _fmt_event(event_type: str, agent_uid: str, details: str | None) -> str:
        ts = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        details_text = f' ({details})' if details else ''
        icon = '🟢' if event_type == 'online' else '🔴' if event_type == 'offline' else 'ℹ️'
        return f'{icon} [{ts}] Агент {agent_uid}: {event_type}{details_text}'

    async def notify_agent_event(self, agent_uid: str, event_type: str, details: str | None = None) -> None:
        db = SessionLocal()
        try:
            cfg = self.get_or_create_config(db)
            if not (cfg.bot_token and cfg.chat_id and cfg.events_enabled):
                return
            await self.send_message(cfg.bot_token, cfg.chat_id, self._fmt_event(event_type, agent_uid, details))
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
                    '/run <task_type> [agent_uid] - запустить проверку'
                )
                await self.send_message(bot_token, chat_id, intro, message_thread_id=message_thread_id)
                return

            if command == '/chatid':
                await self.send_message(bot_token, chat_id, f'ID этого чата: {chat_id}', message_thread_id=message_thread_id)
                return

            if command == '/events_on':
                cfg.chat_id = chat_id
                cfg.events_enabled = True
                db.commit()
                await self.send_message(bot_token, chat_id, 'Дублирование событий включено для этого чата.', message_thread_id=message_thread_id)
                return

            if command == '/events_off':
                cfg.events_enabled = False
                db.commit()
                await self.send_message(bot_token, chat_id, 'Дублирование событий выключено.', message_thread_id=message_thread_id)
                return

            if command == '/run':
                parts = text.split()
                if len(parts) < 2:
                    await self.send_message(bot_token, chat_id, 'Использование: /run <task_type> [agent_uid]', message_thread_id=message_thread_id)
                    return
                task_type = parts[1].strip()
                if task_type not in settings.allowed_task_type_set:
                    await self.send_message(bot_token, chat_id, f'Недопустимый task_type: {task_type}', message_thread_id=message_thread_id)
                    return
                agent_uid = parts[2].strip() if len(parts) > 2 else ''
                if agent_uid:
                    agent = db.query(Agent).filter(Agent.agent_uid == agent_uid).first()
                    if not agent:
                        await self.send_message(bot_token, chat_id, f'Агент не найден: {agent_uid}', message_thread_id=message_thread_id)
                        return
                    db.add(Task(task_uid=uuid.uuid4().hex, task_type=task_type, command=None, status=TaskStatus.pending, agent_id=agent.id))
                    db.commit()
                    await self.send_message(bot_token, chat_id, f'Задача {task_type} поставлена для агента {agent_uid}.', message_thread_id=message_thread_id)
                    return
                agents = db.query(Agent).all()
                if not agents:
                    await self.send_message(bot_token, chat_id, 'Нет зарегистрированных агентов.', message_thread_id=message_thread_id)
                    return
                for agent in agents:
                    db.add(Task(task_uid=uuid.uuid4().hex, task_type=task_type, command=None, status=TaskStatus.pending, agent_id=agent.id))
                db.commit()
                await self.send_message(bot_token, chat_id, f'Задача {task_type} поставлена для {len(agents)} агентов.', message_thread_id=message_thread_id)
                return
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
