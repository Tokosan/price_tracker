"""Categorías del usuario: CRUD, asignación, privacidad y qué pasa al juntar o separar."""

from tests.test_api import BILLY, STARDEW, logged_in, sin_red  # noqa: F401 (fixture autouse)
from tests.test_groups import BILLY2


def names(watch) -> list[str]:
    return [c["name"] for c in watch["categories"]]


def test_crear_renombrar_y_colores():
    api = logged_in("ana")
    r = api.post("/api/categories", {"name": "  Juegos   de mesa "})
    assert r.status_code == 201, r.text
    juegos = r.json()
    assert juegos == {"id": juegos["id"], "name": "Juegos de mesa", "color": "gray", "count": 0}
    # La siguiente toma el primer color libre; se puede elegir uno.
    assert api.post("/api/categories", {"name": "Regalos"}).json()["color"] == "red"
    assert api.post("/api/categories", {"name": "Casa", "color": "blue"}).json()["color"] == "blue"
    assert api.post("/api/categories", {"name": "Otra", "color": "fucsia"}).status_code == 422
    # Únicas sin distinguir mayúsculas, también al renombrar.
    assert api.post("/api/categories", {"name": "regalos"}).status_code == 409
    assert api.patch(f"/api/categories/{juegos['id']}", {"name": "CASA"}).status_code == 409
    r = api.patch(f"/api/categories/{juegos['id']}", {"name": "Juegos", "color": "green"})
    assert (r.json()["name"], r.json()["color"]) == ("Juegos", "green")
    # Orden alfabético.
    assert [c["name"] for c in api.get("/api/categories").json()] == ["Casa", "Juegos", "Regalos"]


def test_asignar_al_agregar_y_editar():
    api = logged_in("ana")
    juegos = api.post("/api/categories", {"name": "Juegos"}).json()
    regalos = api.post("/api/categories", {"name": "Regalos"}).json()
    w = api.post(
        "/api/watches", {"urls": [STARDEW], "rules": [], "category_ids": [regalos["id"]]}
    ).json()[0]
    assert names(w) == ["Regalos"]

    r = api.put(
        f"/api/watches/{w['id']}/categories", {"ids": [juegos["id"], regalos["id"], juegos["id"]]}
    )
    assert r.status_code == 200, r.text
    assert names(r.json()) == ["Juegos", "Regalos"]
    counts = {c["name"]: c["count"] for c in api.get("/api/categories").json()}
    assert counts == {"Juegos": 1, "Regalos": 1}

    # Borrar la categoría no toca el producto.
    assert api.delete(f"/api/categories/{juegos['id']}").status_code == 204
    assert names(api.get(f"/api/watches/{w['id']}").json()) == ["Regalos"]


def test_asignar_en_masa():
    api = logged_in("ana")
    cat = api.post("/api/categories", {"name": "Casa"}).json()
    a = api.post("/api/watches", {"urls": [BILLY], "rules": []}).json()[0]
    b = api.post("/api/watches", {"urls": [STARDEW], "rules": []}).json()[0]
    ids = [a["id"], b["id"]]
    r = api.post(f"/api/categories/{cat['id']}/watches", {"watch_ids": ids, "action": "add"})
    assert r.status_code == 200, r.text
    assert r.json()["category"]["count"] == 2
    # Agregar dos veces no duplica.
    api.post(f"/api/categories/{cat['id']}/watches", {"watch_ids": ids, "action": "add"})
    assert all(names(w) == ["Casa"] for w in api.get("/api/watches").json())
    r = api.post(
        f"/api/categories/{cat['id']}/watches", {"watch_ids": [a["id"]], "action": "remove"}
    )
    assert r.json()["category"]["count"] == 1
    assert r.json()["watches"] == [{"id": a["id"], "categories": []}]


def test_privacidad_de_categorias():
    ana, beto = logged_in("ana"), logged_in("beto")
    cat = ana.post("/api/categories", {"name": "Secreta"}).json()
    w_beto = beto.post("/api/watches", {"urls": [STARDEW], "rules": []}).json()[0]
    w_ana = ana.post("/api/watches", {"urls": [BILLY], "rules": []}).json()[0]

    assert beto.get("/api/categories").json() == []
    assert beto.patch(f"/api/categories/{cat['id']}", {"name": "x"}).status_code == 404
    assert beto.delete(f"/api/categories/{cat['id']}").status_code == 404
    # Ni asignar la categoría ajena a lo propio, ni la propia a un producto ajeno.
    r = beto.post("/api/watches", {"urls": [BILLY], "rules": [], "category_ids": [cat["id"]]})
    assert r.status_code == 404
    r = beto.put(f"/api/watches/{w_beto['id']}/categories", {"ids": [cat["id"]]})
    assert r.status_code == 404
    r = ana.post(
        f"/api/categories/{cat['id']}/watches",
        {"watch_ids": [w_ana["id"], w_beto["id"]], "action": "add"},
    )
    assert r.status_code == 404
    assert names(ana.get(f"/api/watches/{w_ana['id']}").json()) == []

    # El admin sí las ve.
    admin = logged_in("jefe", role="admin")
    ana.put(f"/api/watches/{w_ana['id']}/categories", {"ids": [cat["id"]]})
    de_ana = [w for w in admin.get("/api/admin/watches").json() if w["user"]["username"] == "ana"]
    assert names(de_ana[0]) == ["Secreta"]


def test_juntar_une_las_categorias_y_separar_las_copia():
    api = logged_in("ana")
    casa = api.post("/api/categories", {"name": "Casa"}).json()
    juegos = api.post("/api/categories", {"name": "Juegos"}).json()
    a = api.post("/api/watches", {"urls": [BILLY], "rules": [], "category_ids": [casa["id"]]})
    b = api.post("/api/watches", {"urls": [BILLY2], "rules": [], "category_ids": [juegos["id"]]})
    a, b = a.json()[0], b.json()[0]

    m = api.post("/api/watches/merge", {"ids": [a["id"], b["id"]]}).json()
    assert names(m) == ["Casa", "Juegos"]
    assert {c["count"] for c in api.get("/api/categories").json()} == {1}

    pid = m["items"][1]["id"]
    r = api.post(f"/api/watches/{m['id']}/items/{pid}/move", {"to": None}).json()
    assert names(r["target"]) == ["Casa", "Juegos"]
    assert names(r["source"]) == ["Casa", "Juegos"]


def test_mover_el_ultimo_link_lleva_sus_categorias():
    api = logged_in("ana")
    casa = api.post("/api/categories", {"name": "Casa"}).json()
    a = api.post("/api/watches", {"urls": [BILLY], "rules": []}).json()[0]
    b = api.post("/api/watches", {"urls": [BILLY2], "rules": [], "category_ids": [casa["id"]]})
    b = b.json()[0]
    pid = b["items"][0]["id"]
    r = api.post(f"/api/watches/{b['id']}/items/{pid}/move", {"to": a["id"]}).json()
    assert r["source"] is None
    assert names(r["target"]) == ["Casa"]


def test_borrar_el_producto_no_borra_la_categoria():
    api = logged_in("ana")
    casa = api.post("/api/categories", {"name": "Casa"}).json()
    w = api.post("/api/watches", {"urls": [BILLY], "rules": [], "category_ids": [casa["id"]]})
    assert api.delete(f"/api/watches/{w.json()[0]['id']}").status_code == 204
    assert api.get("/api/categories").json() == [{**casa, "count": 0}]
