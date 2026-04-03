from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Agent, Task
from app.services.auth_services import get_current_user

router = APIRouter(tags=['ui'])
templates = Jinja2Templates(directory='app/templates')


@router.get('/', response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), _=Depends(get_current_user)):
    agents = db.query(Agent).all()
    tasks = db.query(Task).order_by(Task.created_at.desc()).limit(50).all()
    alerts = [a for a in agents if a.revoked]
    return templates.TemplateResponse(
        'dashboard.html',
        {'request': request, 'agents': agents, 'tasks': tasks, 'alerts': alerts},
    )
