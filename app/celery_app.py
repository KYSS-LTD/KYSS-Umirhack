from celery import Celery
from app.core.config import get_settings

settings = get_settings()
celery_app = Celery('kysscheck', broker=settings.redis_url, backend=settings.redis_url)


@celery_app.task(name='kysscheck.ping')
def ping_task():
    return 'pong'
