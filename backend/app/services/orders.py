"""Резервирование остатков.

Жизненный цикл остатка размера (stock / reserved):
  создание заказа  -> reserved += qty   (только если stock - reserved >= qty)
  доставлен        -> stock -= qty, reserved -= qty  (товар ушёл физически)
  отменён          -> reserved -= qty   (резерв снят)
Резерв делается одним атомарным UPDATE ... WHERE stock - reserved >= qty, поэтому
два одновременных заказа не смогут занять один и тот же последний товар.
"""
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.models import Order, OrderItem, ProductSize, User
from app.schemas.schemas import OrderCreate

TRANSITIONS = {
    "new": {"confirmed", "cancelled"},
    "confirmed": {"shipped", "cancelled"},
    "shipped": {"delivered", "cancelled"},
    "delivered": set(),
    "cancelled": set(),
}


MAX_ACTIVE_ORDERS = 5  # защита от «скупки» остатков резервами
ACTIVE_STATUSES = ("new", "confirmed", "shipped")


class BadItem(Exception):
    pass


class TooManyActiveOrders(Exception):
    pass


class OutOfStock(Exception):
    def __init__(self, product_name: str, size: str):
        super().__init__(f"{product_name} ({size})")
        self.product_name, self.size = product_name, size


class InvalidTransition(Exception):
    pass


def create_order(db: Session, user: User, data: OrderCreate) -> Order:
    wanted: dict[int, int] = {}
    for it in data.items:
        wanted[it.size_id] = wanted.get(it.size_id, 0) + it.quantity
    if any(q > 10 for q in wanted.values()):
        raise BadItem("quantity")
    active = db.scalar(select(func.count()).select_from(Order)
                       .where(Order.user_id == user.id, Order.status.in_(ACTIVE_STATUSES)))
    if (active or 0) >= MAX_ACTIVE_ORDERS:
        raise TooManyActiveOrders()
    try:
        items, total = [], 0
        for size_id in sorted(wanted):  # единый порядок блокировок — без взаимных блокировок
            qty = wanted[size_id]
            size = db.get(ProductSize, size_id)
            if size is None or not size.product.is_published:
                raise BadItem("size")
            res = db.execute(
                update(ProductSize)
                .where(ProductSize.id == size_id,
                       ProductSize.stock - ProductSize.reserved >= qty)
                .values(reserved=ProductSize.reserved + qty))
            if res.rowcount != 1:
                raise OutOfStock(size.product.name, size.size)
            p = size.product  # цена берётся из БД, а не от клиента
            items.append(OrderItem(product_id=p.id, size_id=size.id, product_name=p.name,
                                   size=size.size, price=p.price,
                                   purchase_price=p.purchase_price, quantity=qty))
            total += p.price * qty
        order = Order(user_id=user.id, customer_name=data.customer_name, phone=data.phone,
                      address=data.address, comment=data.comment, total=total, items=items)
        db.add(order)
        db.commit()
        db.refresh(order)
    except Exception:
        db.rollback()
        raise
    return order


def change_status(db: Session, order: Order, new_status: str) -> Order:
    if new_status not in TRANSITIONS.get(order.status, set()):
        raise InvalidTransition(f"{order.status} -> {new_status}")
    try:
        # Сравнить-и-заменить: статус меняется только если он всё ещё прежний. Если два
        # администратора одновременно отменяют заказ, второй получит rowcount=0 и не вернёт резерв дважды.
        cas = db.execute(update(Order).where(Order.id == order.id, Order.status == order.status)
                         .values(status=new_status, updated_at=func.now()))
        if cas.rowcount != 1:
            raise InvalidTransition("статус уже изменён другим запросом")
        for item in order.items:
            if item.size_id is None:
                continue
            q = item.quantity
            if new_status == "delivered":
                stmt = (update(ProductSize)
                        .where(ProductSize.id == item.size_id, ProductSize.reserved >= q,
                               ProductSize.stock >= q)
                        .values(stock=ProductSize.stock - q, reserved=ProductSize.reserved - q))
            elif new_status == "cancelled":
                stmt = (update(ProductSize)
                        .where(ProductSize.id == item.size_id, ProductSize.reserved >= q)
                        .values(reserved=ProductSize.reserved - q))
            else:
                continue
            if db.execute(stmt).rowcount != 1:
                raise RuntimeError(f"Несогласованный остаток для позиции {item.id}")
        db.commit()
        db.refresh(order)
    except Exception:
        db.rollback()
        raise
    return order
