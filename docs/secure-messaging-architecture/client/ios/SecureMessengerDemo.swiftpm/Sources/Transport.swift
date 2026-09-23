//
//  Transport.swift
//
//  MQTT-Anbindung an denselben öffentlichen Test-Broker wie die
//  Web-Demo (siehe ../../../PROTOCOL.md) -- Platzhalter für den echten
//  "blinden" Relay-Server in backend/src/main.rs. Nutzt CocoaMQTT über
//  TLS (native Clients können echtes MQTT statt WebSocket-MQTT sprechen).
//
//  Hinweis: Diese Datei konnte in dieser Umgebung nicht gegen Xcode
//  kompiliert werden (kein macOS verfügbar). Falls CocoaMQTTDelegate hier
//  eine abweichende Methode erwartet (API kann sich zwischen Versionen
//  ändern), bitte die genaue Xcode-Fehlermeldung zurückmelden.
//

import Foundation
import CocoaMQTT

enum ConnectionStatus { case connecting, live, warn, error }
enum LogKind { case info, ok, warn, fail }

final class Transport: NSObject, ObservableObject, CocoaMQTTDelegate {
    @Published var status: ConnectionStatus = .connecting
    @Published var statusText: String = "Verbinde…"

    var onEnvelope: ((Envelope) -> Void)?
    var onLog: ((String, LogKind) -> Void)?

    private var mqtt: CocoaMQTT?
    private var ownTopic: String?

    func connect(ownBoxPubHex: String) {
        ownTopic = "cipherwire-demo-v1/" + ownBoxPubHex
        let clientID = "cipherwire-ios-" + String(UUID().uuidString.prefix(8))
        let client = CocoaMQTT(clientID: clientID, host: "test.mosquitto.org", port: 8883)
        client.enableSSL = true
        client.autoReconnect = true
        client.delegate = self
        mqtt = client
        client.connect()
    }

    func publish(topic: String, envelope: Envelope) {
        guard let data = try? JSONEncoder().encode(envelope),
              let json = String(data: data, encoding: .utf8) else {
            onLog?("✗ Envelope konnte nicht serialisiert werden", .fail)
            return
        }
        mqtt?.publish(topic, withString: json, qos: .qos1)
    }

    // MARK: - CocoaMQTTDelegate

    func mqtt(_ mqtt: CocoaMQTT, didConnectAck ack: CocoaMQTTConnAck) {
        guard ack == .accept else {
            DispatchQueue.main.async {
                self.status = .error
                self.statusText = "Verbindung abgelehnt (\(ack))"
            }
            return
        }
        if let topic = ownTopic {
            mqtt.subscribe(topic, qos: .qos1)
        }
        DispatchQueue.main.async {
            self.status = .live
            self.statusText = "Verbunden (öffentliches Test-Relay)"
        }
        onLog?("✓ Transport verbunden", .ok)
    }

    func mqtt(_ mqtt: CocoaMQTT, didReceiveMessage message: CocoaMQTTMessage, id: UInt16) {
        guard let json = message.string, let data = json.data(using: .utf8) else { return }
        guard let envelope = try? JSONDecoder().decode(Envelope.self, from: data) else { return }
        onEnvelope?(envelope)
    }

    func mqttDidDisconnect(_ mqtt: CocoaMQTT, withError err: Error?) {
        DispatchQueue.main.async {
            self.status = .warn
            self.statusText = err != nil ? "Getrennt: \(err!.localizedDescription)" : "Getrennt"
        }
    }

    func mqtt(_ mqtt: CocoaMQTT, didPublishMessage message: CocoaMQTTMessage, id: UInt16) {}
    func mqtt(_ mqtt: CocoaMQTT, didPublishAck id: UInt16) {}
    func mqtt(_ mqtt: CocoaMQTT, didSubscribeTopics success: NSDictionary, failed: [String]) {}
    func mqtt(_ mqtt: CocoaMQTT, didUnsubscribeTopics topics: [String]) {}
    func mqttDidPing(_ mqtt: CocoaMQTT) {}
    func mqttDidReceivePong(_ mqtt: CocoaMQTT) {}
    func mqtt(_ mqtt: CocoaMQTT, didStateChangeTo state: CocoaMQTTConnState) {}
}
