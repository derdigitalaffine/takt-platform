# Passkeys (WebAuthn) – TAKT-Portal

## Einrichtung als Benutzer

1. Mit Passwort oder dem bestehenden OIDC-Anbieter anmelden.
2. Profil → Sicherheit → Passkeys öffnen.
3. Gerät benennen (z. B. Dienstlaptop), das aktuelle Passwort eingeben oder bei einem OIDC-only-Konto innerhalb von zehn Minuten nach OIDC-Anmeldung fortfahren.
4. Passkey einrichten wählen und die Gerätesperre (Windows Hello, Face ID, Touch ID, PIN, FIDO2-Sicherheitsschlüssel oder synchronisierten Passwortmanager) bestätigen.
5. Beim nächsten Besuch auf der Anmeldeseite Mit Passkey anmelden verwenden.

Mehrere Passkeys pro Konto sind möglich (maximal 15). Im Sicherheitsprofil lassen sich die einzelnen Passkeys nach erneuter Passwortbestätigung entfernen. Verlorenes Gerät: mit Passwort/OIDC anmelden und den betreffenden Passkey entfernen. Ist auch das nicht mehr möglich, ist der Administrator zur Identitätsprüfung und zum Widerruf aller Passkeys des Kontos befugt.

## Verwaltung

Unter Benutzer & Gruppen stehen Passkey-Anzahlen und für Administratoren eine Widerruffunktion zur Verfügung (Auswahl des Kontos und erneute Passwortbestätigung bzw. frische OIDC-Anmeldung). Der Widerruf entfernt sämtliche zugehörigen WebAuthn-Zugangsdaten. Passwort, OIDC-Zuordnungen und andere Benutzerrechte bleiben unberührt.

## Technische und Sicherheitsvorgaben

- HTTPS ist Pflicht. PORTAL_BASE_URL=https://portal.beispiel.de muss exakt die tatsächliche Portaldomain inklusive Scheme und Port treffen. Die vertrauenswürdige Relying-Party-ID ist der Hostname dieser konfigurierten Adresse. Kein dynamisch aus Host-/Proxy-Headern abgeleiteter RP-Name.
- Browser benötigen WebAuthn und einen gültigen Secure Context; localhost/http dient nur Entwicklungszwecken.
- Registrierung und Anmeldung erzwingen User Verification und einen auffindbaren (resident/discoverable) Passkey.
- Alle Challenges entstehen serverseitig, sind an Zweck und ggf. aktive Sitzung gebunden, laufen nach 5 Minuten ab und werden atomar einmalig vor der Signaturprüfung beansprucht.
- Passkey-Signaturen, Challenge, Herkunft, RP-ID und Signaturzähler werden serverseitig geprüft. In der Datenbank stehen nur Credential-ID, zufällig erzeugter undurchsichtiger Benutzer-Handle, öffentlicher Schlüssel, Signaturzähler und Metadaten; keine privaten Schlüssel.
- Registrierung und Entfernen erfordern eine gültige Anmeldung und erneute Passwortbestätigung (bei reinen OIDC-Konten eine frische OIDC-Authentifizierung).
- CSRF-Schutz, IP-/Konten-Ratenbegrenzung und die vorhandene serverseitige Sitzungsregistrierung gelten weiterhin.
- Die Passkey-Nutzung ersetzt weder bestehende OIDC-Konten noch die Admin-Konfiguration von Zwei-Faktor-Verfahren.
- Jede Organisation sollte mindestens einen zweiten, unabhängigen Anmeldeweg oder mehrere Passkeys hinterlegen, um Aussperrungen zu vermeiden.

## Freigabeprüfungen

cd portal && pytest -q tests/test_passkeys.py tests/test_security.py tests/test_sessions.py

Zusätzlich die komplette CI ausführen und auf einer HTTPS-Staging-Umgebung mit echten Windows-Hello-/iOS-/Android-/FIDO2-Authentifikatoren testen. Nach Deployment müssen Datenbankmigration, Registrierung und Passwort-Rückfallpfad nachgewiesen sein.
