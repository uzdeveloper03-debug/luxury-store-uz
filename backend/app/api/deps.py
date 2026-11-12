import jwt
from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import InvalidInitData, decode_admin_token, verify_init_data
from app.models import User

_bearer = HTTPBearer(auto_error=False)


def get_tg_user(authorization: str | None = Header(default=None),
                db: Session = Depends(get_db)) -> User:
    """Покупатель определяется ТОЛЬКО по проверенной подписи initData: 'Authorization: tma <initData>'."""
    s = get_settings()
    if not authorization or not authorization.startswith("tma "):
        raise HTTPException(401, "Требуется авторизация Telegram")
    try:
        tg = verify_init_data(authorization[4:], s.bot_token, s.init_data_ttl)
    except InvalidInitData:
        raise HTTPException(401, "Неверные данные авторизации Telegram")
    tid = int(tg["id"])
    first_name = str(tg.get("first_name", ""))[:100]
    username = str(tg["username"])[:100] if tg.get("username") else None
    user = db.scalar(select(User).where(User.telegram_id == tid))
    if user is None:
        lang = "uz" if str(tg.get("language_code", "")).startswith("uz") else "ru"
        user = User(telegram_id=tid, first_name=first_name, username=username, language=lang)
        db.add(user)
        try:
            db.commit()
        except IntegrityError:  # два первых запроса одного пользователя одновременно
            db.rollback()
            user = db.scalar(select(User).where(User.telegram_id == tid))
    elif user.first_name != first_name or user.username != username:
        user.first_name, user.username = first_name, username
        db.commit()  # пишем только если данные действительно изменились
    return user


def require_admin(creds: HTTPAuthorizationCredentials | None = Depends(_bearer)) -> str:
    if creds is None:
        raise HTTPException(401, "Требуется вход администратора")
    try:
        return decode_admin_token(get_settings().secret_key, creds.credentials)
    except jwt.PyJWTError:
        raise HTTPException(401, "Недействительный или просроченный токен")
