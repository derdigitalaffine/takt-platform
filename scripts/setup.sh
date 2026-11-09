#!/usr/bin/env bash
# Erzeugt .env mit Domains und zufälligen Secrets und legt die Datenordner an.
set -euo pipefail

cd "$(dirname "$0")/.."

# Mit denselben Optionen sowohl bei Neuinstallation als auch später aufrufbar.
SEARXNG_MODE=ask
FORCE=0
for arg in "$@"; do
  case "$arg" in
    --enable-searxng) SEARXNG_MODE=enable ;;
    --disable-searxng) SEARXNG_MODE=disable ;;
    --force) FORCE=1 ;;
    -h|--help)
      echo "Verwendung: ./scripts/setup.sh [--enable-searxng|--disable-searxng] [--force]"
      echo "Bei vorhandener .env werden ohne --force ausschließlich SearXNG-Optionen verwaltet."
      exit 0 ;;
    *) echo "Unbekannte Option: $arg" >&2; exit 2 ;;
  esac
done

gen() { openssl rand -hex 24; }

# .env niemals als Shellcode ausführen (untrusted Werte, mögliche Leerzeichen).
env_get() {
  [ -f .env ] || return 0
  sed -n "s/^$1=//p" .env | tail -n 1
}

env_set() {
  local key="$1" value="$2" temp
  temp="$(mktemp)"
  awk -v key="$key" -v value="$value" '
    index($0, key "=") == 1 {
      if (!found) { print key "=" value; found=1 }
      next
    }
    { print }
    END { if (!found) print key "=" value }
  ' .env > "$temp"
  cat "$temp" > .env
  rm -f "$temp"
  chmod 600 .env
}

configure_searxng() {
  local current choice answer profiles item joined
  local -a parts retained
  current="$(env_get SEARXNG_ENABLED)"
  choice="$SEARXNG_MODE"
  if [ "$choice" = ask ]; then
    if [ ! -t 0 ]; then
      echo "SearXNG unverändert (nicht interaktiver Aufruf; --enable-searxng / --disable-searxng verwenden)."
      return
    fi
    if [ "$current" = 1 ]; then
      read -r -p "Optionale, lokale SearXNG-Websuche aktiv lassen? [J/n]: " answer
      case "${answer,,}" in n|nein|no) choice=disable ;; *) choice=enable ;; esac
    else
      read -r -p "Kostenlose lokale SearXNG-Websuche installieren? [j/N]: " answer
      case "${answer,,}" in j|ja|y|yes) choice=enable ;; *) choice=disable ;; esac
    fi
  fi

  profiles="$(env_get COMPOSE_PROFILES)"
  IFS=',' read -r -a parts <<< "$profiles"
  retained=()
  for item in "${parts[@]}"; do
    item="${item//[[:space:]]/}"
    [ -z "$item" ] || [ "$item" = searxng ] || retained+=("$item")
  done

  if [ "$choice" = enable ]; then
    retained+=(searxng)
    # Secret bei Re-Konfiguration nie rotieren: sonst ändern sich die Einstellungen.
    if [ -z "$(env_get SEARXNG_SECRET)" ]; then
      env_set SEARXNG_SECRET "$(gen)"
    fi
    env_set SEARXNG_ENABLED 1
    echo "SearXNG aktiviert. Weiterhin gilt: KI-Websuche im Portal administrativ freigeben."
  else
    env_set SEARXNG_ENABLED 0
    echo "SearXNG deaktiviert. Bestehende Daten und andere Compose-Profile bleiben erhalten."
  fi
  joined="$(IFS=,; echo "${retained[*]}")"
  env_set COMPOSE_PROFILES "$joined"
}

if [ -f .env ] && [ "$FORCE" -eq 0 ]; then
  echo "== TAKT-Setup: vorhandene Installation =="
  echo "Domains, Admin-Zugang und alle bestehenden Secrets bleiben unverändert."
  configure_searxng
  echo
  echo "Änderungen übernehmen: docker compose up -d --build"
  echo "Beim Deaktivieren ggf. zuvor: docker compose --profile searxng stop searxng"
  exit 0
fi

ask() {
  local prompt="$1" default="${2:-}" answer
  if [ -n "$default" ]; then
    read -r -p "$prompt [$default]: " answer
    echo "${answer:-$default}"
  else
    read -r -p "$prompt: " answer
    echo "$answer"
  fi
}

echo "== Videokonferenzserver der Verbandsgemeinde Otterbach-Otterberg – Setup =="
MEET_DOMAIN=$(ask "Domain für die Videokonferenz" "meet.example.com")
PORTAL_DOMAIN=$(ask "Domain für das Portal" "portal.${MEET_DOMAIN#*.}")
ACME_EMAIL=$(ask "E-Mail für Zertifikats-Warnungen (Let's Encrypt, später im Portal einschaltbar)")
DETECTED_IP=$(curl -fs4 --max-time 5 https://api.ipify.org 2>/dev/null || true)
PUBLIC_IP=$(ask "Öffentliche IP des Servers" "${DETECTED_IP}")
ADMIN_EMAIL=$(ask "E-Mail des ersten Portal-Admins" "${ACME_EMAIL}")
ADMIN_PASSWORD=$(gen | cut -c1-20)

cp .env.example .env

set_var() {
  env_set "$1" "$2"
}

set_var MEET_DOMAIN "$MEET_DOMAIN"
set_var PORTAL_DOMAIN "$PORTAL_DOMAIN"
set_var ACME_EMAIL "$ACME_EMAIL"
set_var PUBLIC_URL "https://${MEET_DOMAIN}"
set_var JVB_ADVERTISE_IPS "$PUBLIC_IP"
set_var PORTAL_ADMIN_EMAIL "$ADMIN_EMAIL"
set_var PORTAL_ADMIN_PASSWORD "$ADMIN_PASSWORD"

for key in JWT_APP_SECRET JICOFO_AUTH_PASSWORD JVB_AUTH_PASSWORD JIGASI_XMPP_PASSWORD \
           JIGASI_TRANSCRIBER_PASSWORD JIBRI_RECORDER_PASSWORD JIBRI_XMPP_PASSWORD \
           PORTAL_SECRET_KEY; do
  set_var "$key" "$(gen)"
done
chmod 600 .env

# Optionale Komponente erst nach dem Speichern aller Installations-Secrets.
configure_searxng

mkdir -p data/{web/crontabs,transcripts,prosody/config,prosody/prosody-plugins-custom,jicofo,jvb,jibri,recordings,portal,caddy/data,caddy/config,caddy/conf,portal-rooms,portal-chat}
chmod +x jibri/finalize.sh
# Jibri schreibt als eigener Benutzer in das Aufnahmeverzeichnis
chmod 777 data/recordings
# Prosody schreibt die Chatprotokolle als eigener Benutzer
chmod 1777 data/portal-chat
# Andere Benutzer des Hosts sehen nichts davon (Container greifen über ihre Bind-Mounts direkt zu)
chmod 750 data
chmod 700 data/portal data/caddy/data

echo
echo "Fertig. .env wurde erzeugt."
echo
echo "  Konferenz:  https://${MEET_DOMAIN}"
echo "  Portal:     https://${PORTAL_DOMAIN}"
echo "  Admin:      ${ADMIN_EMAIL}"
echo "  Passwort:   ${ADMIN_PASSWORD}   (muss beim ersten Login geändert werden)"
echo
echo "Zertifikat: zunächst selbst signiert (Browser warnt). Let's Encrypt schalten Sie danach im"
echo "             Portal ein: Admin > HTTPS & Zertifikat (DNS muss auf diesen Server zeigen)."
echo
echo "Firewall: TCP 80, 443 und UDP ${JVB_PORT:-10000} freigeben."
echo "Start:     docker compose up -d --build"
