//
//  IdentityStore.swift
//
//  Persistiert die Demo-Identität über App-Neustarts hinweg, damit ein
//  Kontakt dich über mehrere Sitzungen hinweg unter derselben ID erreichen
//  kann. Zu Testzwecken in UserDefaults (Klartext) -- entspricht dem
//  localStorage-Ansatz der Web-Demo, NICHT der gehärteten
//  Keychain-Variante in ../E2EECryptoManager.swift.
//

import Foundation

enum IdentityStore {
    private static let key = "cipherwire_identity_v1"

    static func loadOrCreate(crypto: DemoCrypto) -> Identity {
        if let stored = UserDefaults.standard.string(forKey: key), let identity = deserialize(stored) {
            return identity
        }
        guard let fresh = try? crypto.generateIdentity() else {
            fatalError("Schlüsselerzeugung fehlgeschlagen -- CSPRNG des Systems nicht verfügbar?")
        }
        UserDefaults.standard.set(serialize(fresh), forKey: key)
        return fresh
    }

    private static func serialize(_ id: Identity) -> String {
        [id.boxPublicKey, id.boxSecretKey, id.signPublicKey, id.signSecretKey]
            .map { $0.hexString }
            .joined(separator: ".")
    }

    private static func deserialize(_ s: String) -> Identity? {
        let parts = s.split(separator: ".").map(String.init)
        guard parts.count == 4,
              let boxPub = Data(hexString: parts[0]),
              let boxSec = Data(hexString: parts[1]),
              let signPub = Data(hexString: parts[2]),
              let signSec = Data(hexString: parts[3])
        else { return nil }
        return Identity(boxPublicKey: boxPub, boxSecretKey: boxSec, signPublicKey: signPub, signSecretKey: signSec)
    }
}
