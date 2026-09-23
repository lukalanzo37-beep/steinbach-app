/*
 * E2EECryptoManager.kt
 *
 * Ende-zu-Ende-Verschlüsselung nach Threema-Vorbild fuer Android, mittels
 * LazySodium (https://github.com/terl/lazysodium-android), einem
 * Kotlin/Java-Wrapper um libsodium, fuer NaCl `crypto_box`
 * (X25519 + XSalsa20-Poly1305).
 *
 * Referenz-/Lehrcode, kein auditierter Produktionscode. Die genaue API der
 * jeweiligen libsodium-Bindings kann je nach Version leicht abweichen --
 * das Grundprinzip (crypto_box_keypair / crypto_box_easy / crypto_box_open_easy)
 * bleibt gleich.
 *
 * Gradle: implementation "com.goterl:lazysodium-android:5.1.0@aar"
 *         implementation "net.java.dev.jna:jna:5.13.0@aar"
 */

package com.example.securemessenger.crypto

import com.goterl.lazysodium.LazySodiumAndroid
import com.goterl.lazysodium.SodiumAndroid
import com.goterl.lazysodium.interfaces.Box
import com.goterl.lazysodium.utils.Key
import com.goterl.lazysodium.utils.KeyPair
import java.security.SecureRandom

sealed class CryptoException(message: String) : Exception(message) {
    object KeyGenerationFailed : CryptoException("Schluesselerzeugung fehlgeschlagen")
    object EncryptionFailed : CryptoException("Verschluesselung fehlgeschlagen")
    object DecryptionFailed : CryptoException("Entschluesselung fehlgeschlagen")
}

data class EncryptedEnvelope(
    val ciphertext: ByteArray,
    val nonce: ByteArray
)

/**
 * Verwaltet die Curve25519-Identitaet des Geraets sowie die Ver-/
 * Entschluesselung einzelner Nachrichten mittels NaCl `crypto_box`.
 *
 * Der Private Key selbst wird NICHT von dieser Klasse gespeichert --
 * dafuer ist [SecureKeyStorage] (Keystore-Key-Wrapping) zustaendig. Diese
 * Klasse erhaelt den Rohschluessel nur kurzzeitig zur Laufzeit einer
 * Ver-/Entschluesselungsoperation.
 */
class E2EECryptoManager {

    private val sodium = LazySodiumAndroid(SodiumAndroid())
    private val secureRandom = SecureRandom() // niemals java.util.Random fuer Krypto-Zwecke!

    /** Erzeugt ein neues Curve25519-Schluesselpaar direkt auf dem Geraet. */
    fun generateIdentityKeyPair(): KeyPair {
        return sodium.cryptoBoxKeypair()
            ?: throw CryptoException.KeyGenerationFailed
    }

    /**
     * Verschluesselt eine Textnachricht fuer einen bestimmten Empfaenger.
     *
     * `crypto_box_easy` kombiniert X25519-Diffie-Hellman (zwischen dem
     * oeffentlichen Schluessel des Empfaengers und dem privaten Schluessel
     * des Senders) mit XSalsa20-Poly1305 -- gleichzeitig verschluesselt UND
     * authentifiziert, ohne separate Signatur.
     */
    fun encryptMessage(
        plaintext: String,
        recipientPublicKey: Key,
        senderSecretKey: Key
    ): EncryptedEnvelope {
        val messageBytes = plaintext.toByteArray(Charsets.UTF_8)

        // 24 zufaellige Bytes ueber den CSPRNG von libsodium. Bei diesem
        // Nonce-Raum (192 Bit) ist eine Kollision fuer dasselbe
        // Schluesselpaar praktisch ausgeschlossen.
        val nonce = ByteArray(Box.NONCEBYTES)
        sodium.randomBytesBuf(nonce, nonce.size)

        val cipherBytes = ByteArray(messageBytes.size + Box.MACBYTES)
        val success = sodium.cryptoBoxEasy(
            cipherBytes,
            messageBytes,
            messageBytes.size.toLong(),
            nonce,
            recipientPublicKey.asBytes,
            senderSecretKey.asBytes
        )

        if (!success) {
            throw CryptoException.EncryptionFailed
        }

        return EncryptedEnvelope(ciphertext = cipherBytes, nonce = nonce)
    }

    /**
     * Entschluesselt und verifiziert eine empfangene Nachricht.
     *
     * Schlaegt die Authentifizierung fehl (falscher Absender, manipulierte
     * Daten, falscher Nonce), wird ausschliesslich eine generische
     * [CryptoException.DecryptionFailed] geworfen -- keine detaillierteren
     * Fehlermeldungen, um Oracle-Angriffe zu vermeiden.
     */
    fun decryptMessage(
        envelope: EncryptedEnvelope,
        senderPublicKey: Key,
        recipientSecretKey: Key
    ): String {
        val plainLength = envelope.ciphertext.size - Box.MACBYTES
        if (plainLength < 0) {
            throw CryptoException.DecryptionFailed
        }

        val plainBytes = ByteArray(plainLength)
        val success = sodium.cryptoBoxOpenEasy(
            plainBytes,
            envelope.ciphertext,
            envelope.ciphertext.size.toLong(),
            envelope.nonce,
            senderPublicKey.asBytes,
            recipientSecretKey.asBytes
        )

        if (!success) {
            throw CryptoException.DecryptionFailed
        }

        return String(plainBytes, Charsets.UTF_8)
    }
}

/*
 * Beispielhafter Ablauf:
 *
 *   val crypto = E2EECryptoManager()
 *   val keyStorage = SecureKeyStorage(context)
 *
 *   // Einmalig beim Onboarding:
 *   val identity = crypto.generateIdentityKeyPair()
 *   keyStorage.wrapAndStorePrivateKey(identity.secretKey.asBytes)
 *   // identity.publicKey wird an den Server uebertragen (siehe backend/src/main.rs)
 *
 *   // Beim Senden:
 *   val mySecretKeyBytes = keyStorage.unwrapPrivateKey()
 *   val envelope = crypto.encryptMessage(
 *       plaintext = "Hallo!",
 *       recipientPublicKey = recipientPublicKey,
 *       senderSecretKey = Key.fromBytes(mySecretKeyBytes)
 *   )
 *   mySecretKeyBytes.fill(0) // Rohschluessel im Speicher ueberschreiben
 */
