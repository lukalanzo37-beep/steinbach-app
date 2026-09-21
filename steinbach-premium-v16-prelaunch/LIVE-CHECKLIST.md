# Launch-Checkliste – Steinbach V15

## Infrastruktur
- [ ] Produktivdomain zeigt auf Hosting
- [ ] HTTPS/TLS aktiv
- [ ] `STEINBACH_COOKIE_SECURE=1`
- [ ] Reverse Proxy / Hosting-Timeouts geprüft
- [ ] Datenbank-Backup automatisiert
- [ ] Upload-Backup automatisiert

## Konten
- [ ] `STEINBACH_DEMO_SEED=0`
- [ ] `STEINBACH_DEV_SHOW_TOKENS=0`
- [ ] keine `.local`-Demo-Konten in Produktionsdatenbank
- [ ] Admins nur über Einladung
- [ ] Admin-MFA aktiv

## Kommunikation
- [ ] SMTP eingerichtet
- [ ] Passwort-Reset-E-Mail getestet
- [ ] Einladung getestet
- [ ] SPF/DKIM/DMARC geprüft
- [ ] VAPID eingerichtet
- [ ] Push auf Android getestet
- [ ] Push auf iPhone/PWA getestet

## Datenschutz / Sicherheit
- [ ] Datenschutzerklärung deckt Portal, Uploads, Push und E-Mail ab
- [ ] AV-Verträge mit Hosting/E-Mail-Anbietern vorhanden
- [ ] Löschfristen festgelegt
- [ ] Rollen/Rechte mit echten Testkonten geprüft
- [ ] Upload-Sicherheitsprüfung extern reviewed
- [ ] MFA-Secrets produktiv verschlüsselt / Identity-Provider entschieden
- [ ] Security-Review durchgeführt

## Pilotbetrieb
- [ ] 3–5 Testkunden eingeladen
- [ ] 2 Mitarbeiterkonten aktiv
- [ ] Eskalationsregel für „Notfall“ definiert
- [ ] Supportweg festgelegt
- [ ] tägliche Kontrolle der Fehlerlogs
