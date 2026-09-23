# iOS-Demo aufs iPhone bringen — ohne eigenen Mac

Diese Anleitung ist für die Situation: du hast nur ein iPhone, keinen Mac,
aber kurzzeitig Zugriff auf einen Windows- oder Linux-Rechner. Kostet
nichts außer etwas Zeit.

Warum zwei Schritte nötig sind: Der eigentliche iOS-Compiler läuft nur auf
macOS (kein Weg drumherum) — dafür übernimmt ein kostenloser
GitHub-Actions-Mac-Runner das Bauen. Die Installation/Signierung aufs
iPhone übernimmt anschließend AltStore/SideStore mit deiner eigenen,
kostenlosen Apple-ID — dafür ist einmalig ein Windows-/Linux-/Mac-Rechner
nötig.

## Schritt 1: Unsignierte App bauen lassen (GitHub Actions)

1. Im Repo auf GitHub zum Tab **Actions** gehen.
2. Den Workflow **"iOS Demo Build (unsigned)"** auswählen.
3. **Run workflow** klicken (auf dem Branch
   `claude/secure-messaging-app-architecture-tsy5a3`). Läuft automatisch
   auch bei jedem Push, der die App-Dateien ändert.
4. Nach ein paar Minuten ist der Lauf grün. Unter **Artifacts** liegt
   `SecureMessengerDemo-unsigned-ipa` (eine .zip, die die `.ipa` enthält).
5. Diese .zip herunterladen — geht auch direkt in Safari auf dem iPhone,
   während du in GitHub eingeloggt bist. Danach die `.ipa` aus der .zip
   entpacken (z. B. über die "Dateien"-App auf dem iPhone: aufs
   heruntergeladene .zip tippen → "Entpacken").

**Falls der Lauf rot ist:** Log von "Unsigniertes .app für echtes iPhone
bauen" bzw. das `xcodebuild-log`-Artefakt öffnen und mir die Fehlermeldung
schicken — dieser Workflow ist ohne echten Mac zum Testen entstanden und
kann beim ersten Versuch Anpassungsbedarf haben (z. B. falscher
Scheme-Name; der Log-Schritt "Verfügbare Schemes anzeigen" zeigt den
korrekten Namen).

## Schritt 2: AltStore/SideStore einmalig einrichten (am geliehenen PC)

1. Auf dem Windows-/Linux-Rechner **AltServer** installieren:
   https://altstore.io (offizielle, kostenlose Seite).
2. iPhone per USB-Kabel anschließen (oder im selben WLAN, dann klappt es
   später auch kabellos).
3. Auf dem Rechner in der AltServer-Menüleiste: **Install AltStore** →
   dein iPhone auswählen → mit deiner Apple-ID anmelden (App-spezifisches
   Passwort wird empfohlen, nicht das Hauptpasswort — erzeugst du unter
   https://appleid.apple.com → Anmelden & Sicherheit → App-spezifische
   Passwörter).
4. Auf dem iPhone: **Einstellungen → Allgemein → VPN & Geräteverwaltung**
   → dem gerade installierten Entwicklerprofil (deine Apple-ID) vertrauen.
5. Die **AltStore**-App ist jetzt auf dem iPhone installiert.

(Alternative: **SideStore** funktioniert nach demselben Prinzip, mit dem
Vorteil, dass die spätere Aktualisierung auch ohne dauerhaft laufenden
AltServer per WLAN/VPN funktionieren kann — für den Einstieg ist AltStore
aber der etablierteste, am besten dokumentierte Weg.)

## Schritt 3: Die selbstgebaute .ipa installieren

1. AltStore auf dem iPhone öffnen, Tab **My Apps** → **+** oben links.
2. Die in Schritt 1 heruntergeladene `SecureMessengerDemo-unsigned.ipa`
   auswählen.
3. AltStore signiert sie automatisch mit deiner Apple-ID und installiert
   sie — fertig, App-Icon liegt auf dem Homescreen.

## Wichtig zu wissen

- Kostenlose Apple-ID-Signierung läuft nach **7 Tagen ab**. AltStore
  erneuert automatisch, sofern das iPhone innerhalb dieser 7 Tage einmal
  im selben WLAN wie ein laufender AltServer ist (oder du öffnest AltStore
  und drückst manuell "Refresh All", solange AltServer erreichbar ist).
- Kostenlose Signierung erlaubt maximal **3 selbst signierte Apps
  gleichzeitig** und ist an eine begrenzte Zahl Geräte pro Jahr gebunden —
  für diesen einen Demo-Zweck aber kein Problem.
- Das ist exakt derselbe Mechanismus, den Xcodes kostenlose
  "Personal Team"-Signierung direkt am Mac nutzen würde — AltStore
  automatisiert nur den Teil, der sonst Xcode übernimmt.
