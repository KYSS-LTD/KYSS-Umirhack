import redis
from fastapi import HTTPException, Request

from app.core.config import get_settings

settings = get_settings()
redis_client = redis.from_url(settings.redis_url, decode_responses=True)


def limit_request(request: Request, scope: str, limit: int, window_sec: int = 60) -> None:
    ip = request.client.host if request.client else 'unknown'
    key = f'ratelimit:{scope}:{ip}'
    count = redis_client.incr(key)
    if count == 1:
        redis_client.expire(key, window_sec)
    if count > limit:
        raise HTTPException(status_code=429, detail='Слишком много запросов')
