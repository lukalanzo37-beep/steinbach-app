# Immobilienservice Steinbach – V16 Pre-Launch

Diese Version ist für den letzten technischen Pilot vor dem echten Kundeneinsatz gedacht. Sie enthält das bestehende Full-Stack-Portal plus zusätzliche Rechteprüfungen, einen Launch-Readiness-Check und einen erweiterten Pre-Launch-Test.

# Immobilienservice Steinbach – V16 Pilot

V16 ist die nächste Pilotstufe der Steinbach-Web-App. Öffentliche Website, Kundenportal, Mitarbeitercockpit und Adminbereich laufen in **einer Anwendung** auf FastAPI mit SQLite.

## Neu in V16

- **serverseitige Terminplanung** statt lokaler Demo-Termine
- Kunden können Wunschtermine anfragen
- Mitarbeiter/Admins können Termine bestätigen, verschieben, zuweisen und abschließen
- Termine werden mit Kundenportal und Ticketstatus synchronisiert
- **Web-Push-Infrastruktur** mit Service Worker und VAPID
- Push-Abos werden pro Benutzer/Gerät gespeichert
- dringende Tickets, Nachrichten und Statusänderungen können Push auslösen
- **Passwort vergessen** mit zeitlich begrenztem Reset-Token
- **Einladungsprozess** für Kunden, Mitarbeiter und Admins
- Einladungslinks laufen nach 72 Stunden ab
- **MFA/TOTP für Admins** mit Authenticator-App
- lokale E-Mail-Outbox; optional echter SMTP-Versand
- bestehende Funktionen aus V14 bleiben erhalten: Tickets, Rollen, Nachrichten, Uploads, Leistungsänderungen, Empfehlungen, Audit-Log, PWA

## Schnellstart unter Windows

1. Python 3.11+ installieren.
2. ZIP entpacken.
3. Terminal in diesem Ordner öffnen.
4. Abhängigkeiten installieren:

```bat
pip install -r requirements.txt
```

5. `start_demo.bat` starten.
6. Im Browser öffnen: `http://127.0.0.1:8000`

### Demo-Zugänge

- Kunde: `kunde@steinbach.local` / `Kunde!2026Demo`
- Mitarbeiter: `mitarbeiter@steinbach.local` / `Mitarbeiter!2026Demo`
- Admin: `admin@steinbach.local` / `Admin!2026Demo`

Die Demo legt diese Konten nur an, wenn `STEINBACH_DEMO_SEED=1` gesetzt ist.

**Nie mit diesen Zugangsdaten produktiv starten.**

## Was sofort lokal getestet werden kann

- Login und Rollen
- Kundenobjekte
- Ticket/Meldung inkl. Priorität
- Foto/PDF-Upload
- Nachrichten
- Termine anfragen und intern bearbeiten
- Leistungsänderungen
- Empfehlungen
- Admin-Einladungen
- Passwort-Reset im Dev-Modus
- Admin-MFA mit Authenticator-App
- PWA-Installation auf localhost
- Push-Abo-Oberfläche, sobald VAPID konfiguriert ist

## Web-Push aktivieren

Nach Installation der Requirements:

```bat
python generate_vapid_keys.py
```

Die ausgegebenen Werte in die Umgebung bzw. `.env` übernehmen. Details stehen in `VAPID-SETUP.md`.

Für echten Push auf Mobilgeräten ist **HTTPS** erforderlich. `localhost` darf von Browsern zu Testzwecken als sicherer Kontext behandelt werden.

## E-Mail für Einladungen und Passwort-Reset

Ohne SMTP-Konfiguration werden E-Mails in der Tabelle `email_outbox` gespeichert. Im Demo-Modus werden Reset-/Einladungslinks zusätzlich in der API-Antwort zurückgegeben.

Für echten Versand diese Variablen konfigurieren:

- `STEINBACH_SMTP_HOST`
- `STEINBACH_SMTP_PORT`
- `STEINBACH_SMTP_USER`
- `STEINBACH_SMTP_PASSWORD`
- `STEINBACH_SMTP_FROM`
- `STEINBACH_SMTP_TLS=1`

Dann `STEINBACH_DEV_SHOW_TOKENS=0` setzen.

## Für einen echten Pilotbetrieb zwingend

- HTTPS + `STEINBACH_COOKIE_SECURE=1`
- `STEINBACH_DEMO_SEED=0`
- `STEINBACH_DEV_SHOW_TOKENS=0`
- starke individuelle Konten
- MFA für alle Admins aktivieren
- produktive SMTP-Konfiguration
- VAPID-Schlüssel sicher hinterlegen
- regelmäßige Datenbank- und Upload-Backups
- Logging/Monitoring einrichten
- Datenschutz, Aufbewahrungsfristen und AV-Verträge prüfen
- MFA-Secrets in einer produktiven Umgebung verschlüsselt speichern oder auf einen Managed-Identity-Provider umstellen
- SQLite vor größerem Betrieb gegen PostgreSQL tauschen

## API-Dokumentation

Lokal: `http://127.0.0.1:8000/docs`

## Wichtiger Status

V16 ist **Pilotsoftware**, nicht als ungeprüfte Produktionssoftware freigegeben. Die Kernabläufe laufen serverseitig, aber ein echter Start mit Kundendaten sollte erst nach Hosting-, Security- und Datenschutzprüfung erfolgen.

## Backup erstellen

Während oder vor einem Pilotbetrieb regelmäßig ausführen:

```bash
python backup.py
```

Das Script erzeugt ein konsistentes ZIP mit SQLite-Datenbank und Uploads im Ordner `backups/`.

## Smoke-Test

Wenn die App bereits läuft:

```bash
python smoke_test.py
```

Der Test prüft Health, Kundenlogin, Objekte, Tickets, Termine und Logout.


## V16 Qualitätsprüfung

```bash
python prelaunch_test.py
```

Der Test muss mit `PRELAUNCH TEST OK` enden. Zusätzlich liefert `/api/readiness` den Produktionsstatus. Siehe `PRELAUNCH-QA-REPORT.md` und `PRODUCTION-GO-LIVE.md`.
