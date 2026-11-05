"""Organization workflows, scoped editing and responsive/no-JS contracts."""

import os, subprocess, sys, tempfile, time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright, expect

BASE = "http://127.0.0.1:8768"
OUTPUT = Path("/tmp/takt-organization-browser")
OUTPUT.mkdir(exist_ok=True)


def login(p, email="planner@example.org"):
    p.goto(BASE + "/login")
    p.get_by_label("E-Mail", exact=True).fill(email)
    p.get_by_label("Passwort", exact=True).fill("browser-test-password")
    p.get_by_role("button", name="Anmelden", exact=True).click()


with tempfile.TemporaryDirectory(prefix="takt-org-") as root:
    env = {
        **os.environ,
        "DATA_DIR": root + "/data",
        "RECORDINGS_DIR": root + "/recordings",
        "CADDY_CONF_DIR": root + "/caddy",
        "PORTAL_ROOMS_FILE": root + "/rooms.json",
        "PORTAL_CHAT_DIR": root + "/chat",
    }
    with open(OUTPUT / "server.log", "w") as log:
        server = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "organization_ui_app:app",
                "--app-dir",
                "tests/browser",
                "--host",
                "127.0.0.1",
                "--port",
                "8768",
                "--lifespan",
                "off",
            ],
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        try:
            for _ in range(80):
                try:
                    if httpx.get(BASE + "/login", trust_env=False).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.25)
            else:
                raise AssertionError((OUTPUT / "server.log").read_text())
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                ctx = browser.new_context(viewport={"width": 1440, "height": 1000})
                p = ctx.new_page()
                errors = []
                p.on("pageerror", lambda e: errors.append(str(e)))
                login(p)
                assert p.goto(BASE + "/admin/organization").status == 200
                tree = p.get_by_role(
                    "navigation", name="Organisationseinheiten", exact=True
                )
                tree.get_by_role("link", name="Finanzen", exact=True).click()
                finance_url = p.url
                p.locator("summary").filter(
                    has_text="Person zuordnen oder Zuordnung ändern"
                ).click()
                p.locator("#org-person").select_option(
                    label="Alex Teilnahme · member@example.org"
                )
                p.get_by_role("button", name="Zuordnung speichern", exact=True).click()
                expect(p.locator("#org-members")).to_contain_text("Alex Teilnahme")
                expect(p.locator("#org-members")).to_contain_text("Hauptzuordnung")
                p.locator("summary").filter(
                    has_text="Organisationseinheit anlegen"
                ).click()
                p.get_by_label("Name der neuen Einheit", exact=True).fill(
                    "Team Haushalt"
                )
                p.get_by_role("button", name="Einheit anlegen", exact=True).click()
                expect(
                    p.get_by_role("heading", name="Team Haushalt", exact=True)
                ).to_be_visible()
                expect(p.locator("#org-roles")).to_contain_text("geerbt")
                p.goto(finance_url)
                p.screenshot(
                    path=str(OUTPUT / "organization-desktop.png"), full_page=True
                )
                for width in (360, 768):
                    p.set_viewport_size({"width": width, "height": 900})
                    p.emulate_media(color_scheme="dark")
                    p.wait_for_timeout(350)
                    p.screenshot(
                        path=str(OUTPUT / f"organization-{width}-debug.png"),
                        full_page=True,
                    )
                    assert p.evaluate(
                        "document.documentElement.scrollWidth<=innerWidth+1"
                    ), p.locator("body *").evaluate_all(
                        "es=>[document.documentElement.scrollWidth,innerWidth,...es.filter(e=>e.getBoundingClientRect().right>innerWidth+1)].map(e=>typeof e==='number'?e:[e.tagName,e.className,e.getBoundingClientRect().right,getComputedStyle(e).overflowX]).slice(0,25)"
                    )
                    p.screenshot(
                        path=str(OUTPUT / f"organization-{width}-dark.png"),
                        full_page=True,
                    )
                p.set_viewport_size({"width": 1440, "height": 1000})
                p.goto(BASE + "/admin/users")
                expect(p.locator("body")).to_contain_text("Finanzplanung")
                expect(p.locator("body")).to_contain_text("Hauptzuordnung")
                scoped = browser.new_context(
                    java_script_enabled=False, viewport={"width": 390, "height": 900}
                )
                q = scoped.new_page()
                login(q, "scope@example.org")
                q.goto(finance_url)
                expect(
                    q.get_by_role("heading", name="Finanzen", exact=True)
                ).to_be_visible()
                expect(
                    q.get_by_role("button", name="Rolle vergeben", exact=True)
                ).to_have_count(0)
                expect(
                    q.get_by_label("Übergeordnete Einheit", exact=True)
                ).to_have_count(0)
                q.get_by_label("Name", exact=True).fill("Finanzen und Haushalt")
                q.get_by_label("Name", exact=True).press("Enter")
                expect(
                    q.get_by_role("heading", name="Finanzen und Haushalt", exact=True)
                ).to_be_visible()
                expect(
                    q.get_by_role(
                        "navigation", name="Organisationseinheiten", exact=True
                    ).get_by_role("link", name="Bauen", exact=True)
                ).to_have_count(0)
                assert q.goto(BASE + "/admin/users").status == 403
                assert not errors, errors
                browser.close()
        finally:
            server.terminate()
            server.wait(timeout=10)
print(
    "Organization UI passed: memberships, hierarchy, inherited roles, scope isolation, mobile, dark and no-JS."
)
