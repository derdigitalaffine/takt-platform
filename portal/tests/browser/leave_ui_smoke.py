"""Exercise real leave and calendar forms with isolated organizational fixtures."""

import os, subprocess, sys, tempfile, time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright, expect

base = "http://127.0.0.1:8769"
with tempfile.TemporaryDirectory(prefix="takt-leave-") as root:
    env = {
        **os.environ,
        "DATA_DIR": root + "/data",
        "RECORDINGS_DIR": root + "/recordings",
        "CADDY_CONF_DIR": root + "/caddy",
        "PORTAL_ROOMS_FILE": root + "/rooms.json",
        "PORTAL_CHAT_DIR": root + "/chat",
    }
    logpath = Path("/tmp/takt-leave-browser.log")
    with logpath.open("w") as log:
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
                "8769",
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
                    if httpx.get(base + "/login", trust_env=False).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.25)
            else:
                raise AssertionError(logpath.read_text())
            with sync_playwright() as pw:
                browser = pw.chromium.launch()
                p = browser.new_page(viewport={"width": 1440, "height": 1000})
                errors = []
                p.on("pageerror", lambda e: errors.append(str(e)))
                p.goto(base + "/login")
                p.get_by_label("E-Mail", exact=True).fill("planner@example.org")
                p.get_by_label("Passwort", exact=True).fill("browser-test-password")
                p.get_by_role("button", name="Anmelden", exact=True).click()
                p.goto(base + "/urlaub")
                p.get_by_label("Organisationseinheit", exact=True).select_option(
                    label="Finanzen"
                )
                p.get_by_role("button", name="Anzeigen", exact=True).click()
                p.locator("#leave-starts_on-display").fill("07.12.2026")
                p.locator("#leave-ends_on-display").fill("09.12.2026")
                p.get_by_role(
                    "button", name="Als geplant speichern", exact=True
                ).click()
                expect(p.locator("article")).to_contain_text("Geplant")
                expect(p.locator("#leave-calendar .fc-toolbar-title")).to_contain_text(
                    "Dezember 2026"
                )
                p.get_by_role("button", name="Quartal", exact=True).click()
                p.reload()
                expect(
                    p.locator(".fc-taktPeopleQuarter-button.fc-button-active")
                ).to_have_count(1)
                p.get_by_role("button", name="Monat", exact=True).click()
                expect(p.locator("#leave-calendar .fc-toolbar-title")).to_contain_text(
                    "Dezember 2026"
                )
                p.get_by_role(
                    "button", name="Verbindlich markieren", exact=True
                ).click()
                expect(p.locator("article > p").first).to_contain_text("Verbindlich")
                p.get_by_role("button", name="Zeitraum bearbeiten", exact=True).click()
                p.locator("#leave-starts_on-display").fill("14.12.2026")
                p.locator("#leave-ends_on-display").fill("16.12.2026")
                p.get_by_role("button", name="Konflikte prüfen", exact=True).click()
                expect(p.locator("#leave-preview")).to_be_visible()
                p.get_by_role(
                    "button", name="Änderung als Entwurf speichern", exact=True
                ).click()
                expect(p.locator("article")).to_contain_text(
                    "Bisheriger verbindlicher Zeitraum"
                )
                with p.expect_navigation(wait_until="domcontentloaded"):
                    p.get_by_role(
                        "button", name="Verbindlich markieren", exact=True
                    ).click()
                expect(p.locator("article > p").first).to_contain_text("Verbindlich")
                expect(p.locator("#leave-calendar .pt-table")).to_be_visible()
                p.set_viewport_size({"width": 390, "height": 844})
                p.wait_for_function(
                    "document.documentElement.scrollWidth<=innerWidth+1"
                )
                p.screenshot(
                    path="/tmp/takt-leave-mobile.png",
                    full_page=True,
                    animations="disabled",
                )
                p.set_viewport_size({"width": 1440, "height": 1000})
                p.goto(base + "/kalender")
                p.locator("summary").filter(has_text="Kalender anlegen").click()
                p.get_by_label("Name", exact=True).fill("Gemeinsame Jahrestermine")
                p.get_by_role("button", name="Kalender anlegen", exact=True).click()
                expect(
                    p.get_by_label("Gemeinsame Jahrestermine", exact=True)
                ).to_be_visible()
                calendar_id = p.get_by_label(
                    "Gemeinsame Jahrestermine", exact=True
                ).get_attribute("data-calendar")
                p.goto(base + f"/kalender/{calendar_id}/teilen")
                picker = p.locator("[data-selection-picker]")
                picker.locator("[data-selection-search]").fill("member@example.org")
                picker.get_by_role(
                    "button", name="Alle Treffer auswählen", exact=True
                ).click()
                picker.locator("[data-selection-search]").fill("scope@example.org")
                picker.get_by_role(
                    "button", name="Alle Treffer auswählen", exact=True
                ).click()
                expect(picker.locator("[data-selection-count]")).to_contain_text(
                    "2 ausgewählt"
                )
                with p.expect_navigation(wait_until="domcontentloaded"):
                    p.get_by_role(
                        "button", name="Freigabe für Auswahl speichern", exact=True
                    ).click()
                expect(
                    p.get_by_role("button", name="Freigabe entziehen", exact=True)
                ).to_have_count(2)
                p.goto(base + "/kalender")
                p.locator("#event-editor summary").click()
                form = p.locator("#calendar-event-form")
                form.get_by_label("Titel", exact=True).fill("Jahresauftakt")
                form.get_by_label("Ganztägig", exact=True).check()
                form.locator("#calendar-start-display").fill("01.12.2026")
                form.locator("#calendar-end-display").fill("02.12.2026")
                form.get_by_role("button", name="Termin speichern", exact=True).click()
                expect(form.get_by_label("Titel", exact=True)).to_have_value("")
                expect(p.locator("#event-error")).to_have_text("")
                form.get_by_label("Art", exact=True).select_option("closure")
                form.get_by_label("Titel", exact=True).fill("Betriebsruhe")
                form.get_by_label(
                    "Betroffener Bereich einschließlich Untereinheiten", exact=True
                ).select_option(label="Finanzen")
                form.get_by_label("Mindest-Notbesetzung", exact=True).fill("1")
                form.locator("#calendar-start-display").fill("28.12.2026")
                form.locator("#calendar-end-display").fill("30.12.2026")
                expect(form.get_by_label("Ort", exact=True)).to_be_hidden()
                form.get_by_role("button", name="Termin speichern", exact=True).click()
                expect(form.get_by_label("Titel", exact=True)).to_have_value("")
                p.goto(base + "/urlaub")
                p.get_by_label("Organisationseinheit", exact=True).select_option(
                    label="Finanzen"
                )
                p.get_by_role("button", name="Anzeigen", exact=True).click()
                closed = p.get_by_role(
                    "heading", name="Schließzeit: Betriebsruhe", exact=True
                ).locator("..")
                expect(closed).to_contain_text("Notbesetzung in")
                with p.expect_navigation(wait_until="domcontentloaded"):
                    closed.get_by_role(
                        "button", name="Zur Notbesetzung eintragen", exact=True
                    ).click()
                expect(
                    p.get_by_text("1 Person zur Notbesetzung eingeteilt.", exact=True)
                ).to_be_visible()
                assert not errors, errors
                browser.close()
        finally:
            server.terminate()
            server.wait(timeout=10)
print("Leave and calendar browser form checks passed")
