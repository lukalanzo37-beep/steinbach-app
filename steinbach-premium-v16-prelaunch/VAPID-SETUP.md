# Web-Push / VAPID einrichten

V15 enthält die Push-Logik, aber **keine privaten Schlüssel im Paket**.

## 1. Schlüssel erzeugen

Nach `pip install -r requirements.txt`:

```bash
python generate_vapid_keys.py
```

Dadurch entsteht `vapid_private.pem`. Das Script zeigt außerdem den öffentlichen Browser-Key an.

## 2. Umgebungsvariablen setzen

```text
STEINBACH_VAPID_PRIVATE_KEY=/sicherer/pfad/vapid_private.pem
STEINBACH_VAPID_PUBLIC_KEY=<ausgegebenen öffentlichen Key>
STEINBACH_VAPID_SUBJECT=mailto:info@immobilienservice-steinbach.de
```

Der private Schlüssel darf **nicht** ins Git-Repository oder öffentlich zugängliche Webverzeichnis.

## 3. HTTPS

Produktiver Push benötigt HTTPS. Auf `localhost` kann Push je nach Browser zum Testen funktionieren.

## 4. Gerät abonnieren

Im Portal unter Einstellungen → Benachrichtigungen die Push-Freigabe aktivieren.

## 5. Test

Adminbereich → Sicherheit & Zugänge → Push-Test senden.

## Hinweise

- Safari/iOS benötigt eine installierte PWA für Web Push.
- Browser-/OS-Einstellungen können Push blockieren.
- Abgelaufene Push-Subscriptions werden serverseitig deaktiviert, wenn der Push-Anbieter 404/410 zurückgibt.
