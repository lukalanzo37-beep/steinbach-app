/*
 * IdentityStore.kt
 *
 * Persistiert die Demo-Identität über App-Neustarts hinweg, damit ein
 * Kontakt dich über mehrere Sitzungen hinweg unter derselben ID erreichen
 * kann. Zu Testzwecken in SharedPreferences (Klartext) -- entspricht dem
 * localStorage-Ansatz der Web-Demo, NICHT der gehärteten
 * Keystore-Variante in ../SecureKeyStorage.kt.
 */

package com.example.securemessenger.demo

import android.content.Context

private const val PREFS = "cipherwire_identity_prefs"
private const val KEY_IDENTITY = "identity_v1"

object IdentityStore {

    fun loadOrCreate(context: Context, crypto: DemoCrypto): Identity {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val stored = prefs.getString(KEY_IDENTITY, null)
        if (stored != null) {
            deserialize(stored)?.let { return it }
        }
        val fresh = crypto.generateIdentity()
        prefs.edit().putString(KEY_IDENTITY, serialize(fresh)).apply()
        return fresh
    }

    private fun serialize(id: Identity): String =
        listOf(id.boxPublicKey, id.boxSecretKey, id.signPublicKey, id.signSecretKey)
            .joinToString(".") { it.toHex() }

    private fun deserialize(s: String): Identity? {
        val parts = s.split(".")
        if (parts.size != 4) return null
        return try {
            Identity(
                boxPublicKey = parts[0].fromHex(), boxSecretKey = parts[1].fromHex(),
                signPublicKey = parts[2].fromHex(), signSecretKey = parts[3].fromHex()
            )
        } catch (e: Exception) { null }
    }
}
