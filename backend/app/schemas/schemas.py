import re
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

SLUG_RE = re.compile(r"^[a-z0-9-]{2,60}$")
SIZE_RE = re.compile(r"^[0-9A-Za-z.,/ -]{1,10}$")


def normalize_phone(v: str) -> str:
    digits = re.sub(r"\D", "", v)
    if len(digits) == 9:
        digits = "998" + digits
    if not re.fullmatch(r"998\d{9}", digits):
        raise ValueError("Телефон должен быть в формате +998XXXXXXXXX")
    return "+" + digits


# ---------- публичные ----------
class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    slug: str
    name_ru: str
    name_uz: str


class BrandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str


class PublicSize(BaseModel):
    id: int
    size: str
    available: int


class ProductPublic(BaseModel):
    id: int
    name: str
    description_ru: str
    description_uz: str
    brand: BrandOut
    category: CategoryOut
    price: int
    images: list[str]
    sizes: list[PublicSize]
    in_stock: bool


class ProductPage(BaseModel):
    items: list[ProductPublic]
    total: int


class OrderItemIn(BaseModel):
    size_id: int
    quantity: int = Field(ge=1, le=10)


class OrderCreate(BaseModel):
    customer_name: str = Field(min_length=2, max_length=100)
    phone: str
    address: str = Field(min_length=5, max_length=300)
    comment: str | None = Field(default=None, max_length=500)
    items: list[OrderItemIn] = Field(min_length=1, max_length=20)

    @field_validator("phone")
    @classmethod
    def _phone(cls, v):
        return normalize_phone(v)

    @field_validator("customer_name", "address")
    @classmethod
    def _strip(cls, v):
        v = v.strip()
        if len(v) < 2:
            raise ValueError("слишком короткое значение")
        return v


class OrderItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    product_id: int | None
    product_name: str
    size: str
    price: int
    quantity: int


class OrderOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    status: str
    customer_name: str
    phone: str
    address: str
    comment: str | None
    total: int
    created_at: datetime
    items: list[OrderItemOut]


class LanguageIn(BaseModel):
    language: Literal["ru", "uz"]


class StoreInfo(BaseModel):
    phone: str
    telegram: str
    address: str


# ---------- админ ----------
class LoginIn(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=200)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CategoryIn(BaseModel):
    slug: str
    name_ru: str = Field(min_length=1, max_length=100)
    name_uz: str = Field(min_length=1, max_length=100)

    @field_validator("slug")
    @classmethod
    def _slug(cls, v):
        if not SLUG_RE.match(v):
            raise ValueError("slug: только a-z, 0-9 и дефис")
        return v


class BrandIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class ProductIn(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    description_ru: str = Field(default="", max_length=5000)
    description_uz: str = Field(default="", max_length=5000)
    brand_id: int
    category_id: int
    price: int = Field(gt=0, le=1_000_000_000)
    purchase_price: int | None = Field(default=None, ge=0, le=1_000_000_000)
    is_published: bool = False


class ProductUpdate(BaseModel):
    """Цены здесь не меняются — для них отдельный PATCH /prices."""
    name: str = Field(min_length=2, max_length=200)
    description_ru: str = Field(default="", max_length=5000)
    description_uz: str = Field(default="", max_length=5000)
    brand_id: int
    category_id: int
    is_published: bool


class PricesIn(BaseModel):
    price: int = Field(gt=0, le=1_000_000_000)
    purchase_price: int | None = Field(default=None, ge=0, le=1_000_000_000)


class SizeIn(BaseModel):
    size: str
    stock: int = Field(ge=0, le=100000)

    @field_validator("size")
    @classmethod
    def _size(cls, v):
        v = v.strip()
        if not SIZE_RE.match(v):
            raise ValueError("недопустимый размер")
        return v


class StockIn(BaseModel):
    stock: int = Field(ge=0, le=100000)


class AdminSizeOut(BaseModel):
    id: int
    size: str
    stock: int
    reserved: int
    available: int


class AdminImageOut(BaseModel):
    id: int
    url: str
    position: int


class AdminProductOut(BaseModel):
    id: int
    name: str
    description_ru: str
    description_uz: str
    brand_id: int
    category_id: int
    price: int
    purchase_price: int | None
    is_published: bool
    images: list[AdminImageOut]
    sizes: list[AdminSizeOut]


class StatusIn(BaseModel):
    status: Literal["confirmed", "shipped", "delivered", "cancelled"]
