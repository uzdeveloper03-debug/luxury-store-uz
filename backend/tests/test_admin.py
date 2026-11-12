import io

from app.core.security import login_limiter
from tests.conftest import order_payload, tma

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 64


def test_admin_endpoints_require_token(client, seed):
    for method, url in [("get", "/api/admin/products"), ("post", "/api/admin/products"),
                        ("get", "/api/admin/orders"), ("get", "/api/admin/stats"),
                        ("post", "/api/admin/backups"), ("delete", f"/api/admin/products/{seed['product']}")]:
        assert getattr(client, method)(url).status_code == 401, url
    assert client.get("/api/admin/orders", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_customer_credentials_do_not_grant_admin(client, seed):
    assert client.get("/api/admin/orders", headers=tma()).status_code == 401


def test_login_wrong_password_and_lockout(client):
    bad = {"username": "admin", "password": "wrong"}
    for _ in range(5):
        assert client.post("/api/admin/login", json=bad).status_code == 401
    assert client.post("/api/admin/login", json=bad).status_code == 429
    good = {"username": "admin", "password": "correct-horse-battery"}
    assert client.post("/api/admin/login", json=good).status_code == 429  # блокировка действует и для верного пароля
    login_limiter.reset()
    assert client.post("/api/admin/login", json=good).status_code == 200


def test_product_crud_and_manual_prices(client, seed, admin):
    r = client.post("/api/admin/products", headers=admin, json={
        "name": "Dunk Low", "brand_id": seed["brand"], "category_id": seed["category"],
        "price": 1_200_000, "purchase_price": 700_000, "is_published": False})
    assert r.status_code == 201
    pid = r.json()["id"]
    assert client.get(f"/api/products/{pid}").status_code == 404  # скрыт
    r = client.patch(f"/api/admin/products/{pid}/prices", headers=admin, json={"price": 1_300_000, "purchase_price": None})
    assert r.json()["price"] == 1_300_000 and r.json()["purchase_price"] is None
    r = client.put(f"/api/admin/products/{pid}", headers=admin, json={
        "name": "Dunk Low v2", "brand_id": seed["brand"], "category_id": seed["category"], "is_published": True})
    assert r.json()["name"] == "Dunk Low v2"
    assert client.get(f"/api/products/{pid}").status_code == 200  # опубликован
    assert client.post("/api/admin/products", headers=admin, json={
        "name": "X1", "brand_id": 999, "category_id": seed["category"], "price": 1}).status_code == 400
    assert client.post("/api/admin/products", headers=admin, json={
        "name": "Bad", "brand_id": seed["brand"], "category_id": seed["category"], "price": -5}).status_code == 422


def test_price_change_does_not_alter_existing_orders(client, seed, admin):
    o = client.post("/api/orders", json=order_payload([{"size_id": seed["s41"], "quantity": 1}]), headers=tma()).json()
    client.patch(f"/api/admin/products/{seed['product']}/prices", headers=admin, json={"price": 9_999_999, "purchase_price": 1})
    mine = client.get("/api/orders/my", headers=tma()).json()[0]
    assert mine["total"] == o["total"] == 1_500_000


def test_sizes_and_stock_management(client, seed, admin):
    pid = seed["product"]
    r = client.post(f"/api/admin/products/{pid}/sizes", headers=admin, json={"size": "43", "stock": 4})
    assert {s["size"] for s in r.json()["sizes"]} == {"41", "42", "43"}  # ответ не устарел
    assert client.post(f"/api/admin/products/{pid}/sizes", headers=admin, json={"size": "43", "stock": 1}).status_code == 409
    new = next(s for s in r.json()["sizes"] if s["size"] == "43")
    r = client.put(f"/api/admin/sizes/{new['id']}", headers=admin, json={"stock": 10})
    assert next(s for s in r.json()["sizes"] if s["size"] == "43")["stock"] == 10
    assert client.delete(f"/api/admin/sizes/{new['id']}", headers=admin).status_code == 204


def test_cannot_reduce_stock_below_reserved_or_delete_reserved(client, seed, admin):
    client.post("/api/orders", json=order_payload([{"size_id": seed["s41"], "quantity": 2}]), headers=tma())
    assert client.put(f"/api/admin/sizes/{seed['s41']}", headers=admin, json={"stock": 1}).status_code == 409
    assert client.put(f"/api/admin/sizes/{seed['s41']}", headers=admin, json={"stock": 2}).status_code == 200
    assert client.delete(f"/api/admin/sizes/{seed['s41']}", headers=admin).status_code == 409
    assert client.delete(f"/api/admin/products/{seed['product']}", headers=admin).status_code == 409


def test_multiple_images_upload_and_validation(client, seed, admin):
    pid = seed["product"]
    r = client.post(f"/api/admin/products/{pid}/images", headers=admin,
                    files=[("files", ("a.png", io.BytesIO(PNG), "image/png")),
                           ("files", ("b.jpg", io.BytesIO(JPG), "image/jpeg"))])
    assert r.status_code == 201
    imgs = r.json()["images"]
    assert len(imgs) == 2 and all(i["url"].startswith("/uploads/") for i in imgs)
    assert len(client.get(f"/api/products/{pid}").json()["images"]) == 2
    # поддельное расширение/тип: содержимое — не картинка
    r = client.post(f"/api/admin/products/{pid}/images", headers=admin,
                    files=[("files", ("evil.png", io.BytesIO(b"<?php echo 1; ?>"), "image/png"))])
    assert r.status_code == 400
    r = client.post(f"/api/admin/products/{pid}/images", headers=admin,
                    files=[("files", ("big.png", io.BytesIO(PNG + b"\x00" * (5 * 1024 * 1024)), "image/png"))])
    assert r.status_code == 413
    assert client.delete(f"/api/admin/products/{pid}/images/{imgs[0]['id']}", headers=admin).status_code == 204
    assert len(client.get(f"/api/admin/products/{pid}", headers=admin).json()["images"]) == 1


def test_stats(client, seed, admin):
    o = client.post("/api/orders", json=order_payload([{"size_id": seed["s41"], "quantity": 2}]), headers=tma()).json()
    for st in ("confirmed", "shipped", "delivered"):
        client.patch(f"/api/admin/orders/{o['id']}/status", json={"status": st}, headers=admin)
    s = client.get("/api/admin/stats", headers=admin).json()
    assert s["revenue_delivered"] == 3_000_000
    assert s["profit_delivered"] == (1_500_000 - 900_000) * 2
    assert s["orders_by_status"] == {"delivered": 1}


def test_category_and_brand_protection(client, seed, admin):
    assert client.delete(f"/api/admin/categories/{seed['category']}", headers=admin).status_code == 409
    assert client.delete(f"/api/admin/brands/{seed['brand']}", headers=admin).status_code == 409
    r = client.post("/api/admin/categories", headers=admin, json={"slug": "Bad Slug!", "name_ru": "x", "name_uz": "y"})
    assert r.status_code == 422
