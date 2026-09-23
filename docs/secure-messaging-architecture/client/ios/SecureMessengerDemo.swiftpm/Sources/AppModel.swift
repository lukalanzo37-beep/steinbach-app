//
//  AppModel.swift
//
//  Verbindet Identität, Kontakt, Transport und Krypto zu dem in
//  ../../../PROTOCOL.md beschriebenen Ablauf.
//

import Foundation

struct ChatMessage: Identifiable {
    let id = UUID()
    let text: String
    let mine: Bool
}

struct LogEntry: Identifiable {
    let id = UUID()
    let text: String
    let kind: LogKind
}

@MainActor
final class AppModel: ObservableObject {
    @Published private(set) var me: Identity
    @Published var contact: ContactIdentity?
    @Published var contactInputText: String = ""
    @Published var sendText: String = ""
    @Published private(set) var messages: [ChatMessage] = []
    @Published private(set) var techLog: [LogEntry] = []

    @Published var connectionStatus: ConnectionStatus = .connecting
    @Published var connectionStatusText: String = "Verbinde…"

    let crypto = DemoCrypto()
    let transport = Transport()

    private let contactKey = "cipherwire_contact_v1"
    private let historyKey = "cipherwire_history_v1"

    init() {
        me = IdentityStore.loadOrCreate(crypto: crypto)
        loadContact()
        loadHistory()

        transport.onLog = { [weak self] text, kind in
            Task { @MainActor in self?.log(text, kind) }
        }
        transport.onEnvelope = { [weak self] envelope in
            Task { @MainActor in self?.handleIncoming(envelope) }
        }
        transport.$status.receive(on: DispatchQueue.main).assign(to: &$connectionStatus)
        transport.$statusText.receive(on: DispatchQueue.main).assign(to: &$connectionStatusText)

        transport.connect(ownBoxPubHex: me.boxPublicKey.hexString)
        log("Meine ID: " + me.idString, .info)
    }

    func log(_ text: String, _ kind: LogKind) {
        techLog.append(LogEntry(text: text, kind: kind))
    }

    func addContact() {
        guard let parsed = crypto.parseContactIdString(contactInputText) else {
            log("✗ Ungültiges ID-Format (erwartet: 64 Hex . 64 Hex)", .fail)
            return
        }
        contact = parsed
        messages = []
        contactInputText = ""
        UserDefaults.standard.set(
            parsed.boxPublicKey.hexString + "." + parsed.signPublicKey.hexString,
            forKey: contactKey
        )
        saveHistory()
    }

    func removeContact() {
        contact = nil
        messages = []
        UserDefaults.standard.removeObject(forKey: contactKey)
        UserDefaults.standard.removeObject(forKey: historyKey)
    }

    func send() {
        guard let contact else { return }
        let text = sendText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty else { return }
        sendText = ""
        messages.append(ChatMessage(text: text, mine: true))
        saveHistory()

        do {
            let envelope = try crypto.encryptForward(plaintext: text, recipientBoxPub: contact.boxPublicKey, me: me)
            log("→ gesendet, Ephemeral \(String(envelope.ephPub.prefix(12)))…", .info)
            transport.publish(topic: "cipherwire-demo-v1/" + contact.boxPublicKey.hexString, envelope: envelope)
        } catch {
            log("✗ " + error.localizedDescription, .fail)
        }
    }

    private func handleIncoming(_ envelope: Envelope) {
        guard let contact, envelope.senderBoxPub == contact.boxPublicKey.hexString else {
            log("✗ Nachricht von unbekannter/nicht hinzugefügter ID ignoriert", .warn)
            return
        }
        do {
            let text = try crypto.decryptForward(envelope, expectedSignPub: contact.signPublicKey, myBoxSecret: me.boxSecretKey)
            messages.append(ChatMessage(text: text, mine: false))
            saveHistory()
            log("✓ empfangen, Signatur + Verschlüsselung verifiziert", .ok)
        } catch {
            log("✗ Empfangene Nachricht verworfen: " + error.localizedDescription, .fail)
        }
    }

    // MARK: - Gegenproben

    func runTamperTest() {
        let targetPub = contact?.boxPublicKey ?? me.boxPublicKey
        guard let envelope = try? crypto.encryptForward(plaintext: "Testnachricht für Manipulationsprobe", recipientBoxPub: targetPub, me: me),
              var cipherBytes = Data(hexString: envelope.ciphertext) else { return }
        cipherBytes[0] ^= 0xFF
        let tampered = Envelope(
            senderBoxPub: envelope.senderBoxPub, senderSignPub: envelope.senderSignPub,
            ephPub: envelope.ephPub, ephSig: envelope.ephSig,
            nonce: envelope.nonce, ciphertext: cipherBytes.hexString
        )
        log("Gegenprobe: 1 Bit im Ciphertext verändert …", .info)
        do {
            _ = try crypto.decryptForward(tampered, expectedSignPub: me.signPublicKey, myBoxSecret: me.boxSecretKey)
            log("✗ Fehler: Manipulation hätte erkannt werden müssen!", .fail)
        } catch {
            log("✓ korrekt abgelehnt: " + error.localizedDescription, .ok)
        }
    }

    func runForgedSignatureTest() {
        guard let attacker = try? crypto.generateIdentity(),
              let forged = try? crypto.encryptForward(plaintext: "gefälscht", recipientBoxPub: me.boxPublicKey, me: attacker)
        else { return }
        // Envelope gibt vor "ich" zu sein, ist aber mit dem
        // Signaturschlüssel eines Angreifers signiert.
        let spoofed = Envelope(
            senderBoxPub: me.boxPublicKey.hexString, senderSignPub: me.signPublicKey.hexString,
            ephPub: forged.ephPub, ephSig: forged.ephSig,
            nonce: forged.nonce, ciphertext: forged.ciphertext
        )
        log("Gegenprobe: gefälschte Ephemeral-Signatur (falscher Signaturschlüssel) …", .info)
        do {
            _ = try crypto.decryptForward(spoofed, expectedSignPub: me.signPublicKey, myBoxSecret: me.boxSecretKey)
            log("✗ Fehler: gefälschte Signatur hätte erkannt werden müssen!", .fail)
        } catch {
            log("✓ korrekt abgelehnt: " + error.localizedDescription, .ok)
        }
    }

    func clearLog() { techLog.removeAll() }

    // MARK: - Persistenz (Klartext-UserDefaults, siehe IdentityStore.swift)

    private func loadContact() {
        guard let s = UserDefaults.standard.string(forKey: contactKey),
              let parsed = crypto.parseContactIdString(s) else { return }
        contact = parsed
    }

    private func loadHistory() {
        guard let data = UserDefaults.standard.data(forKey: historyKey),
              let decoded = try? JSONDecoder().decode([StoredMessage].self, from: data) else { return }
        messages = decoded.map { ChatMessage(text: $0.text, mine: $0.mine) }
    }

    private func saveHistory() {
        let stored = messages.map { StoredMessage(text: $0.text, mine: $0.mine) }
        guard let data = try? JSONEncoder().encode(stored) else { return }
        UserDefaults.standard.set(data, forKey: historyKey)
    }
}

private struct StoredMessage: Codable {
    let text: String
    let mine: Bool
}
