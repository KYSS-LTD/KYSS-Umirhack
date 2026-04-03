import base64
import json
import time

import nacl.encoding
import nacl.signing
import redis
from fastapi import HTTPException, status

from app.core.config import get_settings
from app.repositories.repositories import get_agent_by_uid

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


def verify_agent_signature(db, agent_uid: str, payload: dict, timestamp: int, signature_b64: str, nonce: str | None = None) -> None:
    agent = get_agent_by_uid(db, agent_uid)
    if not agent or agent.revoked:
        raise HTTPException(status_code=401, detail='Агент не найден или отозван')

    enforce_fresh_request(timestamp, nonce)

    message = json.dumps(payload, sort_keys=True, separators=(',', ':')) + f'*{timestamp}'
    verify_key = nacl.signing.VerifyKey(agent.public_key, encoder=nacl.encoding.Base64Encoder)
    signature = base64.b64decode(signature_b64)
    try:
        verify_key.verify(message.encode('utf-8'), signature)
    except Exception as exc:
        raise HTTPException(status_code=401, detail='Неверная подпись') from exc
