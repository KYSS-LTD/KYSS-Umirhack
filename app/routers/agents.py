from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.repositories.repositories import get_next_task_for_agent, touch_agent, upsert_agent
from app.schemas.agent import AgentRegisterRequest, SignedEnvelope
from app.services.rate_limit import limit_request
from app.services.security_services import verify_agent_signature

router = APIRouter(prefix='/api/agents', tags=['agents'])
settings = get_settings()


@router.post('/register')
def register_agent(payload: AgentRegisterRequest, request: Request, db: Session = Depends(get_db)):
    limit_request(request, scope='agent-register', limit=30)
    if payload.registration_token != settings.registration_token:
        raise HTTPException(status_code=403, detail='Неверный registration_token')
    agent = upsert_agent(db, payload.agent_uid, payload.hostname, payload.public_key)
    return {'status': 'ok', 'agent_uid': agent.agent_uid}


@router.post('/heartbeat')
def heartbeat(envelope: SignedEnvelope, request: Request, db: Session = Depends(get_db)):
    limit_request(request, scope=f'heartbeat:{envelope.agent_uid}', limit=120)
    verify_agent_signature(db, envelope.agent_uid, envelope.payload, envelope.timestamp, envelope.signature, envelope.nonce)
    agent = upsert_agent(
        db,
        envelope.agent_uid,
        envelope.payload.get('hostname', 'unknown'),
        envelope.payload.get('public_key', ''),
    )
    agent.last_seen_at = datetime.utcnow()
    touch_agent(db, agent)
    return {'status': 'alive'}


@router.post('/tasks/next')
def next_task(envelope: SignedEnvelope, request: Request, db: Session = Depends(get_db)):
    limit_request(request, scope=f'tasks-next:{envelope.agent_uid}', limit=120)
    verify_agent_signature(db, envelope.agent_uid, envelope.payload, envelope.timestamp, envelope.signature, envelope.nonce)
    agent = upsert_agent(
        db,
        envelope.agent_uid,
        envelope.payload.get('hostname', 'unknown'),
        envelope.payload.get('public_key', ''),
    )
    task = get_next_task_for_agent(db, agent)
    if not task:
        return {'task': None}
    return {
        'task': {
            'task_uid': task.task_uid,
            'task_type': task.task_type,
            'command': task.command,
        }
    }
