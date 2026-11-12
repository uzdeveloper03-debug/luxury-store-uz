"""Сквозная проверка РАБОТАЮЩЕГО локального сервера на тестовых данных (только стандартная библиотека).
Сначала в другом окне: python scripts/run_local.py     Затем:  python scripts/smoke_test.py
Данные создаются в тестовой базе test_local.db; настоящая база не затрагивается."""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _common import DEFAULT_ENV, TEST_MARKER, parse_env_file  # noqa: E402
from make_test_init_data import build_init_data  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32  # проходит проверку сигнатуры; не настоящая картинка
fails: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(("PASS  " if cond else "FAIL  ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--env-file", default=str(DEFAULT_ENV))
    a = ap.parse_args()
    env = parse_env_file(a.env_file)
    token = env.get("BOT_TOKEN", "")
    if env.get("APP_ENV") != "test" or TEST_MARKER not in token:
        print("Отказ: нужен тестовый файл окружения (APP_ENV=test, тестовый токен).", file=sys.stderr)
        return 2

    def call(method, path, body=None, headers=None, raw=None, ctype=None):
        h = dict(headers or {})
        data = None
        if body is not None:
            data, h["Content-Type"] = json.dumps(body).encode(), "application/json"
        elif raw is not None:
            data, h["Content-Type"] = raw, ctype
        req = urllib.request.Request(a.base + path, data=data, method=method, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, r.headers, r.read()
        except urllib.error.HTTPError as e:
            return e.code, e.headers, e.read()

    def js(raw):
        return json.loads(raw.decode() or "null")

    def tma(uid):
        return {"Authorization": "tma " + build_init_data(token, user_id=uid, first_name="Тест")}

    try:
        s, h, _ = call("GET", "/api/health")
    except (urllib.error.URLError, ConnectionError):
        print("Сервер не отвечает. Запустите в другом окне: python scripts/run_local.py", file=sys.stderr)
        return 2
    check("health отвечает 200", s == 200)
    check("заголовок nosniff", h.get("X-Content-Type-Options") == "nosniff")

    # --- авторизация ---
    check("заказы без авторизации → 401", call("GET", "/api/orders/my")[0] == 401)
    check("поддельный initData → 401", call("GET", "/api/orders/my", headers={"Authorization": "tma fake"})[0] == 401)
    check("подделанные данные → 401", call("GET", "/api/orders/my", headers={"Authorization": "tma " + build_init_data(token, tamper=True)})[0] == 401)
    check("просроченные данные → 401", call("GET", "/api/orders/my", headers={"Authorization": "tma " + build_init_data(token, age_seconds=90000)})[0] == 401)
    check("админка без токена → 401", call("GET", "/api/admin/orders")[0] == 401)
    check("админка с токеном покупателя → 401", call("GET", "/api/admin/orders", headers=tma(1))[0] == 401)
    check("неверный пароль админа → 401", call("POST", "/api/admin/login", {"username": "admin", "password": "wrong-password"})[0] == 401)
    s, _, raw = call("POST", "/api/admin/login", {"username": env["ADMIN_USERNAME"], "password": env["ADMIN_PASSWORD"]})
    check("вход админа → 200", s == 200)
    if s != 200:
        return 1
    adm = {"Authorization": "Bearer " + js(raw)["access_token"]}

    # --- каталог (товары создаются вручную через админку) ---
    tag = str(int(time.time()))
    s, _, raw = call("POST", "/api/admin/brands", {"name": f"SmokeBrand-{tag}"}, adm); brand = js(raw)["id"]
    s2, _, raw = call("POST", "/api/admin/categories", {"slug": f"smoke-{tag}", "name_ru": "Тест", "name_uz": "Test"}, adm); cat = js(raw)["id"]
    check("бренд и категория созданы", s == 201 and s2 == 201)
    s, _, raw = call("POST", "/api/admin/products", {"name": f"Smoke Sneaker {tag}", "brand_id": brand, "category_id": cat,
                     "price": 1_000_000, "purchase_price": 600_000, "is_published": False}, adm)
    pid = js(raw)["id"]
    check("товар создан скрытым", s == 201)
    check("скрытый товар не виден покупателям", call("GET", f"/api/products/{pid}")[0] == 404)
    s, _, raw = call("POST", f"/api/admin/products/{pid}/sizes", {"size": "42", "stock": 2}, adm)
    size_id = js(raw)["sizes"][0]["id"]
    b = uuid.uuid4().hex
    body = (f"--{b}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"a.png\"\r\nContent-Type: image/png\r\n\r\n").encode() + PNG + f"\r\n--{b}--\r\n".encode()
    s, _, raw = call("POST", f"/api/admin/products/{pid}/images", headers=adm, raw=body, ctype=f"multipart/form-data; boundary={b}")
    check("фото загружено", s == 201)
    bad = (f"--{b}\r\nContent-Disposition: form-data; name=\"files\"; filename=\"x.png\"\r\nContent-Type: image/png\r\n\r\n").encode() + b"not an image" + f"\r\n--{b}--\r\n".encode()
    check("не-картинка отклонена → 400", call("POST", f"/api/admin/products/{pid}/images", headers=adm, raw=bad, ctype=f"multipart/form-data; boundary={b}")[0] == 400)
    url = js(raw)["images"][0]["url"]
    check("фото доступно по ссылке", call("GET", url)[0] == 200)
    call("PUT", f"/api/admin/products/{pid}", {"name": f"Smoke Sneaker {tag}", "brand_id": brand, "category_id": cat, "is_published": True}, adm)
    s, _, raw = call("GET", f"/api/products/{pid}")
    check("опубликованный товар виден", s == 200)
    check("закупочная цена не раскрывается", b"purchase_price" not in raw and b"600000" not in raw)

    # --- заказы и резервирование ---
    stats0 = js(call("GET", "/api/admin/stats", headers=adm)[2])
    order = {"customer_name": "Тест Покупатель", "phone": "+998901234567", "address": "Тестовый адрес, дом 1",
             "items": [{"size_id": size_id, "quantity": 2}]}
    s, _, raw = call("POST", "/api/orders", order, tma(424242)); oid = js(raw)["id"]
    check("заказ на весь остаток → 201", s == 201)
    order2 = dict(order, items=[{"size_id": size_id, "quantity": 1}])
    check("перепродажа невозможна → 409", call("POST", "/api/orders", order2, tma(424243))[0] == 409)
    check("покупатель видит свои заказы", len(js(call("GET", "/api/orders/my", headers=tma(424242))[2])) >= 1)
    check("чужие заказы не видны", js(call("GET", "/api/orders/my", headers=tma(424243))[2]) == [])
    check("недопустимый переход new→delivered → 409", call("PATCH", f"/api/admin/orders/{oid}/status", {"status": "delivered"}, adm)[0] == 409)
    for st in ("confirmed", "shipped", "delivered"):
        check(f"статус → {st}", call("PATCH", f"/api/admin/orders/{oid}/status", {"status": st}, adm)[0] == 200)
    stats1 = js(call("GET", "/api/admin/stats", headers=adm)[2])
    check("выручка выросла на сумму заказа", stats1["revenue_delivered"] - stats0["revenue_delivered"] == 2_000_000)
    check("прибыль выросла на (цена−закупка)×кол-во", stats1["profit_delivered"] - stats0["profit_delivered"] == 800_000)
    p = js(call("GET", f"/api/admin/products/{pid}", headers=adm)[2])
    check("остаток списан после доставки", (p["sizes"][0]["stock"], p["sizes"][0]["reserved"]) == (0, 0))

    # --- резервное копирование ---
    s, _, raw = call("POST", "/api/admin/backups", headers=adm)
    check("резервная копия создана", s == 201)
    check("копия в списке", any(x["name"] == js(raw)["name"] for x in js(call("GET", "/api/admin/backups", headers=adm)[2])))

    print(f"\nИТОГО: {'ВСЕ ПРОВЕРКИ ПРОЙДЕНЫ' if not fails else 'ПРОВАЛЕНО: ' + str(len(fails))}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
