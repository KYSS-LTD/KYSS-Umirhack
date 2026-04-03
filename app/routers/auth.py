from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token, verify_password
from app.repositories.repositories import get_user_by_username
from app.schemas.auth import LoginRequest, TokenResponse
from app.services.rate_limit import limit_request

router = APIRouter(prefix='/api/auth', tags=['auth'])


@router.post('/login', response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    limit_request(request, scope='login', limit=20)
    user = get_user_by_username(db, payload.username)
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail='Неверные учетные данные')
    return TokenResponse(access_token=create_access_token(user.username))
