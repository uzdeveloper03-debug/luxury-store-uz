"""initial schema

Revision ID: 0001
Revises:
"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TS = lambda: sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)  # noqa: E731


def upgrade() -> None:
    op.create_table("users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("telegram_id", sa.BigInteger, nullable=False),
        sa.Column("first_name", sa.String(100), nullable=False),
        sa.Column("username", sa.String(100), nullable=True),
        sa.Column("language", sa.String(2), nullable=False),
        TS(),
        sa.UniqueConstraint("telegram_id", name="uq_users_telegram_id"))
    op.create_table("categories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("slug", sa.String(60), nullable=False),
        sa.Column("name_ru", sa.String(100), nullable=False),
        sa.Column("name_uz", sa.String(100), nullable=False),
        sa.UniqueConstraint("slug", name="uq_categories_slug"))
    op.create_table("brands",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.UniqueConstraint("name", name="uq_brands_name"))
    op.create_table("products",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description_ru", sa.Text, nullable=False),
        sa.Column("description_uz", sa.Text, nullable=False),
        sa.Column("brand_id", sa.Integer, sa.ForeignKey("brands.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("category_id", sa.Integer, sa.ForeignKey("categories.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("price", sa.BigInteger, nullable=False),
        sa.Column("purchase_price", sa.BigInteger, nullable=True),
        sa.Column("is_published", sa.Boolean, nullable=False),
        TS(),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("price > 0", name="ck_product_price_pos"),
        sa.CheckConstraint("purchase_price IS NULL OR purchase_price >= 0", name="ck_product_purchase_nonneg"))
    op.create_index("ix_products_brand_id", "products", ["brand_id"])
    op.create_index("ix_products_category_id", "products", ["category_id"])
    op.create_table("product_images",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("path", sa.String(200), nullable=False),
        sa.Column("position", sa.Integer, nullable=False))
    op.create_index("ix_product_images_product_id", "product_images", ["product_id"])
    op.create_table("product_sizes",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("size", sa.String(10), nullable=False),
        sa.Column("stock", sa.Integer, nullable=False),
        sa.Column("reserved", sa.Integer, nullable=False),
        sa.UniqueConstraint("product_id", "size", name="uq_product_size"),
        sa.CheckConstraint("stock >= 0", name="ck_size_stock_nonneg"),
        sa.CheckConstraint("reserved >= 0", name="ck_size_reserved_nonneg"),
        sa.CheckConstraint("reserved <= stock", name="ck_size_reserved_le_stock"))
    op.create_index("ix_product_sizes_product_id", "product_sizes", ["product_id"])
    op.create_table("orders",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("customer_name", sa.String(100), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("address", sa.String(300), nullable=False),
        sa.Column("comment", sa.String(500), nullable=True),
        sa.Column("total", sa.BigInteger, nullable=False),
        TS(),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False))
    op.create_index("ix_orders_user_id", "orders", ["user_id"])
    op.create_index("ix_orders_status", "orders", ["status"])
    op.create_table("order_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("order_id", sa.Integer, sa.ForeignKey("orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("product_id", sa.Integer, sa.ForeignKey("products.id", ondelete="SET NULL"), nullable=True),
        sa.Column("size_id", sa.Integer, sa.ForeignKey("product_sizes.id", ondelete="SET NULL"), nullable=True),
        sa.Column("product_name", sa.String(200), nullable=False),
        sa.Column("size", sa.String(10), nullable=False),
        sa.Column("price", sa.BigInteger, nullable=False),
        sa.Column("purchase_price", sa.BigInteger, nullable=True),
        sa.Column("quantity", sa.Integer, nullable=False),
        sa.CheckConstraint("quantity > 0", name="ck_item_qty_pos"))
    op.create_index("ix_order_items_order_id", "order_items", ["order_id"])


def downgrade() -> None:
    for t in ("order_items", "orders", "product_sizes", "product_images", "products",
              "brands", "categories", "users"):
        op.drop_table(t)
