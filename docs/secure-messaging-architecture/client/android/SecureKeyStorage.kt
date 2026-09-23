/*
 * SecureKeyStorage.kt
 *
 * Der Android Keystore kann Curve25519-Rohschlüssel (wie sie libsodium für
 * crypto_box erzeugt) NICHT nativ halten -- er unterstützt nur RSA, EC
 * (secp256r1) und AES. Deshalb wird hier "Key Wrapping" (Envelope
 * Encryption) verwendet:
 *
 *   1. Ein AES-256-GCM-Schlüssel wird hardware-gebunden (idealerweise in
 *      einem StrongBox-Secure-Element) im Android Keystore erzeugt. Dieser
 *      Schlüssel verlässt das gesicherte Hardware-Modul selbst nie.
 *   2. Der rohe Curve25519-Private-Key wird mit diesem AES-Schlüssel
 *      verschlüsselt ("gewickelt") und nur in dieser verschlüsselten Form
 *      auf Disk (SharedPreferences/Room) abgelegt.
 *   3. Beim Zugriff entschlüsselt der Keystore-Schlüssel den Blob wieder --
 *      optional erst nach Biometrie-Freigabe (setUserAuthenticationRequired).
 *
 * Referenz-/Lehrcode, kein auditierter Produktionscode.
 */

package com.example.securemessenger.crypto

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class SecureKeyStorage(private val context: Context) {

    private val androidKeyStore = "AndroidKeyStore"
    private val wrappingKeyAlias = "identity_key_wrapper"
    private val prefsFile = "secure_key_blob"
    private val gcmTagLengthBits = 128

    private fun getOrCreateWrappingKey(): SecretKey {
        val keyStore = KeyStore.getInstance(androidKeyStore).apply { load(null) }
        (keyStore.getKey(wrappingKeyAlias, null) as? SecretKey)?.let { return it }

        val keyGenerator = KeyGenerator.getInstance(
            KeyProperties.KEY_ALGORITHM_AES, androidKeyStore
        )
        val specBuilder = KeyGenParameterSpec.Builder(
            wrappingKeyAlias,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setUserAuthenticationRequired(true) // Biometrie/Geräte-PIN erforderlich
            .setRandomizedEncryptionRequired(true)

        // StrongBox (dediziertes Secure Element) nutzen, falls das Gerät es
        // unterstützt -- fällt sonst automatisch auf TEE-Backing zurück.
        try {
            specBuilder.setIsStrongBoxBacked(true)
        } catch (_: Throwable) {
            // Gerät ohne StrongBox: TEE-gebundener Key ist der Fallback,
            // weiterhin deutlich sicherer als reiner Software-Schlüssel.
        }

        keyGenerator.init(specBuilder.build())
        return keyGenerator.generateKey()
    }

    /**
     * Verschlüsselt den rohen Private Key mit dem Keystore-gebundenen
     * AES-Schlüssel und persistiert nur das Ergebnis. Der Rohschlüssel wird
     * danach im Speicher aktiv überschrieben (best effort -- siehe
     * README.md Fallstricke Nr. 7 zu den Grenzen davon in JVM-Sprachen).
     */
    fun wrapAndStorePrivateKey(rawPrivateKey: ByteArray) {
        val wrappingKey = getOrCreateWrappingKey()
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, wrappingKey)

        val ciphertext = cipher.doFinal(rawPrivateKey)
        val iv = cipher.iv

        context.getSharedPreferences(prefsFile, Context.MODE_PRIVATE)
            .edit()
            .putString("iv", Base64.encodeToString(iv, Base64.NO_WRAP))
            .putString("blob", Base64.encodeToString(ciphertext, Base64.NO_WRAP))
            .apply()

        rawPrivateKey.fill(0)
    }

    /**
     * Entschlüsselt den gespeicherten Private Key wieder. Löst -- abhängig
     * von der Keystore-Konfiguration -- implizit eine BiometricPrompt-Abfrage
     * aus, bevor der Cipher nutzbar ist.
     */
    fun unwrapPrivateKey(): ByteArray {
        val prefs = context.getSharedPreferences(prefsFile, Context.MODE_PRIVATE)
        val iv = Base64.decode(
            prefs.getString("iv", null) ?: error("Kein Schlüssel vorhanden"),
            Base64.NO_WRAP
        )
        val blob = Base64.decode(
            prefs.getString("blob", null) ?: error("Kein Schlüssel vorhanden"),
            Base64.NO_WRAP
        )

        val wrappingKey = getOrCreateWrappingKey()
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, wrappingKey, GCMParameterSpec(gcmTagLengthBits, iv))
        return cipher.doFinal(blob)
    }
}

/*
 * Manifest-Hinweis (nicht Teil dieser Datei, aber zwingend):
 *
 *   <application
 *       android:allowBackup="false"
 *       android:dataExtractionRules="@xml/data_extraction_rules" ... >
 *
 * Ohne diese Einstellung könnte der verschlüsselte Key-Blob potenziell in
 * ein Android-Auto-Backup wandern -- die Geräte-Bindung des
 * StrongBox/TEE-Schlüssels bleibt zwar bestehen (der Blob ist auf einem
 * anderen Gerät nutzlos), aber unnötige Kopien sensibler Daten sollten
 * grundsätzlich vermieden werden.
 */
