//
//  E2EECryptoManager.swift
//
//  Beispielhafte Ende-zu-Ende-Verschlüsselung nach Threema-Vorbild.
//  Nutzt Swift-Sodium (https://github.com/jedisct1/swift-sodium), einen
//  Swift-Wrapper um libsodium, für NaCl `crypto_box` (X25519 + XSalsa20-Poly1305).
//
//  WICHTIG: Dies ist Referenz-/Lehrcode für eine Architektur-Diskussion,
//  kein auditierter Produktionscode. Vor Produktiveinsatz: unabhängiges
//  Krypto-Audit, siehe README.md Abschnitt 5.
//
//  Abhängigkeit (SwiftPM): .package(url: "https://github.com/jedisct1/swift-sodium.git", ...)
//

import Foundation
import Security
import Sodium

enum CryptoError: Error {
    case keyGenerationFailed
    case keychainAccessControlFailed
    case keychainWriteFailed(OSStatus)
    case keychainReadFailed(OSStatus)
    case invalidInput
    case encryptionFailed
    case decryptionFailed
    case invalidPlaintext
}

/// Verwaltet das langlebige Identitäts-Schlüsselpaar eines Geräts sowie
/// die Ver-/Entschlüsselung einzelner Nachrichten mittels NaCl `crypto_box`.
final class E2EECryptoManager {

    private let sodium = Sodium()

    /// Fester Service-Name für die Keychain-Einträge dieser App.
    private let keychainService = "com.example.securemessenger.identitykey"

    struct KeyPair {
        let publicKey: Data   // wird an den Server übertragen (= öffentliche Identität)
        let secretKey: Data   // verlässt das Gerät NIEMALS
    }

    // MARK: - Schlüsselerzeugung

    /// Erzeugt ein neues Curve25519-Schlüsselpaar direkt auf dem Gerät.
    /// Wird einmalig beim ersten App-Start aufgerufen.
    func generateIdentityKeyPair() throws -> KeyPair {
        guard let kp = sodium.box.keyPair() else {
            throw CryptoError.keyGenerationFailed
        }
        return KeyPair(publicKey: Data(kp.publicKey), secretKey: Data(kp.secretKey))
    }

    // MARK: - Sichere Ablage im Keychain

    /// Speichert den Private Key im iOS-Keychain, geschützt durch Geräte-PIN/
    /// Biometrie. `kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly` sorgt
    /// zusätzlich dafür, dass der Eintrag NIE ins iCloud-Keychain-Backup
    /// synchronisiert wird und geräte-gebunden bleibt.
    func storePrivateKeyInKeychain(_ secretKey: Data, account: String) throws {
        var accessControlError: Unmanaged<CFError>?
        guard let accessControl = SecAccessControlCreateWithFlags(
            kCFAllocatorDefault,
            kSecAttrAccessibleWhenPasscodeSetThisDeviceOnly,
            [.privateKeyUsage, .biometryCurrentSet],
            &accessControlError
        ) else {
            throw CryptoError.keychainAccessControlFailed
        }

        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: account,
            kSecValueData as String: secretKey,
            kSecAttrAccessControl as String: accessControl
        ]

        // Vorherigen Eintrag (falls vorhanden) entfernen, bevor neu geschrieben wird.
        SecItemDelete(query as CFDictionary)

        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else {
            throw CryptoError.keychainWriteFailed(status)
        }
    }

    /// Lädt den Private Key aus dem Keychain. Löst je nach Access-Control-
    /// Konfiguration implizit eine Face-ID/Touch-ID/Code-Abfrage aus.
    func loadPrivateKeyFromKeychain(account: String) throws -> Data {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: keychainService,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne
        ]

        var item: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &item)
        guard status == errSecSuccess, let data = item as? Data else {
            throw CryptoError.keychainReadFailed(status)
        }
        return data
    }

    // MARK: - Authenticated Encryption (NaCl crypto_box)

    /// Verschlüsselt eine Textnachricht für einen bestimmten Empfänger.
    ///
    /// `crypto_box` kombiniert X25519-Diffie-Hellman (zwischen dem
    /// öffentlichen Schlüssel des Empfängers und dem privaten Schlüssel des
    /// Senders) mit XSalsa20-Poly1305. Das Ergebnis ist gleichzeitig
    /// verschlüsselt UND authentifiziert: Der Empfänger kann beim
    /// Entschlüsseln verifizieren, dass die Nachricht tatsächlich vom
    /// behaupteten Absender stammt, ohne eine separate Signatur zu benötigen.
    ///
    /// - Returns: Ciphertext (inkl. 16-Byte Poly1305-MAC) und der verwendete
    ///   24-Byte-Nonce. Beides muss zum Empfänger übertragen werden.
    func encryptMessage(
        plaintext: String,
        recipientPublicKey: Data,
        senderPrivateKey: Data
    ) throws -> (ciphertext: Data, nonce: Data) {
        guard let messageBytes = plaintext.data(using: .utf8) else {
            throw CryptoError.invalidInput
        }

        // 24 zufällige Bytes aus dem CSPRNG von libsodium. Bei zufälligen
        // Nonces dieser Größe ist eine Kollision für dasselbe Schlüsselpaar
        // praktisch ausgeschlossen (Geburtstagsparadoxon auf 192 Bit).
        let nonce = sodium.box.nonce()

        guard let sealed = sodium.box.seal(
            message: Bytes(messageBytes),
            recipientPublicKey: Bytes(recipientPublicKey),
            senderSecretKey: Bytes(senderPrivateKey),
            nonce: nonce
        ) else {
            throw CryptoError.encryptionFailed
        }

        return (Data(sealed), Data(nonce))
    }

    /// Entschlüsselt und verifiziert eine empfangene Nachricht.
    ///
    /// Bei fehlgeschlagener Authentifizierung (falscher Absender, manipulierte
    /// Daten, falscher Nonce) wird ausschließlich ein generischer Fehler
    /// geworfen. Detailliertere Fehlermeldungen wären ein Einfallstor für
    /// Oracle-Angriffe und werden deshalb bewusst nicht unterschieden.
    func decryptMessage(
        ciphertext: Data,
        nonce: Data,
        senderPublicKey: Data,
        recipientPrivateKey: Data
    ) throws -> String {
        guard let decrypted = sodium.box.open(
            authenticatedCipherText: Bytes(ciphertext),
            senderPublicKey: Bytes(senderPublicKey),
            recipientSecretKey: Bytes(recipientPrivateKey),
            nonce: Bytes(nonce)
        ) else {
            throw CryptoError.decryptionFailed
        }

        guard let text = String(bytes: decrypted, encoding: .utf8) else {
            throw CryptoError.invalidPlaintext
        }
        return text
    }
}

// MARK: - Beispielhafter Ablauf (Onboarding + eine Nachricht)

enum ExampleUsage {

    static func onboardNewDevice(manager: E2EECryptoManager) throws -> E2EECryptoManager.KeyPair {
        let keyPair = try manager.generateIdentityKeyPair()
        try manager.storePrivateKeyInKeychain(keyPair.secretKey, account: "device-identity")
        // Nur keyPair.publicKey wird anschließend an den Server übertragen,
        // z. B. bei der Registrierung der anonymen ID (siehe backend/src/main.rs).
        return keyPair
    }

    static func sendMessage(
        manager: E2EECryptoManager,
        text: String,
        myPublicKey: Data,
        recipientPublicKey: Data
    ) throws -> (ciphertext: Data, nonce: Data) {
        let myPrivateKey = try manager.loadPrivateKeyFromKeychain(account: "device-identity")
        return try manager.encryptMessage(
            plaintext: text,
            recipientPublicKey: recipientPublicKey,
            senderPrivateKey: myPrivateKey
        )
    }
}
