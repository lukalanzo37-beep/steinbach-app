/*
 * Transport.kt
 *
 * MQTT-Anbindung an denselben öffentlichen Test-Broker wie die Web- und
 * iOS-Demo (siehe ../../../../../../../../PROTOCOL.md) -- Platzhalter für
 * den echten "blinden" Relay-Server in backend/src/main.rs. Nutzt Eclipse
 * Paho direkt (ohne den Android-Service-Wrapper) für eine einfache,
 * foreground-taugliche Demo-Anbindung.
 *
 * Hinweis: Netzwerk-Callbacks von Paho laufen auf einem Hintergrund-Thread
 * -- UI-Updates müssen über den Haupt-Thread laufen (siehe AppModel.kt).
 */

package com.example.securemessenger.demo

import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken
import org.eclipse.paho.client.mqttv3.MqttCallback
import org.eclipse.paho.client.mqttv3.MqttClient
import org.eclipse.paho.client.mqttv3.MqttConnectOptions
import org.eclipse.paho.client.mqttv3.MqttMessage
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence
import org.json.JSONObject
import kotlin.concurrent.thread

enum class ConnectionStatus { CONNECTING, LIVE, WARN, ERROR }
enum class LogKind { INFO, OK, WARN, FAIL }

private const val TOPIC_PREFIX = "cipherwire-demo-v1/"
private const val BROKER_URI = "ssl://test.mosquitto.org:8883"

class Transport {

    var onStatus: ((ConnectionStatus, String) -> Unit)? = null
    var onLog: ((String, LogKind) -> Unit)? = null
    var onEnvelope: ((Envelope) -> Unit)? = null

    private var client: MqttClient? = null
    private var ownTopic: String? = null

    fun connect(ownBoxPubHex: String) {
        ownTopic = TOPIC_PREFIX + ownBoxPubHex
        onStatus?.invoke(ConnectionStatus.CONNECTING, "Verbinde…")

        thread(name = "cipherwire-mqtt-connect") {
            try {
                val clientId = "cipherwire-android-" + (100000..999999).random()
                val c = MqttClient(BROKER_URI, clientId, MemoryPersistence())
                c.setCallback(object : MqttCallback {
                    override fun connectionLost(cause: Throwable?) {
                        onStatus?.invoke(ConnectionStatus.WARN, "Getrennt" + (cause?.message?.let { ": $it" } ?: ""))
                    }
                    override fun messageArrived(topic: String?, message: MqttMessage?) {
                        val payload = message?.payload ?: return
                        val envelope = try { parseEnvelopeJson(String(payload, Charsets.UTF_8)) } catch (e: Exception) { null }
                        if (envelope != null) onEnvelope?.invoke(envelope)
                    }
                    override fun deliveryComplete(token: IMqttDeliveryToken?) {}
                })

                val options = MqttConnectOptions().apply {
                    isCleanSession = true
                    connectionTimeout = 10
                    isAutomaticReconnect = true
                }
                c.connect(options)
                c.subscribe(ownTopic, 1)
                client = c
                onStatus?.invoke(ConnectionStatus.LIVE, "Verbunden (öffentliches Test-Relay)")
                onLog?.invoke("✓ Transport verbunden", LogKind.OK)
            } catch (e: Exception) {
                onStatus?.invoke(ConnectionStatus.ERROR, "Verbindungsfehler: ${e.message}")
                onLog?.invoke("✗ Transportfehler: ${e.message}", LogKind.FAIL)
            }
        }
    }

    fun publish(topic: String, envelope: Envelope) {
        val c = client
        if (c == null || !c.isConnected) {
            onLog?.invoke("✗ Nicht verbunden -- Nachricht konnte nicht gesendet werden", LogKind.FAIL)
            return
        }
        thread(name = "cipherwire-mqtt-publish") {
            try {
                c.publish(topic, MqttMessage(envelopeToJson(envelope).toByteArray(Charsets.UTF_8)))
            } catch (e: Exception) {
                onLog?.invoke("✗ Senden fehlgeschlagen: ${e.message}", LogKind.FAIL)
            }
        }
    }
}

// JSON-Kodierung des Envelope-Formats aus PROTOCOL.md über das in Android
// eingebaute org.json (keine zusätzliche JSON-Library-Dependency nötig).

fun envelopeToJson(e: Envelope): String = JSONObject().apply {
    put("senderBoxPub", e.senderBoxPub)
    put("senderSignPub", e.senderSignPub)
    put("ephPub", e.ephPub)
    put("ephSig", e.ephSig)
    put("nonce", e.nonce)
    put("ciphertext", e.ciphertext)
}.toString()

fun parseEnvelopeJson(json: String): Envelope? = try {
    val obj = JSONObject(json)
    Envelope(
        senderBoxPub = obj.getString("senderBoxPub"),
        senderSignPub = obj.getString("senderSignPub"),
        ephPub = obj.getString("ephPub"),
        ephSig = obj.getString("ephSig"),
        nonce = obj.getString("nonce"),
        ciphertext = obj.getString("ciphertext")
    )
} catch (e: Exception) { null }
