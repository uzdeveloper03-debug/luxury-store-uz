from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_tg_user
from app.core.db import get_db
from app.models import Order, User
from app.schemas.schemas import LanguageIn, OrderCreate, OrderOut
from app.services.orders import BadItem, OutOfStock, TooManyActiveOrders, create_order

router = APIRouter(prefix="/api", tags=["customer"])


@router.post("/orders", response_model=OrderOut, status_code=201)
def place_order(data: OrderCreate, user: User = Depends(get_tg_user), db: Session = Depends(get_db)):
    try:
        return create_order(db, user, data)
    except OutOfStock as e:
        raise HTTPException(409, f"Недостаточно товара на складе: {e}")
    except BadItem:
        raise HTTPException(400, "Некорректная позиция заказа")
    except TooManyActiveOrders:
        raise HTTPException(429, "Слишком много незавершённых заказов. Дождитесь обработки текущих.")


@router.get("/orders/my", response_model=list[OrderOut])
def my_orders(user: User = Depends(get_tg_user), db: Session = Depends(get_db)):
    # только заказы текущего пользователя — чужие данные недоступны
    return db.scalars(select(Order).where(Order.user_id == user.id).order_by(Order.id.desc())
                      .options(selectinload(Order.items))).all()


@router.put("/me/language", status_code=204)
def set_language(data: LanguageIn, user: User = Depends(get_tg_user), db: Session = Depends(get_db)):
    user.language = data.language
    db.commit()
