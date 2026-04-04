import json
import math
import uuid
from collections import Counter
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, decode_access_token, hash_password, verify_password
from app.models.models import Agent, AgentEvent, AgentProfile, Task, TaskScenario, TaskStatus, User
from app.repositories.repositories import (
    create_task,
    create_user,
    ensure_user_access,
    get_task_by_uid,
    get_user_by_username,
    list_recent_agent_events,
    list_users_with_access,
    mark_offline_agents,
)

router = APIRouter(tags=['ui'])
templates = Jinja2Templates(directory='app/templates')
settings = get_settings()


def _decorate_agent(agent: Agent, custom_name: str | None) -> Agent:
    agent.display_name = custom_name or agent.hostname  # type: ignore[attr-defined]
    agent.short_name = (custom_name or agent.hostname or agent.agent_uid)[:12]  # type: ignore[attr-defined]
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




def _task_health_summary(task: Task) -> dict:
    if not task:
        return {'level': 'WARN', 'message': 'Нет данных'}
    text = task.result or ''
    try:
        payload = json.loads(text) if text.strip().startswith('{') else {}
    except Exception:
        payload = {}
    level = payload.get('level')
    summary = payload.get('summary')
    if level in {'OK', 'WARN', 'CRIT'}:
        return {'level': level, 'message': summary or 'Диагностика завершена'}
    if task.status.value == 'failed':
        return {'level': 'CRIT', 'message': 'Задача завершилась ошибкой'}
    if task.status.value == 'done':
        return {'level': 'OK', 'message': 'Задача выполнена'}
    return {'level': 'WARN', 'message': 'Задача в процессе'}


def _build_topology(all_agents: list[Agent]) -> list[dict]:
    topo = []
    center_x, center_y, radius = 250, 180, 130
    total = max(1, len(all_agents))
    for idx, agent in enumerate(all_agents):
        angle = 2 * math.pi * idx / total
        topo.append({'uid': agent.agent_uid, 'name': agent.short_name, 'x': int(center_x + radius * math.cos(angle)), 'y': int(center_y + radius * math.sin(angle)), 'online': bool(agent.is_online and not agent.revoked)})
    return topo

def _require_permissions(request: Request, db: Session, need_view: bool = False, need_create: bool = False, need_admin: bool = False):
    current_user = _get_ui_user_or_redirect(request, db)
    if isinstance(current_user, RedirectResponse):
        return current_user, None
    access = ensure_user_access(db, current_user)
    allowed = True
    if need_admin and not access.is_admin:
        allowed = False
    if need_view and not (access.is_admin or access.can_view_agents):
        allowed = False
    if need_create and not (access.is_admin or access.can_create_tasks):
        allowed = False
    return current_user, access if allowed else None


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
        return templates.TemplateResponse('register.html', {'request': request, 'error': 'Минимум: логин 3 символа, пароль 8 символов'}, status_code=400)
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
def dashboard(request: Request, agent_uid: str = Query(default=''), status: str = Query(default='all'), task_type: str = Query(default='all'), db: Session = Depends(get_db)):
    current_user, access = _require_permissions(request, db, need_view=True)
    if isinstance(current_user, RedirectResponse):
        return current_user
    if not access:
        return templates.TemplateResponse('dashboard.html', {'request': request, 'permission_denied': True, 'current_user': current_user, 'user_access': ensure_user_access(db, current_user)})

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
    all_agents = [_decorate_agent(a, profiles_by_agent_id.get(a.id)) for a in db.query(Agent).order_by(Agent.hostname.asc()).all()]

    tasks_query = db.query(Task)
    if agent_uid:
        target_agent = db.query(Agent).filter(Agent.agent_uid == agent_uid).first()
        tasks_query = tasks_query.filter(Task.agent_id == target_agent.id) if target_agent else tasks_query.filter(Task.id == -1)
    if task_type != 'all':
        tasks_query = tasks_query.filter(Task.task_type == task_type)
    tasks = tasks_query.order_by(Task.created_at.desc()).limit(100).all()

    task_type_counter = Counter(t.task_type for t in tasks)
    task_status_counter = Counter(t.status.value for t in tasks)

    recent_events = list_recent_agent_events(db, limit=120)
    cutoff = datetime.utcnow() - timedelta(hours=24)
    offline_events_24h = sum(1 for e in recent_events if e.event_type == 'offline' and e.created_at >= cutoff)

    topo = _build_topology(all_agents)

    return templates.TemplateResponse(
        'dashboard.html',
        {
            'request': request,
            'agents': agents,
            'all_agents': all_agents,
            'tasks': tasks,
            'events': recent_events,
            'filters': {'agent_uid': agent_uid, 'status': status, 'task_type': task_type},
            'metrics': {
                'online_count': sum(1 for a in all_agents if a.is_online and not a.revoked),
                'offline_count': sum(1 for a in all_agents if not a.is_online or a.revoked),
                'failed_tasks_count': task_status_counter.get('failed', 0),
                'offline_events_24h': offline_events_24h,
            },
            'chart_data_json': json.dumps({'taskStatus': {'labels': list(task_status_counter.keys()) or ['no-data'], 'values': list(task_status_counter.values()) or [0]}, 'taskTypes': {'labels': list(task_type_counter.keys()) or ['no-data'], 'values': list(task_type_counter.values()) or [0]}}, ensure_ascii=False),
            'topology_json': json.dumps(topo, ensure_ascii=False),
            'allowed_types': sorted(settings.allowed_task_type_set),
            'current_user': current_user,
            'user_access': access,
        },
    )




@router.get('/api/ui/topology')
def topology_live(request: Request, db: Session = Depends(get_db)):
    current_user, access = _require_permissions(request, db, need_view=True)
    if isinstance(current_user, RedirectResponse):
        return JSONResponse({'error': 'unauthorized'}, status_code=401)
    if not access:
        return JSONResponse({'error': 'forbidden'}, status_code=403)

    mark_offline_agents(db, settings.agent_offline_seconds)
    profiles_by_agent_id = _load_profiles(db)
    all_agents = [_decorate_agent(a, profiles_by_agent_id.get(a.id)) for a in db.query(Agent).order_by(Agent.hostname.asc()).all()]
    return {'generated_at': datetime.utcnow().isoformat(), 'nodes': _build_topology(all_agents)}
@router.get('/tasks/detail/{task_uid}', response_class=HTMLResponse)
def task_detail(task_uid: str, request: Request, db: Session = Depends(get_db)):
    current_user, access = _require_permissions(request, db, need_view=True)
    if isinstance(current_user, RedirectResponse):
        return current_user
    if not access:
        return RedirectResponse(url='/', status_code=303)
    task = get_task_by_uid(db, task_uid)
    return templates.TemplateResponse('task_detail.html', {'request': request, 'task': task, 'task_summary': _task_health_summary(task), 'current_user': current_user, 'user_access': access})


@router.get('/agents/{agent_uid}', response_class=HTMLResponse)
def agent_detail(agent_uid: str, request: Request, db: Session = Depends(get_db)):
    current_user, access = _require_permissions(request, db, need_view=True)
    if isinstance(current_user, RedirectResponse):
        return current_user
    if not access:
        return RedirectResponse(url='/', status_code=303)

    agent = db.query(Agent).filter(Agent.agent_uid == agent_uid).first()
    profile = db.query(AgentProfile).filter(AgentProfile.agent_id == agent.id).first() if agent else None
    if agent:
        _decorate_agent(agent, profile.custom_name if profile else None)
    tasks = db.query(Task).filter(Task.agent_id == agent.id).order_by(Task.created_at.desc()).limit(50).all() if agent else []
    events = db.query(AgentEvent).filter(AgentEvent.agent_id == agent.id).order_by(AgentEvent.created_at.desc()).limit(30).all() if agent else []
    return templates.TemplateResponse('agent_detail.html', {'request': request, 'agent': agent, 'tasks': tasks, 'events': events, 'current_user': current_user, 'user_access': access})


@router.post('/agents/{agent_uid}/rename')
def rename_agent(agent_uid: str, request: Request, custom_name: str = Form(''), db: Session = Depends(get_db)):
    current_user, access = _require_permissions(request, db, need_view=True)
    if isinstance(current_user, RedirectResponse):
        return current_user
    if not access:
        return RedirectResponse(url='/', status_code=303)
    agent = db.query(Agent).filter(Agent.agent_uid == agent_uid).first()
    if not agent:
        return RedirectResponse(url='/', status_code=303)
    profile = db.query(AgentProfile).filter(AgentProfile.agent_id == agent.id).first() or AgentProfile(agent_id=agent.id)
    db.add(profile)
    profile.custom_name = custom_name.strip()[:120] or None
    db.commit()
    return RedirectResponse(url=f'/agents/{agent_uid}', status_code=303)


@router.post('/agents/{agent_uid}/delete')
def delete_agent(agent_uid: str, request: Request, db: Session = Depends(get_db)):
    current_user, access = _require_permissions(request, db, need_admin=True)
    if isinstance(current_user, RedirectResponse):
        return current_user
    if not access:
        return RedirectResponse(url='/', status_code=303)

    agent = db.query(Agent).filter(Agent.agent_uid == agent_uid).first()
    if not agent:
        return RedirectResponse(url='/', status_code=303)

    tasks = db.query(Task).filter(Task.agent_id == agent.id).all()
    for task in tasks:
        if task.status in {TaskStatus.pending, TaskStatus.running}:
            task.status = TaskStatus.failed
            task.result = 'agent deleted by admin'
            task.logs = task.result
            task.finished_at = datetime.utcnow()
        task.agent_id = None

    db.query(AgentProfile).filter(AgentProfile.agent_id == agent.id).delete()
    db.query(AgentEvent).filter(AgentEvent.agent_id == agent.id).delete()
    db.delete(agent)
    db.commit()
    return RedirectResponse(url='/', status_code=303)


@router.get('/admin/users', response_class=HTMLResponse)
def admin_users(request: Request, db: Session = Depends(get_db)):
    current_user, access = _require_permissions(request, db, need_admin=True)
    if isinstance(current_user, RedirectResponse):
        return current_user
    if not access:
        return RedirectResponse(url='/', status_code=303)
    return templates.TemplateResponse('admin_users.html', {'request': request, 'rows': list_users_with_access(db), 'current_user': current_user, 'user_access': access})


@router.post('/admin/users/{user_id}/access')
def update_user_access(user_id: int, request: Request, can_view_agents: str = Form('off'), can_create_tasks: str = Form('off'), is_admin: str = Form('off'), db: Session = Depends(get_db)):
    current_user, access = _require_permissions(request, db, need_admin=True)
    if isinstance(current_user, RedirectResponse):
        return current_user
    if not access:
        return RedirectResponse(url='/', status_code=303)
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return RedirectResponse(url='/admin/users', status_code=303)
    ua = ensure_user_access(db, user)
    ua.is_admin = is_admin == 'on'
    ua.can_view_agents = can_view_agents == 'on' or ua.is_admin
    ua.can_create_tasks = can_create_tasks == 'on' or ua.is_admin
    db.commit()
    return RedirectResponse(url='/admin/users', status_code=303)


@router.get('/scenarios', response_class=HTMLResponse)
def scenarios_page(request: Request, db: Session = Depends(get_db)):
    current_user, access = _require_permissions(request, db, need_create=True)
    if isinstance(current_user, RedirectResponse):
        return current_user
    if not access:
        return RedirectResponse(url='/', status_code=303)
    scenarios = db.query(TaskScenario).order_by(TaskScenario.created_at.desc()).all()
    return templates.TemplateResponse('scenarios.html', {'request': request, 'scenarios': scenarios, 'allowed_types': sorted(settings.allowed_task_type_set), 'current_user': current_user, 'user_access': access})


@router.post('/scenarios')
def create_scenario(request: Request, name: str = Form(...), task_type: str = Form(...), command: str = Form(''), description: str = Form(''), db: Session = Depends(get_db)):
    current_user, access = _require_permissions(request, db, need_create=True)
    if isinstance(current_user, RedirectResponse):
        return current_user
    if not access:
        return RedirectResponse(url='/', status_code=303)
    if task_type not in settings.allowed_task_type_set:
        return RedirectResponse(url='/scenarios', status_code=303)
    scenario = TaskScenario(name=name.strip()[:120], description=description.strip()[:255] or None, task_type=task_type, command=command.strip()[:255] or None)
    db.add(scenario)
    db.commit()
    return RedirectResponse(url='/scenarios', status_code=303)


@router.get('/tasks/new', response_class=HTMLResponse)
def new_task_page(request: Request, db: Session = Depends(get_db)):
    current_user, access = _require_permissions(request, db, need_create=True)
    if isinstance(current_user, RedirectResponse):
        return current_user
    if not access:
        return RedirectResponse(url='/', status_code=303)

    profiles_by_agent_id = _load_profiles(db)
    agents = [_decorate_agent(a, profiles_by_agent_id.get(a.id)) for a in db.query(Agent).order_by(Agent.hostname.asc()).all()]
    scenarios = db.query(TaskScenario).order_by(TaskScenario.created_at.desc()).all()
    return templates.TemplateResponse('task_new.html', {'request': request, 'agents': agents, 'scenarios': scenarios, 'allowed_types': sorted(settings.allowed_task_type_set), 'current_user': current_user, 'user_access': access})


@router.post('/tasks/new')
def create_task_form(
    request: Request,
    task_types: list[str] = Form(default=[]),
    scenario_ids: list[int] = Form(default=[]),
    command: str = Form(''),
    agent_uid: str = Form(''),
    db: Session = Depends(get_db),
):
    current_user, access = _require_permissions(request, db, need_create=True)
    if isinstance(current_user, RedirectResponse):
        return current_user
    if not access:
        return RedirectResponse(url='/', status_code=303)

    specs: list[tuple[str, str | None]] = []
    for t in task_types:
        if t in settings.allowed_task_type_set:
            specs.append((t, command if t == 'run_command' else None))

    if scenario_ids:
        scenarios = db.query(TaskScenario).filter(TaskScenario.id.in_(scenario_ids)).all()
        for s in scenarios:
            if s.task_type in settings.allowed_task_type_set:
                specs.append((s.task_type, s.command))

    if not specs:
        return RedirectResponse(url='/tasks/new', status_code=303)

    if agent_uid:
        agents = [db.query(Agent).filter(Agent.agent_uid == agent_uid).first()]
    else:
        agents = db.query(Agent).all()

    for agent in [a for a in agents if a]:
        for task_type, cmd in specs:
            if task_type == 'run_command' and cmd not in settings.allowed_command_set:
                continue
            create_task(db, task_uid=uuid.uuid4().hex, task_type=task_type, command=cmd, agent_id=agent.id)

    return RedirectResponse(url='/', status_code=303)
