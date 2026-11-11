"""Eigene Domains je Modul: Weiterleitungen, erlaubte Pfade, Links, Proxy-Konfiguration."""

from fastapi.testclient import TestClient

from app import links, main, modhosts, proxy
from app.db import SessionLocal

from conftest import csrf_of, login, settings


def host_client(host: str) -> TestClient:
    return TestClient(main.app, base_url=f"https://{host}", follow_redirects=False)


def reset():
    main._host_cache["at"] = 0.0
    links.invalidate()


def test_module_domain_routing():
    settings(module_krank="1", module_laws="1", domain_krank="krank.example.org", domain_laws="")
    reset()
    c = host_client("krank.example.org")
    assert c.get("/").headers["location"] == "/krank"
    assert c.get("/krank").status_code == 200
    assert c.get("/static/app.css").status_code == 200
    r = c.get("/admin/users?x=1")
    assert r.status_code == 302 and r.headers["location"] == "https://portal.example.org/admin/users?x=1"
    assert c.get("/recht").headers["location"] == "https://portal.example.org/recht"   # anderes Modul
    assert c.get("/login").headers["location"] == "https://portal.example.org/login"
    # Unter der Portal-Domain bleibt alles wie bisher erreichbar
    assert host_client("portal.example.org").get("/krank").status_code == 200
    # Modul aus → auch unter der eigenen Domain gesperrt
    settings(module_krank="0")
    reset()
    assert c.get("/krank").status_code == 404
    settings(module_krank="1", domain_krank="")
    reset()


def test_links_use_module_domain():
    settings(domain_forms="formulare.example.org")
    reset()
    assert links.base("forms") == "https://formulare.example.org"
    assert links.base("laws") == "https://portal.example.org"
    settings(domain_forms="")
    reset()


def test_proxy_blocks_and_validation():
    cfg = {"tls_mode": "letsencrypt", "tls_email": "it@example.org", "domain_krank": "krank.example.org"}
    text = proxy.render(cfg)
    assert "krank.example.org {" in text and "reverse_proxy portal:8000" in text
    assert "tls internal" not in text
    assert "tls internal" in proxy.render({"tls_mode": "selfsigned", "domain_krank": "krank.example.org"})
    errs = modhosts.validate({"krank": "portal.example.org", "laws": "x", "maps": "a.example.org", "forms": "a.example.org"},
                             {"Portal": "portal.example.org"})
    assert len(errs) == 3


def test_admin_domains_page():
    admin = login("admin@example.org", "admin-passwort-123")
    page = admin.get("/admin/domains")
    assert page.status_code == 200 and "BlueOtter Krankmelder" in page.text
    token = csrf_of(page.text)
    r = admin.post("/admin/domains", data={"csrf": token, "krank": "https://Krank.Example.org/", "laws": "portal.example.org"})
    assert r.status_code == 303
    with SessionLocal() as db:
        from app.db import get_settings
        assert get_settings(db)["domain_krank"] == ""          # Fehler → nichts gespeichert
    admin.post("/admin/domains", data={"csrf": token, "krank": "https://Krank.Example.org/"})
    with SessionLocal() as db:
        from app.db import get_settings
        assert get_settings(db)["domain_krank"] == "krank.example.org"
    admin.post("/admin/domains", data={"csrf": token, "krank": ""})
    reset()


def test_all_registered_modules_have_explicit_domain_policy():
    """Mandatory CI gate: adding a module requires a domain exposure decision."""
    modhosts.assert_module_coverage(main.MODULES)
    assert set(modhosts.MODULE_PUBLIC).isdisjoint(modhosts.PORTAL_ONLY)
    assert set(main.MODULES) == set(modhosts.MODULE_PUBLIC) | set(modhosts.PORTAL_ONLY)


def test_domain_policy_rejects_unclassified_and_stale_modules():
    import pytest

    with pytest.raises(ValueError, match="future_public_module"):
        modhosts.assert_module_coverage({**main.MODULES, "future_public_module": ("Neu", "module_new", ())})
    with pytest.raises(ValueError, match="unbekannt"):
        modhosts.assert_module_coverage({})


def test_admin_domains_shows_portal_only_module_policy():
    admin = login("admin@example.org", "admin-passwort-123")
    page = admin.get("/admin/domains")
    assert page.status_code == 200
    from html import unescape
    readable_html = unescape(page.text)
    for key in modhosts.PORTAL_ONLY:
        assert main.MODULES[key][0] in readable_html
    assert "Module ohne eigene öffentliche Domain" in page.text
    assert "Interne Verwaltungsseiten" in page.text
