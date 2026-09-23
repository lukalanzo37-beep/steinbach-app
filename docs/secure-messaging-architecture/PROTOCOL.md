# Secure-Messenger-Secret-Demo-Protokoll v2

Gemeinsames Wire-Format für alle drei Demo-Clients (Web, iOS, Android), damit
sie tatsächlich untereinander kompatibel sind — eine Nachricht von der
iOS-Demo kann so grundsätzlich von der Web-Demo empfangen werden und
umgekehrt. Einzige Quelle der Wahrheit; bei Änderungen an einer
Implementierung immer zuerst hier aktualisieren, dann alle drei Clients
nachziehen.

**Status v2 (aktuell nur im Web-Client umgesetzt):** Die äußere
Envelope-Struktur ist identisch zu v1. Neu ist die Struktur des
*verschlüsselten Inhalts* (Zustellbestätigungen, Tippt-Anzeige,
Nachrichten-IDs). Die iOS- und Android-Referenz-Apps
(`client/ios/SecureMessengerDemo.swiftpm/`, `client/android/SecureMessengerDemo/`)
implementieren aktuell noch v1 (reiner Text als Plaintext, kein
Zustellstatus/Tippt-Anzeige) und sind ein offener Nachzieh-Punkt — siehe
README.md.

Status insgesamt: Demo-/Entwicklungsprotokoll, kein finales
Produktprotokoll. Siehe README.md Abschnitt 5 für offene Punkte (u. a.
volle Double-Ratchet-Sicherheit, echter Relay-Server statt Test-Broker).

## Identität

Jeder Client besitzt zwei Langzeit-Schlüsselpaare:
- **Box-Schlüsselpaar** (Curve25519, für `crypto_box`)
- **Signatur-Schlüsselpaar** (Ed25519, für die Ephemeral-Key-Signatur)

Die öffentliche Identität, die man einem Kontakt gibt, ist die
String-Verkettung beider Public Keys als Hex, durch einen Punkt getrennt:

```
<boxPublicKeyHex(64 Zeichen)>.<signPublicKeyHex(64 Zeichen)>
```

Beispiel: `4a1f...b02c.9e77...11d4` (je 32 Byte / 64 Hex-Zeichen).

## Transport

Öffentlicher MQTT-Test-Broker `test.mosquitto.org` als Platzhalter für den
echten Relay-Server (`backend/src/main.rs`):

- Web (Browser, kein Raw-TCP möglich): WebSocket, `wss://test.mosquitto.org:8081/mqtt`
- Native (iOS/Android): MQTT über TLS, `test.mosquitto.org:8883`

Beide Wege landen auf demselben Broker/Topic-Namespace, sind also
untereinander kompatibel.

**Topic je Empfänger:**
```
cipherwire-demo-v1/<eigenerBoxPublicKeyHex>
```
(Interner Topic-Namespace, bewusst nicht an den sichtbaren Produktnamen
gekoppelt — eine Umbenennung der App erfordert keine Protokolländerung.)
Jeder Client abonniert nur sein eigenes Topic (= sein eigener Box-Public-Key)
und veröffentlicht an das Topic des Empfängers.

**Wichtig:** Dieser Broker ist öffentlich und unauthentifiziert. Inhalte
bleiben durch E2EE geschützt, aber Topic-Namen (= Public Keys) und
Sende-Zeitpunkte sind für jeden, der denselben Broker nutzt, sichtbar. Nicht
für echte Nutzdaten verwenden, nur zum Testen des Protokolls.

## Envelope (äußeres Nachrichtenformat, unverändert seit v1)

Ein JSON-Objekt, als UTF-8-Text auf dem Empfänger-Topic veröffentlicht:

```json
{
  "senderBoxPub":  "<hex, 64 Zeichen>",
  "senderSignPub": "<hex, 64 Zeichen>",
  "ephPub":        "<hex, 64 Zeichen>",
  "ephSig":        "<hex, 128 Zeichen>",
  "nonce":         "<hex, 48 Zeichen>",
  "ciphertext":    "<hex>"
}
```

## Verschlüsselter Inhalt (neu in v2)

Statt rohem UTF-8-Text ist der entschlüsselte Plaintext (`crypto_box_open`
Ergebnis, UTF-8) ein JSON-Objekt mit einem `type`-Feld:

**Chat-Nachricht:**
```json
{ "type": "msg", "id": "<16 zufällige Hex-Zeichen>", "text": "Hallo!" }
```

**Zustellbestätigung** (Antwort auf eine empfangene `msg`):
```json
{ "type": "receipt", "refId": "<id der msg>", "kind": "delivered" }
```
oder `"kind": "read"`, wenn die zugehörige Unterhaltung beim Empfänger
gerade aktiv geöffnet ist.

**Tippt-gerade-Anzeige:**
```json
{ "type": "typing" }
```
Wird beim Tippen höchstens alle 3 Sekunden gesendet; der Empfänger blendet
die Anzeige nach 4 Sekunden ohne neues Signal automatisch wieder aus.

Alle drei Typen laufen durch **dieselbe** signierte
Ephemeral-`crypto_box`-Verschlüsselung wie in v1 — auch Zustellstatus und
Tippt-Events sind Ende-zu-Ende-verschlüsselt und für den Relay-Server nicht
einsehbar.

## Senden (Verschlüsseln)

Für Forward Secrecy wird **nicht** direkt mit dem Langzeit-Box-Key
verschlüsselt, sondern mit einem frischen, signierten Ephemeral-Key pro
Nachricht (siehe README.md Fallstrick Nr. 1):

1. Frisches Curve25519-Ephemeral-Schlüsselpaar `(ephPub, ephSec)` erzeugen.
2. `ephSig = Ed25519-Sign(ephPub, eigenerSignSecretKey)` — bindet den
   Ephemeral-Key kryptografisch an die eigene Langzeit-Identität.
3. `nonce` = 24 zufällige Bytes.
4. Plaintext gemäß obigem JSON-Format zusammenbauen.
5. `ciphertext = crypto_box(plaintext, nonce, empfängerBoxPub, ephSec)`.
6. Envelope mit `senderBoxPub`/`senderSignPub` (eigene Langzeit-Public-Keys,
   zur Wiedererkennung/Kontaktzuordnung beim Empfänger) zusammenbauen und auf
   `cipherwire-demo-v1/<empfängerBoxPub>` veröffentlichen.
7. `ephSec` sofort verwerfen (nicht weiter referenzieren/speichern).

## Empfangen (Entschlüsseln)

1. Envelope vom eigenen Topic lesen, JSON parsen.
2. Prüfen, ob `senderBoxPub` zu einem bekannten, hinzugefügten Kontakt
   gehört — sonst verwerfen (verhindert Nachrichten von unbekannten IDs).
3. `Ed25519-Verify(ephPub, ephSig, senderSignPub-des-Kontakts)` — schlägt das
   fehl: Envelope verwerfen, generischer Fehler, keine Detailinformation.
4. `plaintext = crypto_box_open(ciphertext, nonce, ephPub, eigenerBoxSecretKey)`
   — schlägt das fehl: ebenfalls verwerfen.
5. Plaintext als JSON parsen, anhand `type` verzweigen (`msg` → anzeigen +
   `delivered`-Receipt zurücksenden, ggf. `read`-Receipt wenn Chat offen ist;
   `receipt` → Status der referenzierten eigenen Nachricht aktualisieren;
   `typing` → Anzeige für ~4s einblenden).

## Referenzimplementierungen

- Web: `client/web/index.html` (TweetNaCl.js + mqtt.js) — **v2**
- iOS: `client/ios/SecureMessengerDemo.swiftpm/` (Swift-Sodium + CocoaMQTT) — v1, Nachzieh-Punkt
- Android: `client/android/SecureMessengerDemo/` (LazySodium + Eclipse Paho) — v1, Nachzieh-Punkt
