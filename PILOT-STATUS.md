# V16 Pre-Launch Status

## Status

Backend-Kernprozesse und Rollenrechte wurden automatisiert gegen einen laufenden Server getestet. Besonders Kunden-/Objekt-/Ticket-Isolation und Mitarbeiter-Zugriffsrechte wurden nachgeschärft.

## Vor echtem Livebetrieb offen

- produktives HTTPS-Hosting
- echte SMTP-Konfiguration
- echte VAPID/Web-Push-Konfiguration
- reale Admin-/Mitarbeiter-/Kundenkonten statt Demo-Seeding
- MFA für produktive Admins aktivieren
- Datenschutz/AV-Verträge/Impressum final juristisch prüfen
- Wiederherstellung eines Backups praktisch testen
- Endgerätetests auf iPhone und Android

## Referenzen

Siehe `PRELAUNCH-QA-REPORT.md`, `PRODUCTION-GO-LIVE.md` und `.env.example`.
