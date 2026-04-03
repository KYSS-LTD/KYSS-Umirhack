import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.models.models import Agent, Task
from app.repositories.repositories import create_task, mark_offline_agents
from app.services.auth_services import get_current_user

router = APIRouter(tags=['ui'])
templates = Jinja2Templates(directory='app/templates')
settings = get_settings()


@router.get('/', response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    mark_offline_agents(db, settings.agent_offline_seconds)
    agents = db.query(Agent).order_by(Agent.last_seen_at.desc()).all()
    tasks = db.query(Task).order_by(Task.created_at.desc()).limit(50).all()
    alerts = [a for a in agents if a.revoked or not a.is_online]
    return templates.TemplateResponse('dashboard.html', {'request': request, 'agents': agents, 'tasks': tasks, 'alerts': alerts})


@router.get('/agents/{agent_uid}', response_class=HTMLResponse)
def agent_detail(agent_uid: str, request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    agent = db.query(Agent).filter(Agent.agent_uid == agent_uid).first()
    tasks = db.query(Task).filter(Task.agent_id == agent.id).order_by(Task.created_at.desc()).limit(50).all() if agent else []
    return templates.TemplateResponse('agent_detail.html', {'request': request, 'agent': agent, 'tasks': tasks})


@router.get('/tasks/new', response_class=HTMLResponse)
def new_task_page(request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    agents = db.query(Agent).order_by(Agent.hostname.asc()).all()
    return templates.TemplateResponse('task_new.html', {'request': request, 'agents': agents, 'allowed_types': sorted(settings.allowed_task_type_set)})


@router.post('/tasks/new')
def create_task_form(
    request: Request,
    task_type: str = Form(...),
    command: str = Form(''),
    agent_uid: str = Form(''),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    if task_type not in settings.allowed_task_type_set:
        return RedirectResponse(url='/tasks/new', status_code=303)
    task_uid = uuid.uuid4().hex
    target_agent = db.query(Agent).filter(Agent.agent_uid == agent_uid).first() if agent_uid else None
    create_task(db, task_uid=task_uid, task_type=task_type, command=command or None, agent_id=target_agent.id if target_agent else None)
    return RedirectResponse(url='/', status_code=303)
