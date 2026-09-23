//
//  DemoCrypto.swift
//
//  Implementiert exakt das in ../../../PROTOCOL.md beschriebene Wire-Format:
//  Langzeit-Box-Identität + Langzeit-Signatur-Identität, pro Nachricht ein
//  frisches, signiertes Ephemeral-Schlüsselpaar für Forward Secrecy. Muss
//  mit DemoCrypto.kt (Android) und dem Krypto-Teil von client/web/index.html
//  kompatibel bleiben.
//
//  Schlüsselspeicherung: zu Testzwecken in UserDefaults (Klartext,
//  entspricht dem localStorage-Ansatz der Web-Demo) -- NICHT die
//  gehärtete Variante. Für die produktionsnahe Keychain-Absicherung siehe
//  ../E2EECryptoManager.swift.
//

import Foundation
import Sodium

enum DemoCryptoError: Error, LocalizedError {
    case keyGenerationFailed
    case encryptionFailed
    case signatureInvalid
    case decryptionFailed
    case malformedEnvelope

    var errorDescription: String? {
        switch self {
        case .keyGenerationFailed: return "Schlüsselerzeugung fehlgeschlagen"
        case .encryptionFailed: return "Verschlüsselung fehlgeschlagen"
        case .signatureInvalid: return "Ephemeral-Signatur ungültig"
        case .decryptionFailed: return "Entschlüsselung fehlgeschlagen"
        case .malformedEnvelope: return "Ungültiges Envelope-Format"
        }
    }
}

struct Identity {
    let boxPublicKey: Data
    let boxSecretKey: Data
    let signPublicKey: Data
    let signSecretKey: Data

    /// PROTOCOL.md: "<boxPubHex>.<signPubHex>"
    var idString: String { boxPublicKey.hexString + "." + signPublicKey.hexString }
}

struct ContactIdentity {
    let boxPublicKey: Data
    let signPublicKey: Data
}

/// PROTOCOL.md Envelope-Feldnamen 1:1 übernommen (JSON-Keys sind bewusst
/// nicht "swifty", damit sie mit der Web-/Android-Implementierung matchen).
struct Envelope: Codable {
    let senderBoxPub: String
    let senderSignPub: String
    let ephPub: String
    let ephSig: String
    let nonce: String
    let ciphertext: String
}

extension Data {
    var hexString: String { map { String(format: "%02x", $0) }.joined() }
    init?(hexString: String) {
        guard hexString.count % 2 == 0 else { return nil }
        var bytes = [UInt8]()
        bytes.reserveCapacity(hexString.count / 2)
        var idx = hexString.startIndex
        while idx < hexString.endIndex {
            let next = hexString.index(idx, offsetBy: 2)
            guard let b = UInt8(hexString[idx..<next], radix: 16) else { return nil }
            bytes.append(b)
            idx = next
        }
        self = Data(bytes)
    }
}

final class DemoCrypto {

    private let sodium = Sodium()

    func generateIdentity() throws -> Identity {
        guard let box = sodium.box.keyPair(), let sign = sodium.sign.keyPair() else {
            throw DemoCryptoError.keyGenerationFailed
        }
        return Identity(
            boxPublicKey: Data(box.publicKey), boxSecretKey: Data(box.secretKey),
            signPublicKey: Data(sign.publicKey), signSecretKey: Data(sign.secretKey)
        )
    }

    func parseContactIdString(_ s: String) -> ContactIdentity? {
        let parts = s.trimmingCharacters(in: .whitespacesAndNewlines).split(separator: ".")
        guard parts.count == 2,
              let boxPub = Data(hexString: String(parts[0])), boxPub.count == 32,
              let signPub = Data(hexString: String(parts[1])), signPub.count == 32
        else { return nil }
        return ContactIdentity(boxPublicKey: boxPub, signPublicKey: signPub)
    }

    /// PROTOCOL.md "Senden (Verschlüsseln)": signiertes Ephemeral crypto_box
    /// statt direkter Verschlüsselung mit dem Langzeit-Box-Key.
    func encryptForward(plaintext: String, recipientBoxPub: Data, me: Identity) throws -> Envelope {
        guard let eph = sodium.box.keyPair() else { throw DemoCryptoError.keyGenerationFailed }
        guard let ephSig = sodium.sign.signature(message: Bytes(eph.publicKey), secretKey: Bytes(me.signSecretKey)) else {
            throw DemoCryptoError.encryptionFailed
        }
        let nonce = sodium.box.nonce()
        guard let messageBytes = plaintext.data(using: .utf8) else { throw DemoCryptoError.encryptionFailed }
        guard let ciphertext = sodium.box.seal(
            message: Bytes(messageBytes),
            recipientPublicKey: Bytes(recipientBoxPub),
            senderSecretKey: eph.secretKey,
            nonce: nonce
        ) else { throw DemoCryptoError.encryptionFailed }

        // eph.secretKey wird ab hier nicht mehr referenziert -- einzige
        // Kopie verschwindet mit dem Ende dieses Funktionsaufrufs
        // (best effort ohne manuelles Memory-Zeroing, siehe README
        // Fallstrick Nr. 7).
        return Envelope(
            senderBoxPub: me.boxPublicKey.hexString,
            senderSignPub: me.signPublicKey.hexString,
            ephPub: Data(eph.publicKey).hexString,
            ephSig: Data(ephSig).hexString,
            nonce: Data(nonce).hexString,
            ciphertext: Data(ciphertext).hexString
        )
    }

    /// PROTOCOL.md "Empfangen (Entschlüsseln)".
    func decryptForward(_ envelope: Envelope, expectedSignPub: Data, myBoxSecret: Data) throws -> String {
        guard let ephPub = Data(hexString: envelope.ephPub),
              let ephSig = Data(hexString: envelope.ephSig),
              let nonce = Data(hexString: envelope.nonce),
              let ciphertext = Data(hexString: envelope.ciphertext)
        else { throw DemoCryptoError.malformedEnvelope }

        guard sodium.sign.verify(message: Bytes(ephPub), publicKey: Bytes(expectedSignPub), signature: Bytes(ephSig)) else {
            throw DemoCryptoError.signatureInvalid
        }

        guard let opened = sodium.box.open(
            authenticatedCipherText: Bytes(ciphertext),
            senderPublicKey: Bytes(ephPub),
            recipientSecretKey: Bytes(myBoxSecret),
            nonce: Bytes(nonce)
        ) else { throw DemoCryptoError.decryptionFailed }

        guard let text = String(bytes: opened, encoding: .utf8) else { throw DemoCryptoError.decryptionFailed }
        return text
    }
}
