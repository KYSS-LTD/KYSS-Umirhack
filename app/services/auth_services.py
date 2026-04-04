from fastapi import Cookie, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.repositories.repositories import get_user_by_username

bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    access_token: str | None = Cookie(default=None),
    db: Session = Depends(get_db),
):
    token = credentials.credentials if credentials else access_token
    if not token:
        raise HTTPException(status_code=401, detail='Not authenticated')

    username = decode_access_token(token)
    if not username:
        raise HTTPException(status_code=401, detail='Недействительный токен')
    user = get_user_by_username(db, username)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail='Пользователь не найден')
    return user
