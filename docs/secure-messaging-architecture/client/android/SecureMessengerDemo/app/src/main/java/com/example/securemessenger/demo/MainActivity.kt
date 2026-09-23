/*
 * MainActivity.kt
 *
 * UI-Spiegel der Web-Demo (client/web/index.html): eigene Identität,
 * Kontakt per ID hinzufügen, echter Chat über MQTT (siehe
 * ../../../../../../../../PROTOCOL.md), Gegenproben im Tech-Log.
 */

package com.example.securemessenger.demo

import android.content.ClipData
import android.content.ClipboardManager
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.Button
import androidx.compose.material3.Card
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.icons.Icons
import androidx.compose.runtime.Composable
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            MaterialTheme {
                Surface(modifier = Modifier.fillMaxSize()) {
                    val model = remember { AppModel(applicationContext) }
                    DemoScreen(model)
                }
            }
        }
    }
}

@Composable
fun DemoScreen(model: AppModel) {
    val clipboard = androidx.compose.ui.platform.LocalContext.current
        .getSystemService(ClipboardManager::class.java)

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
            StatusDot(model.connectionStatus)
            Text(model.connectionStatusText, style = MaterialTheme.typography.bodySmall)
        }

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("MEINE IDENTITÄT", style = MaterialTheme.typography.labelSmall)
                Text(model.me.idString, style = MaterialTheme.typography.bodySmall)
                OutlinedButton(onClick = {
                    clipboard?.setPrimaryClip(ClipData.newPlainText("Cipher Wire ID", model.me.idString))
                }) { Text("ID kopieren") }
            }
        }

        if (model.contact == null) {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("KONTAKT HINZUFÜGEN", style = MaterialTheme.typography.labelSmall)
                    Text(
                        "ID vom anderen Gerät außerhalb dieses Kanals austauschen (persönlich/QR) — sonst ist eine Man-in-the-Middle-Zuordnung nicht ausgeschlossen.",
                        style = MaterialTheme.typography.bodySmall
                    )
                    OutlinedTextField(
                        value = model.contactInputText,
                        onValueChange = { model.contactInputText = it },
                        label = { Text("boxPubHex.signPubHex") },
                        modifier = Modifier.fillMaxWidth()
                    )
                    Button(onClick = { model.addContact() }) { Text("Hinzufügen") }
                }
            }
        } else {
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Row(
                        modifier = Modifier.fillMaxWidth(),
                        horizontalArrangement = Arrangement.SpaceBetween,
                        verticalAlignment = Alignment.CenterVertically
                    ) {
                        Text(
                            model.contact!!.boxPublicKey.toHex().take(12) + "…",
                            fontWeight = FontWeight.Bold
                        )
                        OutlinedButton(onClick = { model.removeContact() }) { Text("Entfernen") }
                    }

                    LazyColumn(
                        modifier = Modifier.heightIn(max = 320.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        if (model.messages.isEmpty()) {
                            item { Text("Noch keine Nachrichten.", style = MaterialTheme.typography.bodySmall) }
                        }
                        items(model.messages) { m ->
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = if (m.mine) Arrangement.End else Arrangement.Start
                            ) {
                                Surface(
                                    color = if (m.mine) Color(0xFFDCEFE9) else Color(0xFFF5E3D3),
                                    shape = MaterialTheme.shapes.medium
                                ) {
                                    Text(m.text, modifier = Modifier.padding(8.dp))
                                }
                            }
                        }
                    }

                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        OutlinedTextField(
                            value = model.sendText,
                            onValueChange = { model.sendText = it },
                            label = { Text("Nachricht…") },
                            modifier = Modifier.weight(1f)
                        )
                        Button(onClick = { model.send() }) { Text("Senden") }
                    }
                }
            }
        }

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
                Text("TECHNISCHES LOG & GEGENPROBEN", style = MaterialTheme.typography.labelSmall)
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    OutlinedButton(onClick = { model.runTamperTest() }) { Text("Manipulation testen") }
                    OutlinedButton(onClick = { model.runForgedSignatureTest() }) { Text("Fake-Signatur testen") }
                }
                OutlinedButton(onClick = { model.clearLog() }) { Text("Log leeren") }
                LazyColumn(modifier = Modifier.heightIn(max = 220.dp)) {
                    items(model.techLog) { entry ->
                        Text(
                            entry.text,
                            style = MaterialTheme.typography.bodySmall,
                            color = colorFor(entry.kind)
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun StatusDot(status: ConnectionStatus) {
    val color = when (status) {
        ConnectionStatus.LIVE -> Color(0xFF1F6F61)
        ConnectionStatus.WARN, ConnectionStatus.CONNECTING -> Color(0xFF8A6D1F)
        ConnectionStatus.ERROR -> Color(0xFFA3341F)
    }
    Surface(color = color, shape = MaterialTheme.shapes.small) {
        androidx.compose.foundation.layout.Box(modifier = Modifier.padding(4.dp))
    }
}

private fun colorFor(kind: LogKind): Color = when (kind) {
    LogKind.OK -> Color(0xFF1F6F61)
    LogKind.FAIL -> Color(0xFFA3341F)
    LogKind.WARN -> Color(0xFF8A6D1F)
    LogKind.INFO -> Color.Gray
}
