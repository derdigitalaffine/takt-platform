# SearXNG als optionale TAKT-KI-Websuche

TAKT kann öffentliche Internetquellen über eine **selbst gehostete SearXNG-Metasuche** oder weiterhin über die Brave Search API recherchieren. SearXNG erhebt keine eigene API-Gebühr, benötigt aber Zugriff auf externe Suchmaschinen, die Anfragen drosseln oder mit CAPTCHA blockieren können.

## Erstinstallation

Bei \`./scripts/setup.sh\` die Frage **„Kostenlose lokale SearXNG-Websuche installieren?“** mit \`j\` beantworten. Standard ist **nein**. Das Skript erzeugt nur bei Aktivierung ein zufälliges \`SEARXNG_SECRET\`, fügt das Compose-Profil \`searxng\` hinzu und behält andere Profile wie \`rag\` bei.

\`\`\`bash
./scripts/setup.sh
docker compose up -d --build
docker compose ps searxng
\`\`\`

## Nachträglich aktivieren / deaktivieren

Das vorhandene Setup-Skript ist idempotent: Bei vorhandener \`.env\` bleiben Domains, Passwörter und andere Secrets **unverändert**. Es verwaltet dann nur den SearXNG-Schalter (interaktiv oder direkt mit einem Flag).

\`\`\`bash
./scripts/setup.sh --enable-searxng
docker compose up -d --build

# Später deaktivieren:
./scripts/setup.sh --disable-searxng
docker compose --profile searxng stop searxng
docker compose up -d --build
\`\`\`

**Achtung:** \`--force\` richtet die gesamte \`.env\` neu ein und kann bestehende Zugangsdaten ersetzen. Für SearXNG nie nötig.

## Im Portal freigeben

1. **Admin → KI → Optionale KI-Websuche** öffnen.
2. Anbieter **„Nur SearXNG“** auswählen (empfohlen, damit keine Brave-Weiterleitung geschieht); alternativ „Automatisch“ oder „Nur Brave“.
3. **KI-Websuche freigeben** aktivieren und speichern. Das KI-Modul selbst muss aktiv sein.
4. Berechtigten Benutzern das Recht **KI-Websuche** geben. Pro Chatnachricht muss die Person die Websuche ausdrücklich auswählen.

Der Setup-Schalter allein gibt **noch keinem Benutzer** die KI-Websuche frei. Ein bisheriger Brave-Schlüssel bleibt verschlüsselt in der Portaldatenbank und wird nicht gelöscht oder überschrieben.

## Sicherheit und Betrieb

- SearXNG wird mit dem Docker-Profil \`searxng\` gestartet; ohne Aktivierung läuft der Container nicht.
- **Keine Host-Ports** und kein Caddy-Routing. Das Portal kommuniziert über \`http://searxng:8080/search\` im privaten Docker-Netz \`search_private\`.
- SearXNG hat ein zweites Netz \`search_egress\` ausschließlich für die benötigten externen Suchanfragen. Ein **rein internes** Netz würde die externe Suche verhindern.
- Nur die aktuelle Benutzerfrage (höchstens 75 Wörter / 600 Zeichen) wird übertragen. Weiterleitungen, Umgebungsproxies und beliebige Ziel-URLs sind deaktiviert.
- Antworten sind auf 200 KB begrenzt; nur eindeutig öffentliche HTTPS-Quellen werden in den KI-Kontext übernommen.
- Der bestehende Websuche-Ratelimiter greift pro Benutzer (6 Suchanfragen / 60 Sekunden). Dies ersetzt nicht die Nutzungsgrenzen externer Suchmaschinen.
- Administratoren können die Websuche jederzeit zentral abschalten, was auch die Anzeige gespeicherter webquellenbasierter Antworten einschränkt.
- Keine automatische Umschaltung bei Ausfällen: Ein explizit gewählter SearXNG-Anbieter fällt **nicht** ohne Zustimmung auf Brave zurück.
- Bei produktivem Betrieb einen geprüften, festen \`SEARXNG_IMAGE_VERSION\`-Tag in \`.env\` eintragen und Updates kontrolliert durchführen.

Diagnose:

\`\`\`bash
docker compose ps searxng
docker compose logs --tail=100 searxng
# Keine öffentlich freigegebene URL/API
\`\`\`

Der Suchdienst ist nicht direkt vom Host erreichbar. Ein externer Direkt-Test erfolgt bei Bedarf innerhalb des Portal-Netzes, nicht durch Freigabe eines Ports.
