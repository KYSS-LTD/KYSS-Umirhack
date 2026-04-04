from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.models import Agent, TaskStatus
from app.repositories.repositories import (
    create_task,
    ensure_user_access,
    fail_running_tasks_for_offline_agents,
    fail_stale_running_tasks,
    get_agent_by_uid,
    get_task_by_uid,
    mark_offline_agents,
)
from app.schemas.agent import SignedEnvelope
from app.schemas.task import TaskCreateRequest
from app.services.auth_services import get_current_user
from app.services.rate_limit import limit_request
from app.services.security_services import get_agent_and_validate_uid, get_agent_from_bearer, verify_agent_signature_if_present

router = APIRouter(tags=['tasks'])
settings = get_settings()


@router.post('/api/tasks')
def create_task_endpoint(payload: TaskCreateRequest, request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    limit_request(request, scope='task-create', limit=60)
    access = ensure_user_access(db, current_user)
    if not (access.is_admin or access.can_create_tasks):
        raise HTTPException(status_code=403, detail='Недостаточно прав на создание задач')
    if payload.task_type not in settings.allowed_task_type_set:
        raise HTTPException(status_code=400, detail='Недопустимый тип задачи')
    if payload.task_type == 'run_command' and payload.command not in settings.allowed_command_set:
        raise HTTPException(status_code=400, detail='Команда не входит в белый список')
    mark_offline_agents(db, offline_seconds=settings.agent_offline_seconds)
    fail_running_tasks_for_offline_agents(db)
    fail_stale_running_tasks(db, timeout_seconds=settings.task_execution_timeout_seconds)
    target_agent_id = None
    if payload.agent_uid:
        agent = get_agent_by_uid(db, payload.agent_uid)
        if not agent:
            raise HTTPException(status_code=404, detail='Агент не найден')
        target_agent_id = agent.id
    task = create_task(db, payload.task_uid, payload.task_type, payload.command, agent_id=target_agent_id)
    return {'task_uid': task.task_uid, 'status': task.status.value}


@router.post('/api/tasks/result')
def submit_result(
    envelope: SignedEnvelope,
    request: Request,
    db: Session = Depends(get_db),
    bearer_agent: Agent = Depends(get_agent_from_bearer),
):
    limit_request(request, scope=f'task-result:{bearer_agent.agent_uid}', limit=120)
    agent = get_agent_and_validate_uid(db, bearer_agent, envelope.agent_uid)
    verify_agent_signature_if_present(agent, envelope.payload, envelope.timestamp, envelope.signature, envelope.nonce)

    task_uid = envelope.payload.get('task_uid')
    task = get_task_by_uid(db, task_uid)
    if not task:
        raise HTTPException(status_code=404, detail='Задача не найдена')
    if task.agent_id and task.agent_id != agent.id:
        raise HTTPException(status_code=403, detail='Задача назначена другому агенту')
    if task.status != TaskStatus.running:
        return {'status': 'ignored', 'task_status': task.status.value, 'reason': 'task already finalized'}

    new_status = envelope.payload.get('status', 'failed')
    task.logs = str(envelope.payload.get('logs', envelope.payload.get('result', '')))[:8000]
    task.result = str(envelope.payload.get('result', ''))[:8000]
    task.finished_at = datetime.utcnow()

    if new_status == 'done':
        task.status = TaskStatus.done
    else:
        if task.retries < task.max_retries:
            task.retries += 1
            task.status = TaskStatus.pending
            task.result = 'retry scheduled'
            task.started_at = None
            task.finished_at = None
        else:
            task.status = TaskStatus.failed
    db.commit()
    return {'status': 'ok', 'task_status': task.status.value, 'retries': task.retries}
