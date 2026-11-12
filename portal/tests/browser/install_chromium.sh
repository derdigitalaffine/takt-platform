#!/usr/bin/env bash
set -euo pipefail

python -m playwright install chromium

# Hosted runners usually already have the libraries Chromium needs.
# Only contact the OS package mirror when Chromium cannot start.
if ! python - <<'PY'
from playwright.sync_api import sync_playwright

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    browser.close()
PY
then
    python -m playwright install-deps chromium
fi
