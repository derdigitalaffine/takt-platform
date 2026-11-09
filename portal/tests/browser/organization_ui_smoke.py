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
                expect(p.locator(".admin-org-workspace > header.workspace-head")).to_be_visible()
                assert p.locator(".workspace-head").evaluate("el => getComputedStyle(el).backgroundImage === 'none'")
                assert p.locator(".workspace-head").bounding_box()["height"] < 160

                tree = p.get_by_role(
                    "navigation", name="Organisationseinheiten", exact=True
                )
                tree.get_by_role("link", name="Finanzen", exact=True).click()
                finance_url = p.url
                p.locator("summary").filter(
                    has_text="Personen zuordnen oder Zuordnungen ändern"
                ).click()
                picker = p.locator("#org-members [data-selection-picker]").first
                search = picker.locator("[data-selection-search]")
                search.fill("member@example.org")
                picker.get_by_role(
                    "button", name="Alle Treffer auswählen", exact=True
                ).click()
                expect(picker.locator("[data-selection-count]")).to_contain_text(
                    "1 ausgewählt"
                )
                search.fill("scope@example.org")
                expect(picker.locator("[data-selection-count]")).to_contain_text(
                    "1 ausgewählt"
                )
                picker.get_by_role(
                    "button", name="Alle Treffer auswählen", exact=True
                ).click()
                expect(picker.locator("[data-selection-count]")).to_contain_text(
                    "2 ausgewählt"
                )
                with p.expect_navigation(wait_until="domcontentloaded"):
                    p.get_by_role("button", name="Auswahl zuordnen", exact=True).click()
                expect(p.locator("#org-members .list-group")).to_contain_text(
                    "Alex Teilnahme"
                )
                expect(p.locator("#org-members .list-group")).to_contain_text(
                    "Hauptzuordnung"
                )
                expect(p.locator('.alert-danger[role="alert"]')).to_have_count(0)
                p.locator("#org-assignment > summary").click()
                p.screenshot(
                    path=str(OUTPUT / "organization-selection-desktop.png"),
                    full_page=True,
                )
                p.locator("#org-assignment > summary").click()
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
                    p.locator("#org-assignment").evaluate("(el)=>el.open=true")
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
                # The same rights-checked editor is reusable from organization
                # and users; its preview must describe actual field changes.
                p.goto(finance_url)
                p.locator("[data-org-person-editor]").first.click()
                drawer = p.locator("#org-person-drawer")
                expect(drawer.locator("[data-org-person-form]")).to_be_visible()
                preview = drawer.locator("[data-org-person-preview]")
                expect(preview).to_contain_text("Noch keine Änderungen")
                drawer.locator('details[open] input[name^="role_"]:not(:checked)').first.check()
                expect(preview).to_contain_text("Rolle")
                expect(preview).to_contain_text("Organisationseinheiten prüfen")
                p.set_viewport_size({"width": 390, "height": 844})
                assert p.evaluate("document.documentElement.scrollWidth<=innerWidth+1")
                drawer.get_by_role("button", name="Schließen").click()
                expect(drawer).to_be_hidden()
                p.set_viewport_size({"width": 1440, "height": 1000})
                p.goto(BASE + "/admin/users")
                expect(p.locator(".admin-users-workspace > header.workspace-head")).to_be_visible()
                assert p.locator(".workspace-head").evaluate("el => getComputedStyle(el).backgroundImage === 'none'")
                assert p.locator(".workspace-head").bounding_box()["height"] < 160
                expect(p.locator("body")).to_contain_text("Finanzplanung")
                expect(p.locator("body")).to_contain_text("Hauptzuordnung")
                expect(p.locator(".admin-users-workspace")).to_be_visible()
                expect(p.locator("#admin-user-query")).to_be_visible()
                expect(p.locator("#admin-user-status")).to_be_visible()
                expect(p.locator("#admin-users-heading")).to_be_visible()
                assert p.locator("#admin-group-editor-modal").count() == 0
                p.locator('[data-admin-group-editor="0"]').click()
                group_modal = p.locator("#admin-group-editor-modal")
                expect(group_modal).to_be_visible()
                expect(group_modal.locator("#admin-group-members")).to_have_count(1)
                group_modal.get_by_role("button", name="Schließen").click()
                expect(group_modal).to_have_count(0)
                p.set_viewport_size({"width": 390, "height": 844})
                assert p.evaluate("document.documentElement.scrollWidth<=window.innerWidth+1")
                p.screenshot(path=str(OUTPUT / "users-mobile.png"), full_page=True)
                p.set_viewport_size({"width": 1440, "height": 1000})
                p.locator("#admin-user-query").fill("Lea Bereich")
                p.get_by_role("button", name="Anwenden", exact=True).click()
                expect(p.locator("#admin-user-query")).to_have_value("Lea Bereich")
                expect(p.locator(".admin-users-table .admin-user-row")).to_have_count(1)
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
