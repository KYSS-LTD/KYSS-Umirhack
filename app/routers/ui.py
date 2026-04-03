import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password, verify_password
from app.models.models import Agent, Task
from app.repositories.repositories import create_task, create_user, get_user_by_username, mark_offline_agents
from app.services.auth_services import get_current_user

router = APIRouter(tags=['ui'])
templates = Jinja2Templates(directory='app/templates')
settings = get_settings()


def _redirect_if_guest(request: Request):
    if not request.cookies.get('access_token'):
        return RedirectResponse(url='/login', status_code=303)
    return None


@router.get('/login', response_class=HTMLResponse)
def login_page(request: Request):
    if request.cookies.get('access_token'):
        return RedirectResponse(url='/', status_code=303)
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
def register_page(request: Request):
    if request.cookies.get('access_token'):
        return RedirectResponse(url='/', status_code=303)
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
def dashboard(request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    guest_redirect = _redirect_if_guest(request)
    if guest_redirect:
        return guest_redirect

    mark_offline_agents(db, settings.agent_offline_seconds)
    agents = db.query(Agent).order_by(Agent.last_seen_at.desc()).all()
    tasks = db.query(Task).order_by(Task.created_at.desc()).limit(50).all()
    alerts = [a for a in agents if a.revoked or not a.is_online]
    return templates.TemplateResponse('dashboard.html', {'request': request, 'agents': agents, 'tasks': tasks, 'alerts': alerts, 'current_user': current_user})


@router.get('/agents/{agent_uid}', response_class=HTMLResponse)
def agent_detail(agent_uid: str, request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    guest_redirect = _redirect_if_guest(request)
    if guest_redirect:
        return guest_redirect

    agent = db.query(Agent).filter(Agent.agent_uid == agent_uid).first()
    tasks = db.query(Task).filter(Task.agent_id == agent.id).order_by(Task.created_at.desc()).limit(50).all() if agent else []
    return templates.TemplateResponse('agent_detail.html', {'request': request, 'agent': agent, 'tasks': tasks, 'current_user': current_user})


@router.get('/tasks/new', response_class=HTMLResponse)
def new_task_page(request: Request, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    guest_redirect = _redirect_if_guest(request)
    if guest_redirect:
        return guest_redirect

    agents = db.query(Agent).order_by(Agent.hostname.asc()).all()
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
    _=Depends(get_current_user),
):
    guest_redirect = _redirect_if_guest(request)
    if guest_redirect:
        return guest_redirect

    if task_type not in settings.allowed_task_type_set:
        return RedirectResponse(url='/tasks/new', status_code=303)
    task_uid = uuid.uuid4().hex
    target_agent = db.query(Agent).filter(Agent.agent_uid == agent_uid).first() if agent_uid else None
    create_task(db, task_uid=task_uid, task_type=task_type, command=command or None, agent_id=target_agent.id if target_agent else None)
    return RedirectResponse(url='/', status_code=303)
