from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import get_tg_user
from app.api.public import to_public
from app.core.db import get_db
from app.models import CartItem, Favorite, Product, ProductSize, User
from app.schemas.schemas import (
    CartAddIn,
    CartItemOut,
    CartQuantityIn,
    ProductPublic,
    ProfileOut,
)

router = APIRouter(prefix="/api", tags=["customer"])


def product_options():
    return (
        selectinload(Product.images),
        selectinload(Product.sizes),
        selectinload(Product.brand),
        selectinload(Product.category),
    )


# ---------- ПРОФИЛЬ ----------

@router.get("/me", response_model=ProfileOut)
def my_profile(
    user: User = Depends(get_tg_user),
):
    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "first_name": user.first_name,
        "username": user.username,
        "language": user.language,
        "created_at": user.created_at,
    }


# ---------- ИЗБРАННОЕ ----------

@router.get("/favorites", response_model=list[ProductPublic])
def get_favorites(
    user: User = Depends(get_tg_user),
    db: Session = Depends(get_db),
):
    products = db.scalars(
        select(Product)
        .join(Favorite, Favorite.product_id == Product.id)
        .where(
            Favorite.user_id == user.id,
            Product.is_published.is_(True),
        )
        .options(*product_options())
        .order_by(Favorite.created_at.desc())
    ).all()

    return [to_public(product) for product in products]


@router.post("/favorites/{product_id}", status_code=204)
def add_favorite(
    product_id: int,
    user: User = Depends(get_tg_user),
    db: Session = Depends(get_db),
):
    product = db.scalar(
        select(Product).where(
            Product.id == product_id,
            Product.is_published.is_(True),
        )
    )
    if product is None:
        raise HTTPException(404, "Товар не найден")

    existing = db.scalar(
        select(Favorite).where(
            Favorite.user_id == user.id,
            Favorite.product_id == product_id,
        )
    )

    if existing is None:
        db.add(Favorite(user_id=user.id, product_id=product_id))
        db.commit()


@router.delete("/favorites/{product_id}", status_code=204)
def remove_favorite(
    product_id: int,
    user: User = Depends(get_tg_user),
    db: Session = Depends(get_db),
):
    favorite = db.scalar(
        select(Favorite).where(
            Favorite.user_id == user.id,
            Favorite.product_id == product_id,
        )
    )

    if favorite is not None:
        db.delete(favorite)
        db.commit()


# ---------- КОРЗИНА ----------

@router.get("/cart", response_model=list[CartItemOut])
def get_cart(
    user: User = Depends(get_tg_user),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(CartItem, ProductSize, Product)
        .join(ProductSize, CartItem.size_id == ProductSize.id)
        .join(Product, ProductSize.product_id == Product.id)
        .where(
            CartItem.user_id == user.id,
            Product.is_published.is_(True),
        )
        .options(*product_options())
        .order_by(CartItem.created_at.desc())
    ).all()

    return [
        CartItemOut(
            id=item.id,
            product=to_public(product),
            size_id=size.id,
            size=size.size,
            quantity=item.quantity,
            available=max(size.stock - size.reserved, 0),
        )
        for item, size, product in rows
    ]


@router.post("/cart", status_code=204)
def add_cart_item(
    data: CartAddIn,
    user: User = Depends(get_tg_user),
    db: Session = Depends(get_db),
):
    size = db.scalar(
        select(ProductSize)
        .join(Product, Product.id == ProductSize.product_id)
        .where(
            ProductSize.id == data.size_id,
            Product.is_published.is_(True),
        )
    )

    if size is None:
        raise HTTPException(404, "Размер или товар не найден")

    available = max(size.stock - size.reserved, 0)

    existing = db.scalar(
        select(CartItem).where(
            CartItem.user_id == user.id,
            CartItem.size_id == data.size_id,
        )
    )

    new_quantity = data.quantity + (
        existing.quantity if existing else 0
    )

    if new_quantity > 10:
        raise HTTPException(409, "Максимум 10 единиц одного размера")

    if new_quantity > available:
        raise HTTPException(409, "Недостаточно товара на складе")

    if existing:
        existing.quantity = new_quantity
    else:
        db.add(
            CartItem(
                user_id=user.id,
                size_id=data.size_id,
                quantity=new_quantity,
            )
        )

    db.commit()


@router.patch("/cart/{item_id}", status_code=204)
def update_cart_item(
    item_id: int,
    data: CartQuantityIn,
    user: User = Depends(get_tg_user),
    db: Session = Depends(get_db),
):
    row = db.execute(
        select(CartItem, ProductSize, Product)
        .join(ProductSize, CartItem.size_id == ProductSize.id)
        .join(Product, ProductSize.product_id == Product.id)
        .where(
            CartItem.id == item_id,
            CartItem.user_id == user.id,
        )
    ).first()

    if row is None:
        raise HTTPException(404, "Позиция корзины не найдена")

    item, size, product = row

    if not product.is_published:
        raise HTTPException(409, "Товар больше не опубликован")

    available = max(size.stock - size.reserved, 0)

    if data.quantity > available:
        raise HTTPException(409, "Недостаточно товара на складе")

    item.quantity = data.quantity
    db.commit()


@router.delete("/cart/{item_id}", status_code=204)
def remove_cart_item(
    item_id: int,
    user: User = Depends(get_tg_user),
    db: Session = Depends(get_db),
):
    item = db.scalar(
        select(CartItem).where(
            CartItem.id == item_id,
            CartItem.user_id == user.id,
        )
    )

    if item is not None:
        db.delete(item)
        db.commit()
