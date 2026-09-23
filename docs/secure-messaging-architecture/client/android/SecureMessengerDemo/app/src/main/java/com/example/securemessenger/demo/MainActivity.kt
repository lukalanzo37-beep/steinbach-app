/*
 * MainActivity.kt
 *
 * Zeigt denselben Ablauf wie docs/secure-messaging-architecture/demo_e2ee.py:
 * Alice (dieses Gerät) verschlüsselt eine Nachricht für Bob, Bob
 * entschlüsselt sie, danach zwei Gegenproben (Manipulation, falscher
 * Absender). Nutzt echte NaCl crypto_box-Aufrufe über LazySodium -- keine
 * Mock-/Fake-Kryptografie.
 */

package com.example.securemessenger.demo

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

data class DemoLogLine(val text: String, val isHeading: Boolean = false)

private fun ByteArray.hexPreview(count: Int = 16): String =
    take(count).joinToString("") { "%02x".format(it) } + "…"

private fun runDemo(): List<DemoLogLine> {
    val log = mutableListOf<DemoLogLine>()
    fun add(text: String, heading: Boolean = false) = log.add(DemoLogLine(text, heading))

    val crypto = DemoCrypto()
    try {
        add("1. Schlüsselerzeugung (je Gerät lokal)", heading = true)
        val alice = crypto.generateIdentity()
        val bob = crypto.generateIdentity()
        add("Alice Public Key: ${alice.publicKey.asBytes.hexPreview()}")
        add("Bob   Public Key: ${bob.publicKey.asBytes.hexPreview()}")

        add("2. Alice verschlüsselt eine Nachricht für Bob", heading = true)
        val message = "Hallo Bob, dieser Text ist Ende-zu-Ende verschlüsselt."
        val envelope = crypto.encrypt(message, bob.publicKey.asBytes, alice.secretKey.asBytes)
        add("Klartext:   $message")
        add("Nonce:      ${envelope.nonce.joinToString("") { "%02x".format(it) }}")
        add("Ciphertext: ${envelope.ciphertext.hexPreview(32)}")

        add("3. Bob entschlüsselt und verifiziert", heading = true)
        val decrypted = crypto.decrypt(envelope, alice.publicKey.asBytes, bob.secretKey.asBytes)
        add("Entschlüsselt: $decrypted")
        add(if (decrypted == message) "✅ Stimmt mit Original überein" else "❌ Unterschied!")

        add("4. Gegenprobe: manipulierter Ciphertext", heading = true)
        val tampered = envelope.ciphertext.copyOf()
        tampered[0] = (tampered[0].toInt() xor 0xFF).toByte()
        try {
            crypto.decrypt(DemoEnvelope(tampered, envelope.nonce), alice.publicKey.asBytes, bob.secretKey.asBytes)
            add("❌ Fehler: Manipulation hätte erkannt werden müssen!")
        } catch (e: DemoCryptoException) {
            add("✅ Erwartetes Verhalten: ${e.message}")
        }

        add("5. Gegenprobe: falscher Absender", heading = true)
        val mallory = crypto.generateIdentity()
        try {
            crypto.decrypt(envelope, mallory.publicKey.asBytes, bob.secretKey.asBytes)
            add("❌ Fehler: falscher Absender hätte erkannt werden müssen!")
        } catch (e: DemoCryptoException) {
            add("✅ Erwartetes Verhalten: ${e.message}")
        }
    } catch (e: Exception) {
        add("Fehler: ${e.message}")
    }
    return log
}

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    DemoScreen()
                }
            }
        }
    }
}

@Composable
fun DemoScreen() {
    var log by remember { mutableStateOf<List<DemoLogLine>>(emptyList()) }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Text("NaCl crypto_box Demo (Android)", style = MaterialTheme.typography.titleMedium)

        Button(onClick = { log = runDemo() }, modifier = Modifier.fillMaxWidth()) {
            Text("Demo starten")
        }

        LazyColumn(verticalArrangement = Arrangement.spacedBy(2.dp)) {
            items(log) { line ->
                Text(
                    text = line.text,
                    fontWeight = if (line.isHeading) FontWeight.Bold else FontWeight.Normal,
                    style = if (line.isHeading) MaterialTheme.typography.bodyMedium
                            else MaterialTheme.typography.bodySmall
                )
            }
        }
    }
}
