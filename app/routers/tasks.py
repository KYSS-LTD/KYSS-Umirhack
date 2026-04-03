from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.models import TaskStatus
from app.repositories.repositories import create_task, get_task_by_uid
from app.schemas.agent import SignedEnvelope
from app.schemas.task import TaskCreateRequest
from app.services.auth_services import get_current_user
from app.services.rate_limit import limit_request
from app.services.security_services import verify_agent_signature

router = APIRouter(prefix='/api/tasks', tags=['tasks'])
settings = get_settings()


@router.post('')
def create_task_endpoint(payload: TaskCreateRequest, request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    limit_request(request, scope='task-create', limit=60)
    if payload.task_type == 'run_command' and payload.command not in settings.allowed_command_set:
        raise HTTPException(status_code=400, detail='Команда не входит в белый список')
    task = create_task(db, payload.task_uid, payload.task_type, payload.command)
    return {'task_uid': task.task_uid, 'status': task.status.value}


@router.post('/result')
def submit_result(envelope: SignedEnvelope, request: Request, db: Session = Depends(get_db)):
    limit_request(request, scope=f'task-result:{envelope.agent_uid}', limit=120)
    verify_agent_signature(db, envelope.agent_uid, envelope.payload, envelope.timestamp, envelope.signature, envelope.nonce)
    task_uid = envelope.payload.get('task_uid')
    task = get_task_by_uid(db, task_uid)
    if not task:
        raise HTTPException(status_code=404, detail='Задача не найдена')
    new_status = envelope.payload.get('status', 'failed')
    task.status = TaskStatus.done if new_status == 'done' else TaskStatus.failed
    task.result = str(envelope.payload.get('result', ''))[:4000]
    db.commit()
    return {'status': 'ok'}
