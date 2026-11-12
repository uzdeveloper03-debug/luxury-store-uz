from tests.conftest import order_payload, tma


def available(client, seed, key):
    p = client.get(f"/api/products/{seed['product']}").json()
    return {s["id"]: s["available"] for s in p["sizes"]}[seed[key]]


def test_order_reserves_stock(client, seed):
    r = client.post("/api/orders", json=order_payload([{"size_id": seed["s41"], "quantity": 2}]), headers=tma())
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["total"] == 3_000_000 and body["status"] == "new"
    assert body["phone"] == "+998901234567"
    assert available(client, seed, "s41") == 1


def test_cannot_oversell(client, seed):
    ok = client.post("/api/orders", json=order_payload([{"size_id": seed["s42"], "quantity": 1}]), headers=tma(1))
    assert ok.status_code == 201
    second = client.post("/api/orders", json=order_payload([{"size_id": seed["s42"], "quantity": 1}]), headers=tma(2))
    assert second.status_code == 409
    assert available(client, seed, "s42") == 0


def test_order_is_all_or_nothing(client, seed):
    items = [{"size_id": seed["s41"], "quantity": 1}, {"size_id": seed["s42"], "quantity": 5}]
    r = client.post("/api/orders", json=order_payload(items), headers=tma())
    assert r.status_code == 409
    assert available(client, seed, "s41") == 3  # первая позиция не должна остаться в резерве
    assert client.get("/api/orders/my", headers=tma()).json() == []


def test_duplicate_items_are_merged_and_checked(client, seed):
    items = [{"size_id": seed["s41"], "quantity": 2}, {"size_id": seed["s41"], "quantity": 2}]
    assert client.post("/api/orders", json=order_payload(items), headers=tma()).status_code == 409


def test_client_cannot_set_price_and_hidden_not_orderable(client, seed):
    r = client.post("/api/orders", headers=tma(),
                    json=order_payload([{"size_id": seed["s41"], "quantity": 1, "price": 1}]))
    assert r.json()["total"] == 1_500_000
    r = client.post("/api/orders", json=order_payload([{"size_id": seed["shidden"], "quantity": 1}]), headers=tma())
    assert r.status_code == 400


def test_validation(client, seed):
    item = [{"size_id": seed["s41"], "quantity": 1}]
    assert client.post("/api/orders", json=order_payload(item, phone="12345"), headers=tma()).status_code == 422
    assert client.post("/api/orders", json=order_payload([]), headers=tma()).status_code == 422
    assert client.post("/api/orders", json=order_payload([{"size_id": seed["s41"], "quantity": 0}]), headers=tma()).status_code == 422
    assert client.post("/api/orders", json=order_payload(item, address="x"), headers=tma()).status_code == 422


def test_user_sees_only_own_orders(client, seed):
    client.post("/api/orders", json=order_payload([{"size_id": seed["s41"], "quantity": 1}]), headers=tma(1))
    assert len(client.get("/api/orders/my", headers=tma(1)).json()) == 1
    assert client.get("/api/orders/my", headers=tma(2)).json() == []


def test_cancel_releases_and_delivery_commits(client, seed, admin):
    a = client.post("/api/orders", json=order_payload([{"size_id": seed["s41"], "quantity": 2}]), headers=tma()).json()
    assert client.patch(f"/api/admin/orders/{a['id']}/status", json={"status": "cancelled"}, headers=admin).status_code == 200
    assert available(client, seed, "s41") == 3  # резерв снят
    b = client.post("/api/orders", json=order_payload([{"size_id": seed["s41"], "quantity": 2}]), headers=tma()).json()
    for st in ("confirmed", "shipped", "delivered"):
        assert client.patch(f"/api/admin/orders/{b['id']}/status", json={"status": st}, headers=admin).status_code == 200
    assert available(client, seed, "s41") == 1  # физический остаток уменьшился: 3 - 2
    full = client.get(f"/api/admin/products/{seed['product']}", headers=admin).json()
    s41 = next(s for s in full["sizes"] if s["id"] == seed["s41"])
    assert (s41["stock"], s41["reserved"]) == (1, 0)


def test_invalid_status_transitions(client, seed, admin):
    o = client.post("/api/orders", json=order_payload([{"size_id": seed["s41"], "quantity": 1}]), headers=tma()).json()
    url = f"/api/admin/orders/{o['id']}/status"
    assert client.patch(url, json={"status": "delivered"}, headers=admin).status_code == 409  # new -> delivered нельзя
    client.patch(url, json={"status": "cancelled"}, headers=admin)
    assert client.patch(url, json={"status": "confirmed"}, headers=admin).status_code == 409  # из cancelled нельзя
    assert client.patch(url, json={"status": "cancelled"}, headers=admin).status_code == 409  # двойной возврат резерва
    assert available(client, seed, "s41") == 3
