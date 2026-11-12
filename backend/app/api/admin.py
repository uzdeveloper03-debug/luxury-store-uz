import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.api.deps import require_admin
from app.core.config import get_settings
from app.core.db import get_db
from app.core.security import (check_admin_credentials, create_admin_token, login_limiter)
from app.models import Brand, Category, Order, OrderItem, Product, ProductImage, ProductSize
from app.schemas.schemas import (AdminImageOut, AdminProductOut, AdminSizeOut, BrandIn, BrandOut,
                                 CategoryIn, CategoryOut, LoginIn, OrderOut, PricesIn,
                                 ProductIn, ProductUpdate, SizeIn, StatusIn, StockIn, TokenOut)
from app.services import backup as backup_service
from app.services.orders import InvalidTransition, change_status

login_router = APIRouter(prefix="/api/admin", tags=["admin-auth"])
router = APIRouter(prefix="/api/admin", tags=["admin"], dependencies=[Depends(require_admin)])


# ---------- вход ----------
@login_router.post("/login", response_model=TokenOut)
def login(data: LoginIn, request: Request):
    s = get_settings()
    ip = request.client.host if request.client else "unknown"
    if login_limiter.blocked(ip):
        raise HTTPException(429, "Слишком много попыток входа. Попробуйте позже.")
    if not check_admin_credentials(data.username, data.password, s.admin_username, s.admin_password):
        login_limiter.fail(ip)
        raise HTTPException(401, "Неверный логин или пароль")
    login_limiter.success(ip)
    return TokenOut(access_token=create_admin_token(s.secret_key, data.username, s.jwt_ttl_minutes))


# ---------- вспомогательное ----------
def _product_out(p: Product) -> AdminProductOut:
    return AdminProductOut(
        id=p.id, name=p.name, description_ru=p.description_ru, description_uz=p.description_uz,
        brand_id=p.brand_id, category_id=p.category_id, price=p.price,
        purchase_price=p.purchase_price, is_published=p.is_published,
        images=[AdminImageOut(id=i.id, url=f"/uploads/{i.path}", position=i.position) for i in p.images],
        sizes=[AdminSizeOut(id=s.id, size=s.size, stock=s.stock, reserved=s.reserved,
                            available=s.stock - s.reserved) for s in p.sizes])


def _load_product(db: Session, product_id: int) -> Product:
    p = db.scalar(select(Product).where(Product.id == product_id)
                  .options(selectinload(Product.images), selectinload(Product.sizes))
                  .execution_options(populate_existing=True))  # не отдавать устаревшие данные из сессии
    if p is None:
        raise HTTPException(404, "Товар не найден")
    return p


def _check_refs(db: Session, brand_id: int, category_id: int) -> None:
    if db.get(Brand, brand_id) is None or db.get(Category, category_id) is None:
        raise HTTPException(400, "Бренд или категория не существуют")


# ---------- категории ----------
@router.get("/categories", response_model=list[CategoryOut])
def list_categories(db: Session = Depends(get_db)):
    return db.scalars(select(Category).order_by(Category.name_ru)).all()


@router.post("/categories", response_model=CategoryOut, status_code=201)
def create_category(data: CategoryIn, db: Session = Depends(get_db)):
    c = Category(**data.model_dump())
    db.add(c)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Категория с таким slug уже есть")
    return c


@router.put("/categories/{cid}", response_model=CategoryOut)
def update_category(cid: int, data: CategoryIn, db: Session = Depends(get_db)):
    c = db.get(Category, cid)
    if c is None:
        raise HTTPException(404, "Не найдено")
    for k, v in data.model_dump().items():
        setattr(c, k, v)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Категория с таким slug уже есть")
    return c


@router.delete("/categories/{cid}", status_code=204)
def delete_category(cid: int, db: Session = Depends(get_db)):
    c = db.get(Category, cid)
    if c is None:
        raise HTTPException(404, "Не найдено")
    if db.scalar(select(func.count()).select_from(Product).where(Product.category_id == cid)):
        raise HTTPException(409, "В категории есть товары")
    db.delete(c)
    db.commit()


# ---------- бренды ----------
@router.get("/brands", response_model=list[BrandOut])
def list_brands(db: Session = Depends(get_db)):
    return db.scalars(select(Brand).order_by(Brand.name)).all()


@router.post("/brands", response_model=BrandOut, status_code=201)
def create_brand(data: BrandIn, db: Session = Depends(get_db)):
    b = Brand(name=data.name.strip())
    db.add(b)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Такой бренд уже есть")
    return b


@router.delete("/brands/{bid}", status_code=204)
def delete_brand(bid: int, db: Session = Depends(get_db)):
    b = db.get(Brand, bid)
    if b is None:
        raise HTTPException(404, "Не найдено")
    if db.scalar(select(func.count()).select_from(Product).where(Product.brand_id == bid)):
        raise HTTPException(409, "У бренда есть товары")
    db.delete(b)
    db.commit()


# ---------- товары ----------
@router.get("/products", response_model=list[AdminProductOut])
def list_products(q: str | None = Query(None, max_length=100), limit: int = Query(50, ge=1, le=200),
                  offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    stmt = select(Product).order_by(Product.id.desc()).limit(limit).offset(offset).options(
        selectinload(Product.images), selectinload(Product.sizes))
    if q:
        stmt = stmt.where(Product.name.icontains(q.strip(), autoescape=True))
    return [_product_out(p) for p in db.scalars(stmt).all()]


@router.post("/products", response_model=AdminProductOut, status_code=201)
def create_product(data: ProductIn, db: Session = Depends(get_db)):
    _check_refs(db, data.brand_id, data.category_id)
    p = Product(**data.model_dump())
    db.add(p)
    db.commit()
    return _product_out(_load_product(db, p.id))


@router.get("/products/{pid}", response_model=AdminProductOut)
def get_product(pid: int, db: Session = Depends(get_db)):
    return _product_out(_load_product(db, pid))


@router.put("/products/{pid}", response_model=AdminProductOut)
def update_product(pid: int, data: ProductUpdate, db: Session = Depends(get_db)):
    p = _load_product(db, pid)
    _check_refs(db, data.brand_id, data.category_id)
    for k, v in data.model_dump().items():
        setattr(p, k, v)
    db.commit()
    return _product_out(_load_product(db, pid))


@router.patch("/products/{pid}/prices", response_model=AdminProductOut)
def update_prices(pid: int, data: PricesIn, db: Session = Depends(get_db)):
    """Ручное изменение розничной и закупочной цены. Уже созданные заказы хранят старую цену."""
    p = _load_product(db, pid)
    p.price, p.purchase_price = data.price, data.purchase_price
    db.commit()
    return _product_out(_load_product(db, pid))


@router.delete("/products/{pid}", status_code=204)
def delete_product(pid: int, db: Session = Depends(get_db)):
    p = _load_product(db, pid)
    if any(s.reserved > 0 for s in p.sizes):
        raise HTTPException(409, "Есть активные заказы с этим товаром. Скройте товар вместо удаления.")
    paths = [i.path for i in p.images]
    db.delete(p)
    db.commit()
    for path in paths:
        _remove_file(path)


# ---------- фотографии ----------
_MAGIC = [(b"\xff\xd8\xff", "jpg"), (b"\x89PNG\r\n\x1a\n", "png")]


def _detect_ext(head: bytes) -> str | None:
    for sig, ext in _MAGIC:
        if head.startswith(sig):
            return ext
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp"
    return None


def _remove_file(name: str) -> None:
    base = Path(get_settings().upload_dir).resolve()
    f = (base / name).resolve()
    if f.parent == base:  # защита от выхода за пределы каталога
        f.unlink(missing_ok=True)


@router.post("/products/{pid}/images", response_model=AdminProductOut, status_code=201)
async def upload_images(pid: int, files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    s = get_settings()
    p = _load_product(db, pid)
    if len(p.images) + len(files) > s.max_images_per_product:
        raise HTTPException(400, f"Не более {s.max_images_per_product} фотографий на товар")
    limit = s.max_upload_mb * 1024 * 1024
    prepared = []
    for f in files:  # сначала проверяем все файлы, потом сохраняем
        data = await f.read(limit + 1)
        if len(data) > limit:
            raise HTTPException(413, f"Файл больше {s.max_upload_mb} МБ")
        ext = _detect_ext(data[:16])
        if ext is None:
            raise HTTPException(400, "Допустимы только JPEG, PNG и WEBP")
        prepared.append((data, ext))
    base = Path(s.upload_dir)
    base.mkdir(parents=True, exist_ok=True)
    pos = max((i.position for i in p.images), default=-1) + 1
    saved = []
    try:
        for data, ext in prepared:
            name = f"{secrets.token_hex(16)}.{ext}"  # имя генерируется сервером
            (base / name).write_bytes(data)
            saved.append(name)
            db.add(ProductImage(product_id=pid, path=name, position=pos))
            pos += 1
        db.commit()
    except Exception:
        db.rollback()
        for n in saved:
            _remove_file(n)
        raise
    return _product_out(_load_product(db, pid))


@router.delete("/products/{pid}/images/{image_id}", status_code=204)
def delete_image(pid: int, image_id: int, db: Session = Depends(get_db)):
    img = db.scalar(select(ProductImage).where(ProductImage.id == image_id,
                                               ProductImage.product_id == pid))
    if img is None:
        raise HTTPException(404, "Фото не найдено")
    name = img.path
    db.delete(img)
    db.commit()
    _remove_file(name)


# ---------- размеры и остатки ----------
@router.post("/products/{pid}/sizes", response_model=AdminProductOut, status_code=201)
def add_size(pid: int, data: SizeIn, db: Session = Depends(get_db)):
    _load_product(db, pid)
    db.add(ProductSize(product_id=pid, size=data.size, stock=data.stock, reserved=0))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Такой размер у товара уже есть")
    return _product_out(_load_product(db, pid))


@router.put("/sizes/{size_id}", response_model=AdminProductOut)
def set_stock(size_id: int, data: StockIn, db: Session = Depends(get_db)):
    """Устанавливает физический остаток. Нельзя сделать меньше, чем уже зарезервировано."""
    size = db.get(ProductSize, size_id)
    if size is None:
        raise HTTPException(404, "Размер не найден")
    res = db.execute(update(ProductSize)
                     .where(ProductSize.id == size_id, ProductSize.reserved <= data.stock)
                     .values(stock=data.stock))
    if res.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Остаток не может быть меньше зарезервированного количества")
    db.commit()
    return _product_out(_load_product(db, size.product_id))


@router.delete("/sizes/{size_id}", status_code=204)
def delete_size(size_id: int, db: Session = Depends(get_db)):
    res = db.execute(delete(ProductSize).where(ProductSize.id == size_id, ProductSize.reserved == 0))
    if res.rowcount != 1:
        db.rollback()
        raise HTTPException(409, "Размер не найден или под него есть активные заказы")
    db.commit()


# ---------- заказы ----------
@router.get("/orders", response_model=list[OrderOut])
def list_orders(status: str | None = Query(None, max_length=20), limit: int = Query(50, ge=1, le=200),
                offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    stmt = select(Order).order_by(Order.id.desc()).limit(limit).offset(offset).options(
        selectinload(Order.items))
    if status:
        stmt = stmt.where(Order.status == status)
    return db.scalars(stmt).all()


@router.get("/orders/{oid}", response_model=OrderOut)
def get_order(oid: int, db: Session = Depends(get_db)):
    o = db.scalar(select(Order).where(Order.id == oid).options(selectinload(Order.items)))
    if o is None:
        raise HTTPException(404, "Заказ не найден")
    return o


@router.patch("/orders/{oid}/status", response_model=OrderOut)
def set_order_status(oid: int, data: StatusIn, db: Session = Depends(get_db)):
    o = db.scalar(select(Order).where(Order.id == oid).options(selectinload(Order.items)))
    if o is None:
        raise HTTPException(404, "Заказ не найден")
    try:
        return change_status(db, o, data.status)
    except InvalidTransition:
        raise HTTPException(409, f"Нельзя перевести заказ из статуса '{o.status}' в '{data.status}'")


# ---------- статистика ----------
@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    by_status = dict(db.execute(select(Order.status, func.count()).group_by(Order.status)).all())
    revenue = db.scalar(select(func.coalesce(func.sum(Order.total), 0)).where(Order.status == "delivered"))
    profit = db.scalar(
        select(func.coalesce(func.sum((OrderItem.price - OrderItem.purchase_price) * OrderItem.quantity), 0))
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.status == "delivered", OrderItem.purchase_price.is_not(None)))
    top = db.execute(
        select(OrderItem.product_name, func.sum(OrderItem.quantity).label("qty"))
        .join(Order, Order.id == OrderItem.order_id).where(Order.status == "delivered")
        .group_by(OrderItem.product_name).order_by(func.sum(OrderItem.quantity).desc()).limit(5)).all()
    low = db.execute(
        select(Product.name, ProductSize.size, (ProductSize.stock - ProductSize.reserved))
        .join(Product, Product.id == ProductSize.product_id)
        .where(ProductSize.stock - ProductSize.reserved <= 2).order_by(Product.name).limit(20)).all()
    return {
        "orders_by_status": by_status,
        "orders_total": sum(by_status.values()),
        "revenue_delivered": int(revenue or 0),
        "profit_delivered": int(profit or 0),  # считается только по позициям с указанной закупочной ценой
        "top_products": [{"name": n, "quantity": int(q)} for n, q in top],
        "low_stock": [{"product": n, "size": sz, "available": int(a)} for n, sz, a in low],
    }


# ---------- резервные копии ----------
@router.post("/backups", status_code=201)
def create_backup():
    try:
        return {"name": backup_service.make_backup().name}
    except backup_service.BackupError as e:
        raise HTTPException(500, str(e))


@router.get("/backups")
def get_backups():
    return backup_service.list_backups()
