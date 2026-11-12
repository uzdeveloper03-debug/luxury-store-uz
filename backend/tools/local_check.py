"""Локальная сквозная проверка backend БЕЗ Telegram и БЕЗ хостинга.

Запуск из папки backend:   python -m tools.local_check

Что делает: создаёт ВРЕМЕННУЮ SQLite-базу, проверяет миграции (upgrade / current / downgrade / upgrade),
поднимает сервер на 127.0.0.1 и проходит сценарий «админ добавляет товар → покупатель заказывает».
Использует вымышленный тестовый токен и случайные секреты. К сети и Telegram не обращается,
ваш .env и вашу базу не трогает (переменные окружения приоритетнее .env), всё временное удаляется.
"""
import importlib.util
import json
import os
import secrets
import shutil
import socket
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from tools.test_init_data import TEST_BOT_TOKEN, build_init_data

BACKEND = Path(__file__).resolve().parents[1]
TABLES = {"users", "categories", "brands", "products", "product_images", "product_sizes", "orders", "order_items"}
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPG = b"\xff\xd8\xff\xe0" + b"\x00" * 32
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    results.append((name, bool(ok), detail))
    print(("[OK]   " if ok else "[FAIL] ") + name + (f"  — {detail}" if detail and not ok else ""))
    return bool(ok)


def preflight() -> list[str]:
    missing = [m for m in ("fastapi", "uvicorn", "sqlalchemy", "pydantic_settings", "multipart", "jwt")
               if importlib.util.find_spec(m) is None]
    try:
        if importlib.util.find_spec("alembic.config") is None:  # локальная папка alembic/ — не библиотека
            missing.append("alembic")
    except ModuleNotFoundError:
        missing.append("alembic")
    return missing


def call(base, method, path, body=None, headers=None, raw=None, ctype=None):
    h = dict(headers or {})
    data = None
    if raw is not None:
        data, h["Content-Type"] = raw, ctype
    elif body is not None:
        data, h["Content-Type"] = json.dumps(body).encode(), "application/json"
    req = urllib.request.Request(base + path, data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            status, text, hdrs = r.status, r.read().decode(), r.headers
    except urllib.error.HTTPError as e:
        status, text, hdrs = e.code, e.read().decode(), e.headers
    try:
        js = json.loads(text) if text else None
    except ValueError:
        js = None
    return status, js, text, hdrs


def multipart(files):
    b = "----luxurytest" + secrets.token_hex(8)
    body = b""
    for fname, ctype, data in files:
        body += (f'--{b}\r\nContent-Disposition: form-data; name="files"; filename="{fname}"\r\n'
                 f"Content-Type: {ctype}\r\n\r\n").encode() + data + b"\r\n"
    return body + f"--{b}--\r\n".encode(), f"multipart/form-data; boundary={b}"


def tables(db: Path) -> set:
    con = sqlite3.connect(db)
    try:
        return {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")} - {"sqlite_sequence"}
    finally:
        con.close()


def scenario(base: str, admin_user: str, admin_pw: str) -> None:
    A = {"Authorization": "tma " + build_init_data(1001)}
    Bh = {"Authorization": "tma " + build_init_data(2002)}
    st, js, text, hdrs = call(base, "GET", "/api/health")
    check("health отвечает 200", st == 200)
    check("заголовки безопасности", hdrs.get("X-Content-Type-Options") == "nosniff" and hdrs.get("X-Frame-Options") == "DENY")

    check("админка без токена → 401", call(base, "GET", "/api/admin/orders")[0] == 401)
    check("неверный пароль → 401", call(base, "POST", "/api/admin/login", {"username": admin_user, "password": "wrong-password"})[0] == 401)
    st, js, *_ = call(base, "POST", "/api/admin/login", {"username": admin_user, "password": admin_pw})
    if not check("вход администратора → 200 и токен", st == 200 and js and js.get("access_token")):
        return
    AD = {"Authorization": "Bearer " + js["access_token"]}
    check("токен покупателя не даёт доступ к админке", call(base, "GET", "/api/admin/orders", headers=A)[0] == 401)

    brand = call(base, "POST", "/api/admin/brands", {"name": "Nike"}, AD)[1]
    cat = call(base, "POST", "/api/admin/categories", {"slug": "running", "name_ru": "Бег", "name_uz": "Yugurish"}, AD)[1]
    st, prod, *_ = call(base, "POST", "/api/admin/products", {
        "name": "Air Max 90", "brand_id": brand["id"], "category_id": cat["id"],
        "price": 1_500_000, "purchase_price": 900_000, "is_published": False}, AD)
    if not check("товар создан (скрыт)", st == 201):
        return
    pid = prod["id"]
    check("скрытый товар не виден покупателям", call(base, "GET", f"/api/products/{pid}")[0] == 404)
    body, ctype = multipart([("a.png", "image/png", PNG), ("b.jpg", "image/jpeg", JPG)])
    st, js, *_ = call(base, "POST", f"/api/admin/products/{pid}/images", headers=AD, raw=body, ctype=ctype)
    check("загружено 2 фотографии", st == 201 and len(js["images"]) == 2)
    body, ctype = multipart([("evil.png", "image/png", b"<html>not an image</html>")])
    check("не-картинка отклонена → 400", call(base, "POST", f"/api/admin/products/{pid}/images", headers=AD, raw=body, ctype=ctype)[0] == 400)
    s41 = call(base, "POST", f"/api/admin/products/{pid}/sizes", {"size": "41", "stock": 2}, AD)[1]
    js = call(base, "POST", f"/api/admin/products/{pid}/sizes", {"size": "42", "stock": 1}, AD)[1]
    size41 = next(s for s in js["sizes"] if s["size"] == "41")["id"]
    st, js, *_ = call(base, "PUT", f"/api/admin/products/{pid}", {
        "name": "Air Max 90", "brand_id": brand["id"], "category_id": cat["id"], "is_published": True}, AD)
    check("товар опубликован", st == 200 and js["is_published"])

    st, js, text, _ = call(base, "GET", "/api/products?q=air&size=41")
    check("каталог: поиск и фильтр по размеру находят товар", st == 200 and js["total"] == 1 and len(js["items"][0]["images"]) == 2)
    check("закупочная цена не раскрывается покупателям", "purchase_price" not in text and "900000" not in text)
    check("поиск '%' не превращается в «любой текст»", call(base, "GET", "/api/products?q=%25")[1]["total"] == 0)

    order = {"customer_name": "Али Валиев", "phone": "+998 90 123-45-67", "address": "Ташкент, ул. Навои 1",
             "items": [{"size_id": size41, "quantity": 2}]}
    check("заказ без авторизации → 401", call(base, "POST", "/api/orders", order)[0] == 401)
    forged = {"Authorization": "tma " + build_init_data(1001, bot_token="999999999:FORGED_token_0123456789abcdef")}
    check("initData чужим токеном → 401", call(base, "POST", "/api/orders", order, forged)[0] == 401)
    tampered = {"Authorization": "tma " + build_init_data(1001).replace("Test", "Hack")}
    check("изменённые initData → 401", call(base, "POST", "/api/orders", order, tampered)[0] == 401)
    expired = {"Authorization": "tma " + build_init_data(1001, auth_date=int(time.time()) - 200000)}
    check("просроченные initData → 401", call(base, "POST", "/api/orders", order, expired)[0] == 401)

    st, oa, *_ = call(base, "POST", "/api/orders", order, A)
    check("заказ A (2 шт.) создан, сумма посчитана сервером", st == 201 and oa["total"] == 3_000_000)
    order_b = {**order, "items": [{"size_id": size41, "quantity": 1}]}
    check("резервирование: заказ B на то же → 409 (нет остатка)", call(base, "POST", "/api/orders", order_b, Bh)[0] == 409)
    avail = lambda: next(s["available"] for s in call(base, "GET", f"/api/products/{pid}")[1]["sizes"] if s["id"] == size41)
    check("доступный остаток размера 41 = 0", avail() == 0)
    st, js, *_ = call(base, "PATCH", f"/api/admin/orders/{oa['id']}/status", {"status": "cancelled"}, AD)
    check("отмена заказа A", st == 200)
    check("после отмены резерв снят (остаток 2)", avail() == 2)
    check("повторная отмена → 409", call(base, "PATCH", f"/api/admin/orders/{oa['id']}/status", {"status": "cancelled"}, AD)[0] == 409)
    st, ob, *_ = call(base, "POST", "/api/orders", order_b, Bh)
    check("заказ B теперь проходит", st == 201)
    codes = [call(base, "PATCH", f"/api/admin/orders/{ob['id']}/status", {"status": s}, AD)[0] for s in ("confirmed", "shipped", "delivered")]
    check("статусы confirmed → shipped → delivered", codes == [200, 200, 200], str(codes))
    ps = call(base, "GET", f"/api/admin/products/{pid}", headers=AD)[1]
    s = next(x for x in ps["sizes"] if x["id"] == size41)
    check("после доставки физический остаток 2 → 1, резерв 0", (s["stock"], s["reserved"]) == (1, 0), str(s))
    stats = call(base, "GET", "/api/admin/stats", headers=AD)[1]
    check("статистика: выручка 1 500 000, прибыль 600 000", stats["revenue_delivered"] == 1_500_000 and stats["profit_delivered"] == 600_000, str(stats))
    check("A видит только свои заказы", [o["status"] for o in call(base, "GET", "/api/orders/my", headers=A)[1]] == ["cancelled"])
    check("B видит только свои заказы", [o["status"] for o in call(base, "GET", "/api/orders/my", headers=Bh)[1]] == ["delivered"])
    check("резервная копия создаётся", call(base, "POST", "/api/admin/backups", headers=AD)[0] == 201 and len(call(base, "GET", "/api/admin/backups", headers=AD)[1]) == 1)

    for _ in range(5):
        call(base, "POST", "/api/admin/login", {"username": admin_user, "password": "wrong-password"})
    check("перебор пароля: блокировка 429", call(base, "POST", "/api/admin/login", {"username": admin_user, "password": admin_pw})[0] == 429)


def main() -> int:
    missing = preflight()
    if missing:
        print("Не установлены пакеты:", ", ".join(missing))
        print("Выполните в папке backend:  pip install -r requirements.txt")
        return 2
    tmp = Path(tempfile.mkdtemp(prefix="luxury_local_"))
    admin_pw = "Local-" + secrets.token_urlsafe(12)
    env = {**os.environ, "BOT_TOKEN": TEST_BOT_TOKEN, "SECRET_KEY": secrets.token_urlsafe(48),
           "ADMIN_USERNAME": "admin", "ADMIN_PASSWORD": admin_pw,
           "DATABASE_URL": f"sqlite:///{(tmp / 'local.db').as_posix()}",
           "UPLOAD_DIR": str(tmp / "uploads"), "BACKUP_DIR": str(tmp / "backups"),
           "CORS_ORIGINS": "", "WEBAPP_URL": "", "DEBUG": "false", "PYTHONIOENCODING": "utf-8"}
    run = lambda *a: subprocess.run([sys.executable, "-m", *a], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=180)
    server = None
    try:
        print(f"Временная папка: {tmp}\n")
        r = run("alembic", "upgrade", "head")
        check("alembic upgrade head", r.returncode == 0, r.stderr[-400:])
        r = run("alembic", "current")
        check("alembic current показывает 0001", "0001" in (r.stdout + r.stderr), (r.stdout + r.stderr)[-200:])
        check("миграция создала все 8 таблиц", TABLES <= tables(tmp / "local.db"), str(TABLES - tables(tmp / "local.db")))
        r = run("alembic", "downgrade", "base")
        check("alembic downgrade base", r.returncode == 0 and not (TABLES & tables(tmp / "local.db")), r.stderr[-400:])
        r = run("alembic", "upgrade", "head")
        check("повторный upgrade head", r.returncode == 0 and TABLES <= tables(tmp / "local.db"), r.stderr[-400:])

        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        log = open(tmp / "server.log", "w", encoding="utf-8")
        server = subprocess.Popen([sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
                                  cwd=BACKEND, env=env, stdout=log, stderr=log)
        base = f"http://127.0.0.1:{port}"
        up = False
        for _ in range(60):
            if server.poll() is not None:
                break
            try:
                up = call(base, "GET", "/api/health")[0] == 200
                if up:
                    break
            except OSError:
                time.sleep(0.5)
        if not check("сервер запустился", up):
            log.flush()
            print((tmp / "server.log").read_text(encoding="utf-8")[-1500:])
        else:
            scenario(base, "admin", admin_pw)
    finally:
        if server and server.poll() is None:
            server.terminate()
            try:
                server.wait(10)
            except subprocess.TimeoutExpired:
                server.kill()
        shutil.rmtree(tmp, ignore_errors=True)
    failed = [n for n, ok, _ in results if not ok]
    print(f"\nИТОГО: пройдено {len(results) - len(failed)} из {len(results)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
