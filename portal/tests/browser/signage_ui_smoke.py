"""Create and publish a passive sign through the portal, then check the kiosk in Chromium."""
import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
from time import sleep

import httpx
from playwright.sync_api import expect, sync_playwright


BASE = "http://127.0.0.1:8786"


def exercise():
    options = {}
    executable = os.getenv("PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH")
    if executable:
        options["executable_path"] = executable
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(**options)
        page = browser.new_page()
        page.set_default_timeout(8000)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(BASE + "/login")
        page.locator('[name="email"]').fill("signage@example.org")
        page.locator('[name="password"]').fill("browser-test-password")
        page.locator('button[type="submit"]').click()
        page.goto(BASE + "/signage")
        row = page.locator("tr").filter(has_text="Bürgerbüro")
        row.get_by_label("Raum 01 freigeben").check()
        row.get_by_role("button", name="Freigabe speichern").click()

        wizard = page.locator('form[action="/signage/new"]')
        wizard.get_by_label("Name").fill("Wegweiser am Eingang")
        wizard.get_by_label("Vorlage").select_option("sign_corridor")
        wizard.locator("[name=building_id]").select_option(label="Rathaus")
        wizard.locator("[name=floor_id]").select_option(label="Erdgeschoss")
        wizard.locator("[name=node_id]").select_option(label="Eingang · Erdgeschoss")
        wizard.locator("[name=facing]").select_option("north")
        wizard.get_by_role("button", name="Anzeige gestalten").click()
        expect(page.get_by_role("heading", name="Anzeigebereich und Pfeile")).to_be_visible()
        page.get_by_label("Zugriffsart").select_option("public")
        page.get_by_role("button", name="Speichern", exact=True).click()
        screen_id = re.search(r"/signage/(\d+)/edit", page.url)[1]
        assert not errors, errors

        for width, height in ((1280, 720), (540, 960)):
            kiosk = browser.new_page(viewport={"width": width, "height": height})
            kiosk.goto(f"{BASE}/signage/view/{screen_id}")
            expect(kiosk.get_by_text("Bürgerbüro", exact=True)).to_be_visible()
            expect(kiosk.get_by_text("Rechts", exact=True)).to_be_visible()
            expect(kiosk.locator("button, input, select, details")).to_have_count(0)
            assert kiosk.evaluate("document.documentElement.scrollWidth === innerWidth")
            assert kiosk.evaluate("document.documentElement.scrollHeight <= innerHeight")
            # A disconnected kiosk must immediately mask stale room and
            # special-event details; no input elements appear on the screen.
            kiosk.evaluate("window.dispatchEvent(new Event('offline'))")
            expect(kiosk.locator("[data-sg-stale]")).to_be_visible()
            expect(kiosk.get_by_text("Informationen momentan nicht verfügbar")).to_be_visible()
            kiosk.close()

        # Central building action is configured once and picked up by the
        # existing passive corridor without editing its individual settings.
        page.goto(BASE + "/signage/campaigns")
        campaign = page.locator("#sg-central-form")
        campaign.locator("[name=preset]").select_option("postal")
        campaign.locator("[name=building_id]").select_option(label="Rathaus")
        building_id = campaign.locator("[name=building_id]").input_value()
        expect(campaign.locator("[name=room_id]")).not_to_have_value("")
        campaign.locator("[name=title]").fill("Briefwahlstelle heute")
        local_now = datetime.now(ZoneInfo("Europe/Berlin"))
        # Portal's accessible German date widget wraps the canonical native
        # datetime-local input. Exercise its *visible* text proxy.
        campaign.locator("[name=starts_at]").locator("xpath=..").locator(
            "input[type=text]").fill(
            (local_now - timedelta(minutes=5)).strftime("%d.%m.%Y, %H:%M"))
        campaign.locator("[name=ends_at]").locator("xpath=..").locator(
            "input[type=text]").fill(
            (local_now + timedelta(minutes=45)).strftime("%d.%m.%Y, %H:%M"))
        campaign.locator("[name=published]").check()
        campaign.get_by_role("button", name="Sonderanzeige anlegen").click()
        expect(page.get_by_text("Briefwahlstelle heute", exact=True)).to_be_visible()

        display = browser.new_page(viewport={"width": 1280, "height": 720})
        display.goto(f"{BASE}/signage/view/{screen_id}")
        expect(display.locator(".sd-special").get_by_text("Briefwahlstelle heute")).to_be_visible()
        expect(display.locator("input, button, select, details")).to_have_count(0)
        assert not errors, errors
        display.close()

        simulation_at = local_now.strftime("%Y-%m-%dT%H:%M")
        page.goto(f"{BASE}/signage/campaigns/simulate?building_id={building_id}&at={simulation_at}")
        expect(page.get_by_text("Briefwahlstelle heute")).to_be_visible()

        # Pair a real API player and verify the operations dashboard.
        page.goto(f"{BASE}/signage/{screen_id}/edit")
        registration = page.locator(f'form[action="/signage/{screen_id}/device"]')
        registration.locator('[name=name]').fill("Empfangsmonitor Probelauf")
        registration.get_by_role("button", name="Geräteschlüssel erstellen").click()
        secret_text = page.locator("#sg-secret").inner_text()
        found = re.search(r"Gerät-ID: (\d+)\s+Bearer: ([\w-]+)", secret_text)
        assert found, "One-time pairing secret must be visible"
        device_id, device_token = found.group(1), found.group(2)
        pulse = httpx.post(
            f"{BASE}/signage/api/device/{device_id}/heartbeat",
            headers={"Authorization": f"Bearer {device_token}"},
            json={"platform": "browser", "client_version": "1.0.0",
                  "screen_width": 1280, "screen_height": 720,
                  "diagnostic_code": "ok"}, trust_env=False)
        assert pulse.status_code == 200, pulse.text
        page.goto(BASE + "/signage/fleet")
        expect(page.get_by_role("heading", name="Geräte & Betriebszustand")).to_be_visible()
        device = page.locator(f'[data-device-id="{device_id}"]')
        expect(device.get_by_text("Empfangsmonitor Probelauf")).to_be_visible()
        expect(device.locator("[data-fleet-health]")).to_contain_text("Online")
        assert device_token not in page.content()
        browser.close()


with TemporaryDirectory(prefix="takt-signage-browser-") as temp:
    root = Path(temp)
    env = {
        **os.environ, "DATA_DIR": str(root / "data"), "RECORDINGS_DIR": str(root / "recordings"),
        "CADDY_CONF_DIR": str(root / "caddy"), "PORTAL_BASE_URL": BASE,
        "PORTAL_SECRET_KEY": "signage-browser-only-key-over-32-characters",
        "JWT_APP_SECRET": "signage-browser-jwt-over-32-characters",
    }
    with (root / "server.log").open("w") as log:
        server = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "signage_ui_app:app", "--app-dir", "tests/browser",
             "--host", "127.0.0.1", "--port", "8786", "--lifespan", "off"],
            env=env, stdout=log, stderr=subprocess.STDOUT,
        )
        try:
            for _ in range(80):
                try:
                    if httpx.get(BASE + "/login", trust_env=False).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                sleep(0.25)
            else:
                raise AssertionError("Signage browser server did not start")
            exercise()
        except Exception:
            print("\n".join((root / "server.log").read_text().splitlines()[-35:]))
            raise
        finally:
            server.terminate()
            server.wait(timeout=10)
print("Signage browser smoke passed.")
