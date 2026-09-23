/*
 * AppModel.kt
 *
 * Verbindet Identität, Kontakt, Transport und Krypto zu dem in
 * ../../../../../../../../PROTOCOL.md beschriebenen Ablauf. Hält den
 * Zustand als Compose State; alle Callbacks von Transport (Paho-Threads)
 * springen über Handler(mainLooper) auf den Haupt-Thread zurück, bevor sie
 * State verändern -- Compose State darf nur vom Haupt-Thread aus
 * geschrieben werden.
 */

package com.example.securemessenger.demo

import android.content.Context
import android.os.Handler
import android.os.Looper
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import org.json.JSONArray
import org.json.JSONObject

data class ChatMessage(val text: String, val mine: Boolean)
data class LogEntry(val text: String, val kind: LogKind)

private const val PREFS = "cipherwire_app_prefs"
private const val KEY_CONTACT = "contact_v1"
private const val KEY_HISTORY = "history_v1"

class AppModel(private val context: Context) {

    val crypto = DemoCrypto()
    val transport = Transport()
    val me: Identity = IdentityStore.loadOrCreate(context, crypto)

    var contact by mutableStateOf<ContactIdentity?>(null)
        private set
    var contactInputText by mutableStateOf("")
    var sendText by mutableStateOf("")
    val messages = mutableStateListOf<ChatMessage>()
    val techLog = mutableStateListOf<LogEntry>()

    var connectionStatus by mutableStateOf(ConnectionStatus.CONNECTING)
        private set
    var connectionStatusText by mutableStateOf("Verbinde…")
        private set

    private val mainHandler = Handler(Looper.getMainLooper())
    private fun onMain(block: () -> Unit) = mainHandler.post(block)

    init {
        loadContact()
        loadHistory()

        transport.onStatus = { status, text ->
            onMain { connectionStatus = status; connectionStatusText = text }
        }
        transport.onLog = { text, kind -> onMain { log(text, kind) } }
        transport.onEnvelope = { envelope -> onMain { handleIncoming(envelope) } }

        transport.connect(me.boxPublicKey.toHex())
        log("Meine ID: " + me.idString, LogKind.INFO)
    }

    fun log(text: String, kind: LogKind) { techLog.add(LogEntry(text, kind)) }
    fun clearLog() { techLog.clear() }

    fun addContact() {
        val parsed = crypto.parseContactIdString(contactInputText)
        if (parsed == null) {
            log("✗ Ungültiges ID-Format (erwartet: 64 Hex . 64 Hex)", LogKind.FAIL)
            return
        }
        contact = parsed
        messages.clear()
        contactInputText = ""
        saveContact(parsed)
        saveHistory()
    }

    fun removeContact() {
        contact = null
        messages.clear()
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .remove(KEY_CONTACT).remove(KEY_HISTORY).apply()
    }

    fun send() {
        val c = contact ?: return
        val text = sendText.trim()
        if (text.isEmpty()) return
        sendText = ""
        messages.add(ChatMessage(text, mine = true))
        saveHistory()

        try {
            val envelope = crypto.encryptForward(text, c.boxPublicKey, me)
            log("→ gesendet, Ephemeral ${envelope.ephPub.take(12)}…", LogKind.INFO)
            transport.publish("cipherwire-demo-v1/" + c.boxPublicKey.toHex(), envelope)
        } catch (e: Exception) {
            log("✗ ${e.message}", LogKind.FAIL)
        }
    }

    private fun handleIncoming(envelope: Envelope) {
        val c = contact
        if (c == null || envelope.senderBoxPub != c.boxPublicKey.toHex()) {
            log("✗ Nachricht von unbekannter/nicht hinzugefügter ID ignoriert", LogKind.WARN)
            return
        }
        try {
            val text = crypto.decryptForward(envelope, c.signPublicKey, me.boxSecretKey)
            messages.add(ChatMessage(text, mine = false))
            saveHistory()
            log("✓ empfangen, Signatur + Verschlüsselung verifiziert", LogKind.OK)
        } catch (e: Exception) {
            log("✗ Empfangene Nachricht verworfen: ${e.message}", LogKind.FAIL)
        }
    }

    // ---------- Gegenproben ----------

    fun runTamperTest() {
        val targetPub = contact?.boxPublicKey ?: me.boxPublicKey
        val envelope = try { crypto.encryptForward("Testnachricht für Manipulationsprobe", targetPub, me) } catch (e: Exception) { return }
        val tamperedBytes = envelope.ciphertext.fromHex()
        tamperedBytes[0] = (tamperedBytes[0].toInt() xor 0xFF).toByte()
        val tampered = envelope.copy(ciphertext = tamperedBytes.toHex())
        log("Gegenprobe: 1 Bit im Ciphertext verändert …", LogKind.INFO)
        try {
            crypto.decryptForward(tampered, me.signPublicKey, me.boxSecretKey)
            log("✗ Fehler: Manipulation hätte erkannt werden müssen!", LogKind.FAIL)
        } catch (e: Exception) {
            log("✓ korrekt abgelehnt: ${e.message}", LogKind.OK)
        }
    }

    fun runForgedSignatureTest() {
        val attacker = crypto.generateIdentity()
        val forged = try { crypto.encryptForward("gefälscht", me.boxPublicKey, attacker) } catch (e: Exception) { return }
        // Envelope gibt vor "ich" zu sein, ist aber mit dem
        // Signaturschlüssel eines Angreifers signiert.
        val spoofed = forged.copy(senderBoxPub = me.boxPublicKey.toHex(), senderSignPub = me.signPublicKey.toHex())
        log("Gegenprobe: gefälschte Ephemeral-Signatur (falscher Signaturschlüssel) …", LogKind.INFO)
        try {
            crypto.decryptForward(spoofed, me.signPublicKey, me.boxSecretKey)
            log("✗ Fehler: gefälschte Signatur hätte erkannt werden müssen!", LogKind.FAIL)
        } catch (e: Exception) {
            log("✓ korrekt abgelehnt: ${e.message}", LogKind.OK)
        }
    }

    // ---------- Persistenz (Klartext-SharedPreferences) ----------

    private fun loadContact() {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val s = prefs.getString(KEY_CONTACT, null) ?: return
        contact = crypto.parseContactIdString(s)
    }

    private fun saveContact(c: ContactIdentity) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString(KEY_CONTACT, c.boxPublicKey.toHex() + "." + c.signPublicKey.toHex())
            .apply()
    }

    private fun loadHistory() {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val s = prefs.getString(KEY_HISTORY, null) ?: return
        try {
            val arr = JSONArray(s)
            for (i in 0 until arr.length()) {
                val obj = arr.getJSONObject(i)
                messages.add(ChatMessage(obj.getString("text"), obj.getBoolean("mine")))
            }
        } catch (e: Exception) { /* korrupte/alte Historie ignorieren */ }
    }

    private fun saveHistory() {
        val arr = JSONArray()
        messages.forEach { m ->
            arr.put(JSONObject().apply { put("text", m.text); put("mine", m.mine) })
        }
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).edit()
            .putString(KEY_HISTORY, arr.toString())
            .apply()
    }
}
