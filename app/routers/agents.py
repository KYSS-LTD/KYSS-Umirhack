import secrets
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.models import Agent
from app.repositories.repositories import create_or_update_agent, get_next_task_for_agent, mark_offline_agents, touch_agent
from app.schemas.agent import AgentRegisterRequest, SignedEnvelope
from app.services.rate_limit import limit_request
from app.services.security_services import get_agent_and_validate_uid, get_agent_from_bearer, verify_agent_signature_if_present

router = APIRouter(tags=['agents'])
settings = get_settings()


def _register(payload: AgentRegisterRequest, request: Request, db: Session):
    limit_request(request, scope='agent-register', limit=30)
    if payload.registration_token != settings.registration_token:
        raise HTTPException(status_code=403, detail='Неверный registration_token')
    agent_token = secrets.token_urlsafe(32)
    agent_uid = payload.agent_uid or secrets.token_hex(16)
    agent = create_or_update_agent(
        db,
        agent_uid=agent_uid,
        hostname=payload.hostname,
        public_key=payload.public_key,
        agent_token=agent_token,
    )
    return {'status': 'ok', 'agent_id': agent.agent_uid, 'agent_token': agent.agent_token}


@router.post('/api/agents/register')
@router.post('/agents/register')
def register_agent(payload: AgentRegisterRequest, request: Request, db: Session = Depends(get_db)):
    return _register(payload, request, db)


def _heartbeat(envelope: SignedEnvelope, request: Request, db: Session, bearer_agent: Agent):
    limit_request(request, scope=f'heartbeat:{bearer_agent.agent_uid}', limit=120)
    agent = get_agent_and_validate_uid(db, bearer_agent, envelope.agent_uid)
    verify_agent_signature_if_present(agent, envelope.payload, envelope.timestamp, envelope.signature, envelope.nonce)
    touch_agent(db, agent, payload=envelope.payload)
    mark_offline_agents(db, offline_seconds=settings.agent_offline_seconds)
    return {'status': 'alive', 'last_seen': datetime.utcnow().isoformat()}


@router.post('/api/agents/heartbeat')
@router.post('/agents/heartbeat')
def heartbeat(
    envelope: SignedEnvelope,
    request: Request,
    db: Session = Depends(get_db),
    bearer_agent: Agent = Depends(get_agent_from_bearer),
):
    return _heartbeat(envelope, request, db, bearer_agent)


@router.post('/api/agents/tasks/next')
@router.post('/agents/tasks/next')
def next_task(
    envelope: SignedEnvelope,
    request: Request,
    db: Session = Depends(get_db),
    bearer_agent: Agent = Depends(get_agent_from_bearer),
):
    limit_request(request, scope=f'tasks-next:{bearer_agent.agent_uid}', limit=120)
    agent = get_agent_and_validate_uid(db, bearer_agent, envelope.agent_uid)
    verify_agent_signature_if_present(agent, envelope.payload, envelope.timestamp, envelope.signature, envelope.nonce)
    task = get_next_task_for_agent(db, agent)
    if not task:
        return {'task': None}
    return {
        'task': {
            'task_uid': task.task_uid,
            'task_type': task.task_type,
            'command': task.command,
            'status': task.status.value,
        }
    }
