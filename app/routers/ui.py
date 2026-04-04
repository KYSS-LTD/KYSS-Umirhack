import json
import uuid
from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.models.models import Agent, AgentEvent, AgentProfile, Task, User
from app.repositories.repositories import create_task, create_user, get_user_by_username, list_recent_agent_events, mark_offline_agents

router = APIRouter(tags=['ui'])
templates = Jinja2Templates(directory='app/templates')
settings = get_settings()


def _decorate_agent(agent: Agent, custom_name: str | None) -> Agent:
    agent.display_name = custom_name or agent.hostname  # type: ignore[attr-defined]
    return agent


def _load_profiles(db: Session) -> dict[int, str]:
    profiles = db.query(AgentProfile).all()
    return {p.agent_id: p.custom_name for p in profiles if p.custom_name}


def _get_ui_user_or_redirect(request: Request, db: Session) -> User | RedirectResponse:
    token = request.cookies.get('access_token')
    if not token:
        return RedirectResponse(url='/login', status_code=303)

    username = decode_access_token(token)
    if not username:
        response = RedirectResponse(url='/login', status_code=303)
        response.delete_cookie('access_token')
        return response

    user = get_user_by_username(db, username)
    if not user or not user.is_active:
        response = RedirectResponse(url='/login', status_code=303)
        response.delete_cookie('access_token')
        return response
    return user


@router.get('/login', response_class=HTMLResponse)
def login_page(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get('access_token')
    if token:
        username = decode_access_token(token)
        user = get_user_by_username(db, username) if username else None
        if user and user.is_active:
            return RedirectResponse(url='/', status_code=303)

        response = templates.TemplateResponse('login.html', {'request': request, 'error': None})
        response.delete_cookie('access_token')
        return response
    return templates.TemplateResponse('login.html', {'request': request, 'error': None})


@router.post('/login', response_class=HTMLResponse)
def login_submit(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    user = get_user_by_username(db, username)
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse('login.html', {'request': request, 'error': 'Неверный логин или пароль'}, status_code=401)

    token = create_access_token(user.username)
    response = RedirectResponse(url='/', status_code=303)
    response.set_cookie('access_token', token, httponly=True, samesite='lax', secure=False)
    return response


@router.get('/register', response_class=HTMLResponse)
def register_page(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get('access_token')
    if token:
        username = decode_access_token(token)
        user = get_user_by_username(db, username) if username else None
        if user and user.is_active:
            return RedirectResponse(url='/', status_code=303)

        response = templates.TemplateResponse('register.html', {'request': request, 'error': None})
        response.delete_cookie('access_token')
        return response
    return templates.TemplateResponse('register.html', {'request': request, 'error': None})


@router.post('/register', response_class=HTMLResponse)
def register_submit(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(get_db)):
    if len(username) < 3 or len(password) < 8:
        return templates.TemplateResponse(
            'register.html',
            {'request': request, 'error': 'Минимум: логин 3 символа, пароль 8 символов'},
            status_code=400,
        )

    if get_user_by_username(db, username):
        return templates.TemplateResponse('register.html', {'request': request, 'error': 'Пользователь уже существует'}, status_code=409)

    create_user(db, username=username, password_hash=hash_password(password))
    token = create_access_token(username)
    response = RedirectResponse(url='/', status_code=303)
    response.set_cookie('access_token', token, httponly=True, samesite='lax', secure=False)
    return response


@router.post('/logout')
def logout():
    response = RedirectResponse(url='/login', status_code=303)
    response.delete_cookie('access_token')
    return response


@router.get('/', response_class=HTMLResponse)
def dashboard(
    request: Request,
    agent_uid: str = Query(default=''),
    status: str = Query(default='all'),
    task_type: str = Query(default='all'),
    db: Session = Depends(get_db),
):
    current_user = _get_ui_user_or_redirect(request, db)
    if isinstance(current_user, RedirectResponse):
        return current_user

    mark_offline_agents(db, settings.agent_offline_seconds)

    agents_query = db.query(Agent)
    if agent_uid:
        agents_query = agents_query.filter(Agent.agent_uid == agent_uid)
    if status == 'online':
        agents_query = agents_query.filter(Agent.is_online.is_(True), Agent.revoked.is_(False))
    elif status == 'offline':
        agents_query = agents_query.filter((Agent.is_online.is_(False)) | (Agent.revoked.is_(True)))

    profiles_by_agent_id = _load_profiles(db)
    agents = [_decorate_agent(a, profiles_by_agent_id.get(a.id)) for a in agents_query.order_by(Agent.last_seen_at.desc()).all()]

    tasks_query = db.query(Task)
    if agent_uid:
        target_agent = db.query(Agent).filter(Agent.agent_uid == agent_uid).first()
        if target_agent:
            tasks_query = tasks_query.filter(Task.agent_id == target_agent.id)
        else:
            tasks_query = tasks_query.filter(Task.id == -1)
    if task_type != 'all':
        tasks_query = tasks_query.filter(Task.task_type == task_type)
    tasks = tasks_query.order_by(Task.created_at.desc()).limit(100).all()

    all_agents = [_decorate_agent(a, profiles_by_agent_id.get(a.id)) for a in db.query(Agent).order_by(Agent.hostname.asc()).all()]
    task_type_counter = Counter(t.task_type for t in tasks)
    task_status_counter = Counter(t.status.value for t in tasks)

    online_count = sum(1 for a in all_agents if a.is_online and not a.revoked)
    offline_count = len(all_agents) - online_count
    failed_tasks_count = task_status_counter.get('failed', 0)

    cutoff = datetime.utcnow() - timedelta(hours=24)
    recent_events = list_recent_agent_events(db, limit=120)
    offline_events_24h = sum(1 for e in recent_events if e.event_type == 'offline' and e.created_at >= cutoff)

    filters = {'agent_uid': agent_uid, 'status': status, 'task_type': task_type}
    chart_data = {
        'taskStatus': {'labels': list(task_status_counter.keys()) or ['no-data'], 'values': list(task_status_counter.values()) or [0]},
        'taskTypes': {'labels': list(task_type_counter.keys()) or ['no-data'], 'values': list(task_type_counter.values()) or [0]},
    }

    return templates.TemplateResponse(
        'dashboard.html',
        {
            'request': request,
            'agents': agents,
            'all_agents': all_agents,
            'tasks': tasks,
            'alerts': [a for a in all_agents if a.revoked or not a.is_online],
            'events': recent_events,
            'filters': filters,
            'metrics': {
                'online_count': online_count,
                'offline_count': offline_count,
                'failed_tasks_count': failed_tasks_count,
                'offline_events_24h': offline_events_24h,
            },
            'chart_data_json': json.dumps(chart_data, ensure_ascii=False),
            'current_user': current_user,
        },
    )


@router.get('/agents/{agent_uid}', response_class=HTMLResponse)
def agent_detail(agent_uid: str, request: Request, db: Session = Depends(get_db)):
    current_user = _get_ui_user_or_redirect(request, db)
    if isinstance(current_user, RedirectResponse):
        return current_user

    agent = db.query(Agent).filter(Agent.agent_uid == agent_uid).first()
    profile = db.query(AgentProfile).filter(AgentProfile.agent_id == agent.id).first() if agent else None
    if agent:
        _decorate_agent(agent, profile.custom_name if profile else None)

    tasks = db.query(Task).filter(Task.agent_id == agent.id).order_by(Task.created_at.desc()).limit(50).all() if agent else []
    events = db.query(AgentEvent).filter(AgentEvent.agent_id == agent.id).order_by(AgentEvent.created_at.desc()).limit(30).all() if agent else []
    return templates.TemplateResponse(
        'agent_detail.html',
        {'request': request, 'agent': agent, 'tasks': tasks, 'events': events, 'current_user': current_user},
    )


@router.post('/agents/{agent_uid}/rename')
def rename_agent(agent_uid: str, request: Request, custom_name: str = Form(''), db: Session = Depends(get_db)):
    current_user = _get_ui_user_or_redirect(request, db)
    if isinstance(current_user, RedirectResponse):
        return current_user

    agent = db.query(Agent).filter(Agent.agent_uid == agent_uid).first()
    if not agent:
        return RedirectResponse(url='/', status_code=303)

    profile = db.query(AgentProfile).filter(AgentProfile.agent_id == agent.id).first()
    if not profile:
        profile = AgentProfile(agent_id=agent.id)
        db.add(profile)

    name = custom_name.strip()[:120]
    profile.custom_name = name or None
    db.commit()
    return RedirectResponse(url=f'/agents/{agent_uid}', status_code=303)


@router.get('/tasks/new', response_class=HTMLResponse)
def new_task_page(request: Request, db: Session = Depends(get_db)):
    current_user = _get_ui_user_or_redirect(request, db)
    if isinstance(current_user, RedirectResponse):
        return current_user

    profiles_by_agent_id = _load_profiles(db)
    agents = [_decorate_agent(a, profiles_by_agent_id.get(a.id)) for a in db.query(Agent).order_by(Agent.hostname.asc()).all()]
    return templates.TemplateResponse(
        'task_new.html',
        {'request': request, 'agents': agents, 'allowed_types': sorted(settings.allowed_task_type_set), 'current_user': current_user},
    )


@router.post('/tasks/new')
def create_task_form(
    request: Request,
    task_type: str = Form(...),
    command: str = Form(''),
    agent_uid: str = Form(''),
    db: Session = Depends(get_db),
):
    current_user = _get_ui_user_or_redirect(request, db)
    if isinstance(current_user, RedirectResponse):
        return current_user

    if task_type not in settings.allowed_task_type_set:
        return RedirectResponse(url='/tasks/new', status_code=303)

    if agent_uid:
        target_agent = db.query(Agent).filter(Agent.agent_uid == agent_uid).first()
        if target_agent:
            create_task(db, task_uid=uuid.uuid4().hex, task_type=task_type, command=command or None, agent_id=target_agent.id)
    else:
        for agent in db.query(Agent).all():
            create_task(db, task_uid=uuid.uuid4().hex, task_type=task_type, command=command or None, agent_id=agent.id)

    return RedirectResponse(url='/', status_code=303)
