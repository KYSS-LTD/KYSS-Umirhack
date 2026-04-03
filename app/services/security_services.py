import base64
import json
import time

import nacl.encoding
import nacl.signing
import redis
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.models import Agent
from app.repositories.repositories import get_agent_by_token, get_agent_by_uid

settings = get_settings()
redis_client = redis.from_url(settings.redis_url, decode_responses=True)


def enforce_fresh_request(timestamp: int, nonce: str | None = None) -> None:
    now = int(time.time())
    if abs(now - timestamp) > 30:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Просроченный запрос агента')
    if nonce:
        key = f'nonce:{nonce}'
        if redis_client.get(key):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail='Обнаружен replay')
        redis_client.setex(key, 40, '1')


def verify_agent_signature_if_present(agent: Agent, payload: dict, timestamp: int | None, signature_b64: str | None, nonce: str | None = None) -> None:
    if not signature_b64:
        return
    if timestamp is None:
        raise HTTPException(status_code=401, detail='Для подписи требуется timestamp')
    enforce_fresh_request(timestamp, nonce)

    message = json.dumps(payload, sort_keys=True, separators=(',', ':')) + f'*{timestamp}'
    verify_key = nacl.signing.VerifyKey(agent.public_key, encoder=nacl.encoding.Base64Encoder)
    signature = base64.b64decode(signature_b64)
    try:
        verify_key.verify(message.encode('utf-8'), signature)
    except Exception as exc:
        raise HTTPException(status_code=401, detail='Неверная подпись') from exc


def get_agent_from_bearer(
    authorization: str = Header(default=''),
    db: Session = Depends(get_db),
) -> Agent:
    if not authorization.lower().startswith('bearer '):
        raise HTTPException(status_code=401, detail='Отсутствует Bearer agent_token')
    token = authorization.split(' ', 1)[1].strip()
    agent = get_agent_by_token(db, token)
    if not agent or agent.revoked:
        raise HTTPException(status_code=401, detail='Неверный agent_token')
    return agent


def get_agent_and_validate_uid(db: Session, bearer_agent: Agent, envelope_agent_uid: str) -> Agent:
    if bearer_agent.agent_uid != envelope_agent_uid:
        db_agent = get_agent_by_uid(db, envelope_agent_uid)
        if not db_agent or db_agent.id != bearer_agent.id:
            raise HTTPException(status_code=401, detail='agent_uid не соответствует токену')
    return bearer_agent
