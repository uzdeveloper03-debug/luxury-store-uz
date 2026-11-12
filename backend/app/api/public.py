from fastapi import APIRouter, Depends, Query
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.core.db import get_db
from app.models import Brand, Category, Product, ProductSize
from app.schemas.schemas import (BrandOut, CategoryOut, ProductPage, ProductPublic,
                                 PublicSize, StoreInfo)
from fastapi import HTTPException

router = APIRouter(prefix="/api", tags=["public"])


def to_public(p: Product) -> ProductPublic:
    sizes = [PublicSize(id=s.id, size=s.size, available=max(s.stock - s.reserved, 0)) for s in p.sizes]
    return ProductPublic(
        id=p.id, name=p.name, description_ru=p.description_ru, description_uz=p.description_uz,
        brand=BrandOut.model_validate(p.brand), category=CategoryOut.model_validate(p.category),
        price=p.price, images=[f"/uploads/{i.path}" for i in p.images], sizes=sizes,
        in_stock=any(s.available > 0 for s in sizes))  # purchase_price намеренно не отдаётся


@router.get("/store-info", response_model=StoreInfo)
def store_info():
    s = get_settings()
    return StoreInfo(phone=s.store_phone, telegram=s.store_telegram, address=s.store_address)


@router.get("/categories", response_model=list[CategoryOut])
def categories(db: Session = Depends(get_db)):
    return db.scalars(select(Category).order_by(Category.name_ru)).all()


@router.get("/brands", response_model=list[BrandOut])
def brands(db: Session = Depends(get_db)):
    return db.scalars(select(Brand).order_by(Brand.name)).all()


@router.get("/products", response_model=ProductPage)
def products(q: str | None = Query(None, max_length=100), brand_id: int | None = None,
             category_id: int | None = None, min_price: int | None = Query(None, ge=0),
             max_price: int | None = Query(None, ge=0), size: str | None = Query(None, max_length=10),
             limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0),
             db: Session = Depends(get_db)):
    cond = [Product.is_published.is_(True)]
    if q:
        cond.append(Product.name.icontains(q.strip(), autoescape=True))
    if brand_id:
        cond.append(Product.brand_id == brand_id)
    if category_id:
        cond.append(Product.category_id == category_id)
    if min_price is not None:
        cond.append(Product.price >= min_price)
    if max_price is not None:
        cond.append(Product.price <= max_price)
    if size:
        cond.append(exists().where(ProductSize.product_id == Product.id, ProductSize.size == size,
                                   ProductSize.stock - ProductSize.reserved > 0))
    total = db.scalar(select(func.count()).select_from(Product).where(*cond)) or 0
    rows = db.scalars(
        select(Product).where(*cond).order_by(Product.id.desc()).limit(limit).offset(offset)
        .options(selectinload(Product.images), selectinload(Product.sizes),
                 selectinload(Product.brand), selectinload(Product.category))).all()
    return ProductPage(items=[to_public(p) for p in rows], total=total)


@router.get("/products/{product_id}", response_model=ProductPublic)
def product(product_id: int, db: Session = Depends(get_db)):
    p = db.get(Product, product_id)
    if p is None or not p.is_published:
        raise HTTPException(404, "Товар не найден")
    return to_public(p)
