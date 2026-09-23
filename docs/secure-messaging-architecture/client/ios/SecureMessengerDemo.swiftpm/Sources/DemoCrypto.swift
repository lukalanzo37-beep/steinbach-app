//
//  DemoCrypto.swift
//
//  Schlanker Demo-Wrapper um Swift-Sodium (NaCl crypto_box). Anders als
//  die produktionsnahe Referenz in ../E2EECryptoManager.swift hält diese
//  Version die Schlüssel bewusst NUR im Arbeitsspeicher (keine Keychain) --
//  damit die Demo ohne Geräte-Vorbedingungen (Passcode/Biometrie) sofort
//  in jedem Simulator läuft. Fürs echte Produkt gehört der Private Key in
//  den Keychain, siehe ../E2EECryptoManager.swift.
//

import Foundation
import Sodium

enum DemoCryptoError: Error, LocalizedError {
    case keyGenerationFailed
    case encryptionFailed
    case decryptionFailed

    var errorDescription: String? {
        switch self {
        case .keyGenerationFailed: return "Schlüsselerzeugung fehlgeschlagen"
        case .encryptionFailed: return "Verschlüsselung fehlgeschlagen"
        case .decryptionFailed: return "Entschlüsselung fehlgeschlagen"
        }
    }
}

struct DemoIdentity {
    let publicKey: Data
    let secretKey: Data
}

struct DemoEnvelope {
    let ciphertext: Data
    let nonce: Data
}

final class DemoCrypto {

    private let sodium = Sodium()

    func generateIdentity() throws -> DemoIdentity {
        guard let kp = sodium.box.keyPair() else {
            throw DemoCryptoError.keyGenerationFailed
        }
        return DemoIdentity(publicKey: Data(kp.publicKey), secretKey: Data(kp.secretKey))
    }

    /// Entspricht encryptMessage() in E2EECryptoManager.swift.
    func encrypt(plaintext: String, recipientPublicKey: Data, senderSecretKey: Data) throws -> DemoEnvelope {
        guard let messageBytes = plaintext.data(using: .utf8) else {
            throw DemoCryptoError.encryptionFailed
        }
        let nonce = sodium.box.nonce()
        guard let sealed = sodium.box.seal(
            message: Bytes(messageBytes),
            recipientPublicKey: Bytes(recipientPublicKey),
            senderSecretKey: Bytes(senderSecretKey),
            nonce: nonce
        ) else {
            throw DemoCryptoError.encryptionFailed
        }
        return DemoEnvelope(ciphertext: Data(sealed), nonce: Data(nonce))
    }

    /// Entspricht decryptMessage() in E2EECryptoManager.swift. Gibt bei
    /// Manipulation oder falschem Absender bewusst nur einen generischen
    /// Fehler zurück (kein Oracle für Angreifer).
    func decrypt(envelope: DemoEnvelope, senderPublicKey: Data, recipientSecretKey: Data) throws -> String {
        guard let decrypted = sodium.box.open(
            authenticatedCipherText: Bytes(envelope.ciphertext),
            senderPublicKey: Bytes(senderPublicKey),
            recipientSecretKey: Bytes(recipientSecretKey),
            nonce: Bytes(envelope.nonce)
        ) else {
            throw DemoCryptoError.decryptionFailed
        }
        guard let text = String(bytes: decrypted, encoding: .utf8) else {
            throw DemoCryptoError.decryptionFailed
        }
        return text
    }
}
