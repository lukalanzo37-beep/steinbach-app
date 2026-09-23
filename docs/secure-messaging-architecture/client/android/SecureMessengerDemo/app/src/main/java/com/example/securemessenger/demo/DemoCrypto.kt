/*
 * DemoCrypto.kt
 *
 * Schlanker Demo-Wrapper um LazySodium (NaCl crypto_box). Anders als die
 * produktionsnahe Referenz in ../../../../../../../E2EECryptoManager.kt +
 * SecureKeyStorage.kt hält diese Version die Schlüssel bewusst NUR im
 * Arbeitsspeicher (kein Android-Keystore-Wrapping) -- damit die Demo ohne
 * Geräte-Vorbedingungen sofort in jedem Emulator läuft. Fürs echte Produkt
 * gehört der Private Key hinter Keystore-Key-Wrapping, siehe die
 * Referenzdateien im übergeordneten android-Ordner.
 */

package com.example.securemessenger.demo

import com.goterl.lazysodium.LazySodiumAndroid
import com.goterl.lazysodium.SodiumAndroid
import com.goterl.lazysodium.interfaces.Box
import com.goterl.lazysodium.utils.KeyPair

sealed class DemoCryptoException(message: String) : Exception(message) {
    object KeyGenerationFailed : DemoCryptoException("Schlüsselerzeugung fehlgeschlagen")
    object EncryptionFailed : DemoCryptoException("Verschlüsselung fehlgeschlagen")
    object DecryptionFailed : DemoCryptoException("Entschlüsselung fehlgeschlagen")
}

data class DemoEnvelope(val ciphertext: ByteArray, val nonce: ByteArray)

class DemoCrypto {

    private val sodium = LazySodiumAndroid(SodiumAndroid())

    fun generateIdentity(): KeyPair =
        sodium.cryptoBoxKeypair() ?: throw DemoCryptoException.KeyGenerationFailed

    /** Entspricht encryptMessage() in ../E2EECryptoManager.kt. */
    fun encrypt(plaintext: String, recipientPublicKey: ByteArray, senderSecretKey: ByteArray): DemoEnvelope {
        val messageBytes = plaintext.toByteArray(Charsets.UTF_8)
        val nonce = ByteArray(Box.NONCEBYTES)
        sodium.randomBytesBuf(nonce, nonce.size)

        val cipherBytes = ByteArray(messageBytes.size + Box.MACBYTES)
        val success = sodium.cryptoBoxEasy(
            cipherBytes, messageBytes, messageBytes.size.toLong(),
            nonce, recipientPublicKey, senderSecretKey
        )
        if (!success) throw DemoCryptoException.EncryptionFailed
        return DemoEnvelope(cipherBytes, nonce)
    }

    /**
     * Entspricht decryptMessage() in ../E2EECryptoManager.kt. Gibt bei
     * Manipulation oder falschem Absender bewusst nur einen generischen
     * Fehler zurück (kein Oracle für Angreifer).
     */
    fun decrypt(envelope: DemoEnvelope, senderPublicKey: ByteArray, recipientSecretKey: ByteArray): String {
        val plainLength = envelope.ciphertext.size - Box.MACBYTES
        if (plainLength < 0) throw DemoCryptoException.DecryptionFailed

        val plainBytes = ByteArray(plainLength)
        val success = sodium.cryptoBoxOpenEasy(
            plainBytes, envelope.ciphertext, envelope.ciphertext.size.toLong(),
            envelope.nonce, senderPublicKey, recipientSecretKey
        )
        if (!success) throw DemoCryptoException.DecryptionFailed
        return String(plainBytes, Charsets.UTF_8)
    }
}
