def test_hidden_product_not_visible(client, seed):
    r = client.get("/api/products")
    names = [p["name"] for p in r.json()["items"]]
    assert names == ["Air Max"]
    assert client.get(f"/api/products/{seed['hidden']}").status_code == 404


def test_purchase_price_never_exposed(client, seed):
    r = client.get(f"/api/products/{seed['product']}")
    assert r.status_code == 200
    assert "purchase_price" not in r.text and "900000" not in r.text
    for p in client.get("/api/products").json()["items"]:
        assert "purchase_price" not in p


def test_filters_and_search(client, seed):
    assert client.get("/api/products?q=air").json()["total"] == 1
    assert client.get("/api/products?q=zzz").json()["total"] == 0
    assert client.get("/api/products?min_price=2000000").json()["total"] == 0
    assert client.get("/api/products?max_price=1500000").json()["total"] == 1
    assert client.get("/api/products?size=41").json()["total"] == 1
    assert client.get("/api/products?size=50").json()["total"] == 0
    assert client.get(f"/api/products?brand_id={seed['brand']}").json()["total"] == 1
    assert client.get("/api/products?brand_id=9999").json()["total"] == 0


def test_sizes_show_available_not_total(client, seed):
    p = client.get(f"/api/products/{seed['product']}").json()
    assert {s["size"]: s["available"] for s in p["sizes"]} == {"41": 3, "42": 1}
    assert p["in_stock"] is True


def test_categories_and_brands(client, seed):
    assert client.get("/api/categories").json()[0]["name_uz"] == "Yugurish"
    assert client.get("/api/brands").json()[0]["name"] == "Nike"
