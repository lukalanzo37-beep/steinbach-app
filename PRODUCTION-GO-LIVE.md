# Produktions-Go-Live V16

1. `.env.example` nach `.env` kopieren und echte Werte setzen.
2. `STEINBACH_DEMO_SEED=0`, `STEINBACH_DEV_SHOW_TOKENS=0`, `STEINBACH_COOKIE_SECURE=1` prüfen.
3. Portal unter HTTPS hinter Reverse Proxy betreiben.
4. VAPID-Schlüssel erzeugen und eintragen.
5. SMTP-Zugangsdaten eintragen und Testmail versenden.
6. Admin-Konto mit echtem Passwort erstellen und MFA aktivieren.
7. Demo-Konten und Testdatenbank nicht in die Produktion übernehmen.
8. Backup-Script automatisiert mindestens täglich ausführen und Wiederherstellung testen.
9. `/api/health` und `/api/readiness` überwachen.
10. Erst mit wenigen echten Pilotnutzern starten und Ereignis-/Audit-Logs prüfen.
