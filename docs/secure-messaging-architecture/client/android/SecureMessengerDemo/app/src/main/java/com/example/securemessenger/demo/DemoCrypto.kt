/*
 * DemoCrypto.kt
 *
 * Implementiert exakt das in ../../../../../../../../PROTOCOL.md
 * beschriebene Wire-Format: Langzeit-Box-Identität + Langzeit-
 * Signatur-Identität, pro Nachricht ein frisches, signiertes
 * Ephemeral-Schlüsselpaar für Forward Secrecy. Muss mit DemoCrypto.swift
 * (iOS) und dem Krypto-Teil von client/web/index.html kompatibel bleiben.
 *
 * Schlüsselspeicherung: zu Testzwecken in SharedPreferences (Klartext,
 * entspricht dem localStorage-Ansatz der Web-Demo) -- NICHT die
 * gehärtete Variante. Für die produktionsnahe Keystore-Absicherung siehe
 * ../SecureKeyStorage.kt.
 */

package com.example.securemessenger.demo

import com.goterl.lazysodium.LazySodiumAndroid
import com.goterl.lazysodium.SodiumAndroid
import com.goterl.lazysodium.interfaces.Box
import com.goterl.lazysodium.interfaces.Sign
import com.goterl.lazysodium.utils.Key

sealed class DemoCryptoException(message: String) : Exception(message) {
    object KeyGenerationFailed : DemoCryptoException("Schlüsselerzeugung fehlgeschlagen")
    object EncryptionFailed : DemoCryptoException("Verschlüsselung fehlgeschlagen")
    object SignatureInvalid : DemoCryptoException("Ephemeral-Signatur ungültig")
    object DecryptionFailed : DemoCryptoException("Entschlüsselung fehlgeschlagen")
    object MalformedEnvelope : DemoCryptoException("Ungültiges Envelope-Format")
}

data class Identity(
    val boxPublicKey: ByteArray, val boxSecretKey: ByteArray,
    val signPublicKey: ByteArray, val signSecretKey: ByteArray
) {
    /** PROTOCOL.md: "<boxPubHex>.<signPubHex>" */
    val idString: String get() = boxPublicKey.toHex() + "." + signPublicKey.toHex()
}

data class ContactIdentity(val boxPublicKey: ByteArray, val signPublicKey: ByteArray)

/** PROTOCOL.md Envelope-Feldnamen 1:1 übernommen, damit sie mit Web/iOS matchen. */
data class Envelope(
    val senderBoxPub: String, val senderSignPub: String,
    val ephPub: String, val ephSig: String,
    val nonce: String, val ciphertext: String
)

fun ByteArray.toHex(): String = joinToString("") { "%02x".format(it) }
fun String.fromHex(): ByteArray {
    require(length % 2 == 0) { "Ungerade Hex-Länge" }
    return ByteArray(length / 2) { i -> substring(i * 2, i * 2 + 2).toInt(16).toByte() }
}

class DemoCrypto {

    private val sodium = LazySodiumAndroid(SodiumAndroid())

    fun generateIdentity(): Identity {
        val box = sodium.cryptoBoxKeypair() ?: throw DemoCryptoException.KeyGenerationFailed
        val sign = sodium.cryptoSignKeypair() ?: throw DemoCryptoException.KeyGenerationFailed
        return Identity(
            box.publicKey.asBytes, box.secretKey.asBytes,
            sign.publicKey.asBytes, sign.secretKey.asBytes
        )
    }

    fun parseContactIdString(s: String): ContactIdentity? {
        val parts = s.trim().split(".")
        if (parts.size != 2 || parts[0].length != 64 || parts[1].length != 64) return null
        return try {
            ContactIdentity(parts[0].fromHex(), parts[1].fromHex())
        } catch (e: Exception) { null }
    }

    /** PROTOCOL.md "Senden (Verschlüsseln)": signiertes Ephemeral crypto_box. */
    fun encryptForward(plaintext: String, recipientBoxPub: ByteArray, me: Identity): Envelope {
        val eph = sodium.cryptoBoxKeypair() ?: throw DemoCryptoException.EncryptionFailed

        val ephSig = ByteArray(Sign.ED25519_BYTES)
        val sigLen = LongArray(1)
        val signOk = sodium.cryptoSignDetached(
            ephSig, sigLen, eph.publicKey.asBytes, eph.publicKey.asBytes.size.toLong(), me.signSecretKey
        )
        if (!signOk) throw DemoCryptoException.EncryptionFailed

        val nonce = ByteArray(Box.NONCEBYTES)
        sodium.randomBytesBuf(nonce, nonce.size)
        val messageBytes = plaintext.toByteArray(Charsets.UTF_8)
        val cipherBytes = ByteArray(messageBytes.size + Box.MACBYTES)
        val boxOk = sodium.cryptoBoxEasy(
            cipherBytes, messageBytes, messageBytes.size.toLong(),
            nonce, recipientBoxPub, eph.secretKey.asBytes
        )
        if (!boxOk) throw DemoCryptoException.EncryptionFailed

        // eph.secretKey wird ab hier nicht mehr referenziert (best effort
        // ohne manuelles Memory-Zeroing, siehe README Fallstrick Nr. 7).
        return Envelope(
            senderBoxPub = me.boxPublicKey.toHex(),
            senderSignPub = me.signPublicKey.toHex(),
            ephPub = eph.publicKey.asBytes.toHex(),
            ephSig = ephSig.toHex(),
            nonce = nonce.toHex(),
            ciphertext = cipherBytes.toHex()
        )
    }

    /** PROTOCOL.md "Empfangen (Entschlüsseln)". */
    fun decryptForward(envelope: Envelope, expectedSignPub: ByteArray, myBoxSecret: ByteArray): String {
        val ephPub = try { envelope.ephPub.fromHex() } catch (e: Exception) { throw DemoCryptoException.MalformedEnvelope }
        val ephSig = try { envelope.ephSig.fromHex() } catch (e: Exception) { throw DemoCryptoException.MalformedEnvelope }
        val nonce = try { envelope.nonce.fromHex() } catch (e: Exception) { throw DemoCryptoException.MalformedEnvelope }
        val ciphertext = try { envelope.ciphertext.fromHex() } catch (e: Exception) { throw DemoCryptoException.MalformedEnvelope }

        // Hinweis: Diese Datei konnte in dieser Umgebung nicht gegen den
        // Android-Gradle-Build kompiliert werden (kein Android SDK
        // verfügbar). Falls die LazySodium-Version eine andere
        // Parameterreihenfolge/-typen für cryptoSignVerifyDetached
        // erwartet, bitte die genaue Compiler-Fehlermeldung zurückmelden.
        val sigOk = sodium.cryptoSignVerifyDetached(ephSig, ephPub, ephPub.size, expectedSignPub)
        if (!sigOk) throw DemoCryptoException.SignatureInvalid

        val plainLength = ciphertext.size - Box.MACBYTES
        if (plainLength < 0) throw DemoCryptoException.DecryptionFailed
        val plainBytes = ByteArray(plainLength)
        val ok = sodium.cryptoBoxOpenEasy(plainBytes, ciphertext, ciphertext.size.toLong(), nonce, ephPub, myBoxSecret)
        if (!ok) throw DemoCryptoException.DecryptionFailed
        return String(plainBytes, Charsets.UTF_8)
    }
}
