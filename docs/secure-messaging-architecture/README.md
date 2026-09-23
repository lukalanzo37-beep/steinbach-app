# Technisches Konzept: Hochsichere Messaging-App (Threema-Vorbild)

Dieses Dokument beschreibt die kryptografische und architektonische Basis für
eine Ende-zu-Ende-verschlüsselte (E2EE) Messaging-App mit dem Ziel **maximaler
Metadaten-Minimierung** und einer **Zero-Knowledge-Server-Architektur**. Es
ist als Architektur-Grundlage gedacht, nicht als fertiges, auditiertes
Produkt — vor einem echten Einsatz gehört ein professionelles
Kryptografie-Audit dazu (siehe Fallstricke am Ende).

Referenz-Code liegt in diesem Verzeichnis:

```
docs/secure-messaging-architecture/
├── client/ios/E2EECryptoManager.swift        # iOS Client-Krypto (libsodium/Swift-Sodium)
├── client/android/E2EECryptoManager.kt       # Android Client-Krypto (libsodium/LazySodium)
├── client/android/SecureKeyStorage.kt        # Android Keystore Key-Wrapping
├── backend/src/main.rs                       # "Blinder" Relay-Server (Rust/axum, Skizze)
├── backend/Cargo.toml                        # Abhängigkeiten für den Server-Sketch
├── client/ios/SecureMessengerDemo.swiftpm/   # Lauffähige iOS-Demo-App (SwiftUI + Swift-Sodium)
├── client/android/SecureMessengerDemo/       # Lauffähige Android-Demo-App (Compose + LazySodium)
├── db/schema.sql                             # Lokales SQLite/Room-Schema
└── db/android/SecureMessengerDatabase.kt     # Room + SQLCipher Integration
```

## Demo-Apps lokal öffnen

Die beiden `SecureMessengerDemo`-Ordner sind echte, öffenbare Projekte, die
dieselbe NaCl-`crypto_box`-Verschlüsselung wie oben beschrieben ausführen
(Alice verschlüsselt, Bob entschlüsselt, plus zwei Gegenproben: manipulierte
Nachricht und falscher Absender werden korrekt abgelehnt). Aus
Zuverlässigkeitsgründen halten die Demo-Apps Schlüssel bewusst nur im
Arbeitsspeicher statt in Keychain/Keystore — die produktionsnahe Variante
mit Keychain/Keystore bleibt in den oben gelisteten Referenzdateien.

**iOS** (braucht einen Mac mit Xcode 15+):
1. In Xcode: *File → Open…* und den Ordner
   `client/ios/SecureMessengerDemo.swiftpm` auswählen.
2. Warten, bis Xcode die Paketabhängigkeit `swift-sodium` aufgelöst hat.
3. Einen iOS-Simulator auswählen und mit ⌘R starten.
4. In der App auf "Demo starten" tippen.

**Android** (braucht Android Studio):
1. In Android Studio: *File → Open…* und den Ordner
   `client/android/SecureMessengerDemo` auswählen.
2. Den Gradle-Sync abwarten (lädt u. a. LazySodium/JNA herunter). Falls
   Android Studio wegen des fehlenden `gradle-wrapper.jar` nachfragt, die
   Wrapper-Vervollständigung/das gebündelte Gradle akzeptieren.
3. Einen Emulator oder ein Gerät auswählen und ▶ Run drücken.
4. In der App auf "Demo starten" tippen.

Falls beim ersten Build in Xcode oder Android Studio ein Fehler auftritt:
Fehlermeldung kopieren und zurückmelden — die Projekte wurden ohne Zugriff
auf Xcode/Android SDK erstellt und konnten daher nicht selbst kompiliert
werden.

**Kein Mac vorhanden?** Für die iOS-Demo gibt es einen Weg komplett ohne
eigenen Mac (GitHub-Actions-Cloud-Build + AltStore/SideStore-Sideloading):
siehe `client/ios/SIDELOAD-OHNE-MAC.md`.

---

## 1. Kryptografisches Grundprinzip

Wie bei Threema wird **NaCl `crypto_box`** verwendet (X25519 für den
Schlüsselaustausch, XSalsa20 für die Verschlüsselung, Poly1305 als MAC). Das
ist **Authenticated Encryption**: Eine Nachricht, die erfolgreich entschlüsselt
wird, kann *nur* vom Inhaber des behaupteten Absender-Private-Keys stammen —
eine separate digitale Signatur ist für die 1:1-Verschlüsselung nicht nötig.

Jedes Gerät besitzt ein langlebiges **Identitäts-Schlüsselpaar**
(Curve25519, 32-Byte Public Key = die "Adresse" des Nutzers). Der Private Key
verlässt das Gerät **niemals** — weder Server noch Backup sehen ihn im
Klartext.

Wichtige Design-Entscheidung, die im Fallstricke-Abschnitt vertieft wird:
Reines `crypto_box` zwischen zwei *langlebigen* Schlüsseln bietet **keine
Forward Secrecy**. Für ein produktionsreifes System sollte zusätzlich ein
Ratchet-Mechanismus (siehe unten) ergänzt werden.

---

## 2. Client-seitige Kryptografie

Siehe `client/ios/E2EECryptoManager.swift` und `client/android/E2EECryptoManager.kt`.

Ablauf pro Gerät:

1. **Schlüsselerzeugung** bei Erst-Start der App: `crypto_box_keypair()`
   erzeugt ein Curve25519-Paar direkt auf dem Gerät. Der Public Key wird an
   den Server übertragen (als Identität), der Private Key verlässt das Gerät nie.
2. **Speicherung des Private Keys**:
   - iOS: **Keychain**, geschützt durch `SecAccessControl` mit
     `.biometryCurrentSet` und `kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly`
     — dadurch ist der Key geräte-gebunden, verlangt Face ID/Touch ID/Code und
     landet **nie** im iCloud-Keychain-Backup.
   - Android: Der **Android Keystore** kann Curve25519-Rohschlüssel nicht
     nativ halten (er unterstützt nur RSA/EC-P256/AES). Deshalb wird ein
     **Key-Wrapping**-Verfahren genutzt: Ein Hardware-/StrongBox-gebundener
     AES-256-GCM-Schlüssel im Keystore verschlüsselt ("wrapped") den rohen
     Curve25519-Private-Key, bevor dieser persistiert wird (siehe
     `SecureKeyStorage.kt`). Zusätzlich `android:allowBackup="false"` bzw.
     restriktive `dataExtractionRules`, damit der verschlüsselte Blob nicht in
     Auto-Backups landet.
3. **Verschlüsselung** einer Nachricht: `crypto_box_easy(message, nonce,
   empfänger_public_key, eigener_private_key)`. Der Nonce ist 24 zufällige
   Bytes (CSPRNG), pro Nachricht neu generiert — bei diesem 192-Bit-Nonce-Raum
   ist zufällige Kollision praktisch ausgeschlossen (anders als z. B. bei
   96-Bit-Nonces von AES-GCM).
4. **Entschlüsselung**: `crypto_box_open_easy(ciphertext, nonce,
   sender_public_key, eigener_private_key)`. Schlägt die
   Authentifizierung fehl, wird **grundsätzlich nur ein generischer Fehler**
   zurückgegeben (kein Hinweis, *warum* — Schutz vor Oracle-Angriffen).

---

## 3. Metadaten-Minimierung / "Blinder Server"

Ziel: Der Server soll strukturell **nicht wissen können**, wer mit wem, wann
und wie oft kommuniziert — nicht nur nicht *wollen*.

### 3.1 Anonyme Authentifizierung ohne Telefonnummer/E-Mail

Statt Benutzername/Passwort: **Public-Key-Challenge-Response**.

1. Client generiert lokal ein Ed25519-Signaturschlüsselpaar (zusätzlich zum
   Curve25519-Verschlüsselungspaar, oder abgeleitet via `crypto_sign_ed25519_pk_to_curve25519`).
2. Client sendet nur den **Public Key** an den Server → Server vergibt eine
   zufällige, für sich bedeutungslose ID (z. B. 8 Byte Zufall oder ein
   Base64-Fingerprint des Public Keys). Keine PII wird je übertragen.
3. Bei jedem Login: Server schickt eine zufällige Nonce ("Challenge"), Client
   signiert sie mit seinem Private Key, Server verifiziert mit dem
   gespeicherten Public Key. Der Server hält **kein Passwort und kein
   Geheimnis** — ein Datenbank-Leak des Servers gibt einem Angreifer keine
   Zugangsdaten, mit denen er sich als Nutzer ausgeben könnte.
4. Kontaktaufnahme läuft ausschließlich über den Austausch dieser IDs
   (z. B. QR-Code-Scan persönlich, wie bei Threema) — **kein** automatischer
   Adressbuch-Abgleich mit Klartext-Telefonnummern. Wird Kontakt-Discovery
   gewünscht, nur optional und mit gehashter/verkürzter Telefonnummer nach dem
   Vorbild von Signals privatem Contact-Discovery-Verfahren, niemals im
   Klartext.

### 3.2 "Sofortiges" Löschen aus dem Arbeitsspeicher

Siehe `backend/src/main.rs` für eine Skizze in Rust. Kernideen:

- **Kein Nachrichten-Content im Langzeitspeicher.** Nachrichten liegen nur
  in einer In-Memory-Struktur (`DashMap`), solange sie unzustellt sind. Nach
  erfolgreicher Zustellung (Client bestätigt Empfang) wird der Eintrag
  **sofort entfernt und aktiv überschrieben**, nicht nur dereferenziert.
- **Aktives Überschreiben statt "hoffen, dass der GC/Allocator es tut".**
  In Rust: der `zeroize`-Crate (`Zeroizing<Vec<u8>>`) sorgt mit `volatile`-
  Schreiboperationen dafür, dass der Compiler das Nullen nicht als "totes
  Statement" wegoptimiert — ein Problem, das ein simples `vec.clear()` oder
  manuelles `for b in vec { *b = 0 }` in Release-Builds nicht zuverlässig löst.
- **Kein Swapping sensibler Puffer auf Platte**: `mlock`/`mlockall` auf den
  Prozess anwenden, damit Nachrichteninhalte nicht in die Swap-Partition
  ausgelagert werden, wo sie das Prozessende überdauern könnten.
- **Keine Core-Dumps**: `RLIMIT_CORE=0` setzen bzw. unter Linux
  `prctl(PR_SET_DUMPABLE, 0)`, damit ein Absturz keinen Speicherauszug mit
  Klartext-Metadaten oder Schlüsselmaterial auf Platte schreibt.
- **Kein Access-Log mit IP-Adressen.** Der Reverse-Proxy (z. B. nginx) läuft
  mit `access_log off;` oder einem eigenen Log-Format ohne `$remote_addr`.
  Auf Applikationsebene wird ein eigener `tower`/`axum`-Middleware-Layer
  verwendet, der **explizit keine** IP oder Zeitstempel in irgendeine
  Log-Zeile, Metrik oder Datenbank schreibt.
- **Offline-Zustellung ohne Dauerspeicherung im Klartext**: Ist der
  Empfänger nicht verbunden, wird die (bereits Ende-zu-Ende-verschlüsselte)
  Nachricht nur so lange gepuffert, wie zwingend nötig (kurze TTL, z. B.
  wenige Tage), danach hart gelöscht. Für die "Wach auf und hol ab"-Anstoßung
  kommen stille Push-Benachrichtigungen (APNs/FCM) **ohne Nachrichteninhalt
  und ohne Metadaten** zum Einsatz — der Push-Provider erfährt nur "für
  Gerät X liegt etwas vor", nie von wem.

**Wichtige Einschränkung, ehrlich benannt:** "Unwiderrufliches Löschen aus
RAM" lässt sich in einem allgemeinen Betriebssystem **nicht absolut
garantieren** — Swap, Hypervisor-Snapshots, Ruhezustand/Hibernation-Dateien
und Cold-Boot-Angriffe sind Restrisiken. Die oben genannten Maßnahmen sind
**Defense-in-Depth**, keine mathematische Garantie. Das eigentliche
Sicherheitsversprechen kommt aus der E2EE selbst (der Server sieht nie
Klartext) — die RAM-Löschung reduziert zusätzlich das Zeitfenster für
Metadaten wie Zustell-Zeitpunkte und Routing-Informationen.

---

## 4. Lokales Datenbank-Design

Siehe `db/schema.sql` und `db/android/SecureMessengerDatabase.kt`.

Die App speichert entschlüsselte Nachrichten lokal (für Suche, Anzeige,
Offline-Zugriff) in **Room/SQLite**, aber die **gesamte Datenbankdatei** wird
mit **SQLCipher** (AES-256, transparent auf SQLite-Seitenebene) verschlüsselt.
Der SQLCipher-Passphrase wird **nicht** hartcodiert und **nicht** im Klartext
auf der Platte abgelegt, sondern per **Envelope Encryption** aus einem
Keystore-/Keychain-gebundenen Schlüssel abgeleitet — demselben Muster wie
beim Identitäts-Private-Key (Abschnitt 2).

Kern-Tabellen: `contacts` (anonyme ID + Public Key + Verifikationsstufe),
`conversations`, `messages` (inkl. `delivery_state` für
gesendet/zugestellt/gelesen). Die Server-seitige Nachrichten-ID wird
**nicht** als Primärschlüssel übernommen, sondern lokal eine neue UUID
vergeben — so lässt sich aus der lokalen DB keine Server-Zuordnung
rekonstruieren, falls das Gerät kompromittiert wird.

---

## 5. Wichtigste Fallstricke bei der Umsetzung

1. **Keine Forward Secrecy bei reinem `crypto_box`.** Zwei langlebige
   Schlüssel zu verwenden bedeutet: Wird der Private Key später kompromittiert,
   lässt sich *aller* vergangener Traffic entschlüsseln (sofern mitgeschnitten).
   Abhilfe: pro Sitzung/Nachricht zusätzliche **ephemere X25519-Schlüssel**
   einführen (X3DH-artiger Handshake, wie bei Signal, oder Threemas eigenes
   Forward-Secrecy-Update ab 2023). Ohne das ist es "nur" E2EE, kein
   State-of-the-Art-Messenger.
2. **Schlüssel-Verifikation / MITM.** Ein bösartiger oder kompromittierter
   Server könnte bei der Kontaktaufnahme einen falschen Public Key
   unterschieben. Zwingend nötig: Out-of-Band-Verifikation (QR-Code-Scan
   persönlich, "Sicherheitsnummer"/Fingerprint-Vergleich wie bei Signal/Threema).
3. **Nonce-Disziplin.** Nonce **niemals** wiederverwenden mit demselben
   Schlüsselpaar. Bei NaCl (192-Bit-Zufalls-Nonce) unkritisch bei echtem
   CSPRNG; bei einem Wechsel auf AES-GCM (96 Bit) wird ein Zähler statt
   Zufall nötig, sonst drohen katastrophale Nonce-Kollisionen.
4. **Replay-Angriffe.** Ein Angreifer könnte eine abgefangene, gültige
   verschlüsselte Nachricht erneut einspielen. Gegenmaßnahme: monotone
   Zähler/Zeitstempel **innerhalb** des verschlüsselten Payloads plus
   client- oder serverseitige Duplikat-Erkennung über bereits gesehene Nonces.
5. **Fehlerbehandlung bei Entschlüsselung darf nichts preisgeben.** Nur
   generische Fehler ("Entschlüsselung fehlgeschlagen"), niemals
   unterscheidbare Fehlermeldungen für "falscher MAC" vs. "falsches Padding"
   vs. "falscher Schlüssel" — sonst drohen Padding-/Timing-Oracle-Angriffe.
   Immer `hmac.compare_digest`/`sodium_memcmp`-artige **konstant-Zeit-Vergleiche**.
6. **Sichere Zufallszahlen.** Ausschließlich CSPRNG verwenden:
   `SecRandomCopyBytes` (iOS), `SecureRandom` (Android/Java) —
   **niemals** `java.util.Random` oder `arc4random()` ohne Krypto-Eignungsprüfung.
7. **Secrets in verwalteten Sprachen sind schwer sicher zu löschen.**
   Swift-`String`/Kotlin-`String` sind immutable — sie lassen sich nicht
   gezielt überschreiben, Kopien können durch ARC/GC beliebig lange im
   Speicher verbleiben. Geheimnisse wo möglich als `ByteArray`/`[UInt8]`
   halten und nach Gebrauch explizit nullen.
8. **Backup-Fallen.** Ein Private Key, der versehentlich in ein
   iCloud-Backup oder Android-Auto-Backup wandert, hebelt die gesamte
   Geräte-Bindung aus. Immer explizit ausschließen (`ThisDeviceOnly`-Attribute,
   `allowBackup="false"`).
9. **Metadaten über Traffic-Analyse trotz E2EE.** Auch ohne Content-Zugriff
   verraten Nachrichtengröße, -häufigkeit und -zeitpunkt viel (wer redet mit
   wem, wann). Für höhere Ansprüche: Nachrichten auf feste Größenklassen
   padden, ggf. Dummy-Traffic/verzögerte Zustellung einführen.
10. **Anonyme Registrierung lädt zu Missbrauch/Spam ein.** Ohne jede
    Identitätsprüfung sind Sybil-Angriffe und Massenregistrierung leicht.
    Abhilfe ohne PII-Preisgabe: leichtes Proof-of-Work bei Registrierung,
    Rate-Limiting am Edge (ohne IP-Persistierung), oder ein
    Invite-Token-Modell.
11. **Gruppenchats sind ein eigenes Protokoll-Problem.** Naives paarweises
    `crypto_box` skaliert nicht sauber auf Gruppen (n×m Verschlüsselungen,
    keine Konsistenzgarantien). Erfordert ein dediziertes Gruppenprotokoll
    (z. B. Sender-Keys-Modell), das hier bewusst nicht mitbehandelt wird.
12. **Dieses Konzept ersetzt kein Audit.** Vor Produktivbetrieb: unabhängiges
    Kryptografie- und Penetrationstest-Audit, insbesondere für den
    Ratchet-/Forward-Secrecy-Teil und die Server-Härtung.
