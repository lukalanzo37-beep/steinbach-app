# V16 Pre-Launch QA Report

Stand: 21.09.2026

## Automatisch ausgeführt

- Python-Syntaxprüfung für Backend, Datenbank und Security-Modul
- JavaScript-Syntaxprüfung für `pilot-backend.js`
- echter lokaler FastAPI-Start gegen separate Testdatenbank
- Health- und Readiness-Checks
- Login für Kunde, Mitarbeiter und Admin
- Rollen- und CSRF-Prüfungen
- Kundenisolation mit zwei getrennten Kundenkonten
- Mitarbeiterisolation mit zwei getrennten Mitarbeiterkonten
- Ticketanlage, Statusänderung und Zuweisung
- Objektanlage und Fremdobjekt-Abwehr
- Nachrichten und Fremdticket-Abwehr
- Terminanfrage
- Leistungsänderung und Admin-Freigabe
- Empfehlung und Admin-Freigabe
- Benachrichtigungen
- Passwort-Reset ohne Account-Leak
- Einladung/Account-Aktivierung
- Logout und Session-Ungültigkeit
- Security Header
- Manifest, Service Worker, robots.txt, sitemap.xml und Logo-Erreichbarkeit

Ergebnis des automatisierten API-Tests: `PRELAUNCH TEST OK`.

## Gefundene und behobene Punkte

1. **IDOR bei Kundennachrichten verhindert**
   Kunden können keine fremde Ticket-ID mehr an eine Nachricht hängen.

2. **Fremdobjekte bei Leistungsänderungen verhindert**
   `object_id` wird serverseitig auf Eigentümerschaft und Aktivstatus geprüft.

3. **Mitarbeiterrechte eingeschränkt**
   Mitarbeiter sehen und bearbeiten nur unzugewiesene oder ihnen selbst zugewiesene Tickets. Admins behalten Gesamtzugriff.

4. **Interne Ticketanlage gehärtet**
   Kunden-, Objekt- und Mitarbeiter-Zuordnung werden serverseitig validiert.

5. **Datei-/Ticketzugriff gehärtet**
   Mitarbeiterzugriff auf Uploads folgt denselben Ticketrechten.

6. **Zusätzliche Security Header**
   `X-Permitted-Cross-Domain-Policies` und `Cross-Origin-Opener-Policy` ergänzt.

7. **Launch-Readiness-Endpunkt**
   `/api/readiness` zeigt, ob wichtige Produktionsparameter korrekt gesetzt sind.

## Nicht vollständig in dieser Umgebung testbar

Ein echter Headless-Browser-Test gegen `localhost` wurde von der Ausführungsumgebung mit `ERR_BLOCKED_BY_ADMINISTRATOR` blockiert. Deshalb wurde kein echter Chromium-End-to-End-Klicktest als bestanden markiert. Die API, statischen Ressourcen und Backend-Abläufe wurden dagegen real gegen den laufenden Server getestet.

Vor echtem Kundeneinsatz zusätzlich auf realen Geräten testen:

- iPhone Safari / PWA
- Samsung/Android Chrome / PWA
- Desktop Chrome/Edge/Safari
- echte Web-Push-Zustellung über HTTPS
- SMTP-Zustellung über produktives Postfach
- Kamera/Foto-Upload auf realen Mobilgeräten
- Installations-/Updateverhalten des Service Workers

## Launch-Gate

Im Produktionsmodus muss `/api/readiness` mindestens folgende Pflichtchecks bestehen:

- Datenbank erreichbar
- HTTPS-Basis-URL
- Secure Session Cookie aktiv
- Demo-Seeding deaktiviert
- Entwicklungs-Tokens deaktiviert

SMTP und Push werden separat ausgewiesen und sollten vor breitem Rollout ebenfalls grün sein.
