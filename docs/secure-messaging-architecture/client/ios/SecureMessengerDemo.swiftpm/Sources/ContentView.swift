//
//  ContentView.swift
//
//  Zeigt denselben Ablauf wie docs/secure-messaging-architecture/demo_e2ee.py:
//  Alice (dieses Gerät) verschlüsselt eine Nachricht für Bob, Bob
//  entschlüsselt sie, danach zwei Gegenproben (Manipulation, falscher
//  Absender). Nutzt echte NaCl crypto_box-Aufrufe über Swift-Sodium --
//  keine Mock-/Fake-Kryptografie.
//

import SwiftUI

struct DemoLogLine: Identifiable {
    let id = UUID()
    let text: String
    let isHeading: Bool
}

@MainActor
final class DemoViewModel: ObservableObject {
    @Published var log: [DemoLogLine] = []
    @Published var isRunning = false

    private let crypto = DemoCrypto()

    private func add(_ text: String, heading: Bool = false) {
        log.append(DemoLogLine(text: text, isHeading: heading))
    }

    private func hexPreview(_ data: Data, count: Int = 16) -> String {
        data.prefix(count).map { String(format: "%02x", $0) }.joined() + "…"
    }

    func runDemo() {
        log.removeAll()
        isRunning = true
        defer { isRunning = false }

        do {
            add("1. Schlüsselerzeugung (je Gerät lokal)", heading: true)
            let alice = try crypto.generateIdentity()
            let bob = try crypto.generateIdentity()
            add("Alice Public Key: \(hexPreview(alice.publicKey))")
            add("Bob   Public Key: \(hexPreview(bob.publicKey))")

            add("2. Alice verschlüsselt eine Nachricht für Bob", heading: true)
            let message = "Hallo Bob, dieser Text ist Ende-zu-Ende verschlüsselt."
            let envelope = try crypto.encrypt(
                plaintext: message,
                recipientPublicKey: bob.publicKey,
                senderSecretKey: alice.secretKey
            )
            add("Klartext:   \(message)")
            add("Nonce:      \(envelope.nonce.map { String(format: "%02x", $0) }.joined())")
            add("Ciphertext: \(hexPreview(envelope.ciphertext, count: 32))")

            add("3. Bob entschlüsselt und verifiziert", heading: true)
            let decrypted = try crypto.decrypt(
                envelope: envelope,
                senderPublicKey: alice.publicKey,
                recipientSecretKey: bob.secretKey
            )
            add("Entschlüsselt: \(decrypted)")
            add(decrypted == message ? "✅ Stimmt mit Original überein" : "❌ Unterschied!")

            add("4. Gegenprobe: manipulierter Ciphertext", heading: true)
            var tampered = envelope.ciphertext
            tampered[tampered.startIndex] ^= 0xFF
            do {
                _ = try crypto.decrypt(
                    envelope: DemoEnvelope(ciphertext: tampered, nonce: envelope.nonce),
                    senderPublicKey: alice.publicKey,
                    recipientSecretKey: bob.secretKey
                )
                add("❌ Fehler: Manipulation hätte erkannt werden müssen!")
            } catch {
                add("✅ Erwartetes Verhalten: \(error.localizedDescription)")
            }

            add("5. Gegenprobe: falscher Absender", heading: true)
            let mallory = try crypto.generateIdentity()
            do {
                _ = try crypto.decrypt(
                    envelope: envelope,
                    senderPublicKey: mallory.publicKey,
                    recipientSecretKey: bob.secretKey
                )
                add("❌ Fehler: falscher Absender hätte erkannt werden müssen!")
            } catch {
                add("✅ Erwartetes Verhalten: \(error.localizedDescription)")
            }
        } catch {
            add("Fehler: \(error.localizedDescription)")
        }
    }
}

struct ContentView: View {
    @StateObject private var viewModel = DemoViewModel()

    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                Text("NaCl crypto_box Demo (iOS)")
                    .font(.headline)

                Button(action: viewModel.runDemo) {
                    Label("Demo starten", systemImage: "lock.shield")
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .disabled(viewModel.isRunning)
                .padding(.horizontal)

                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 4) {
                        ForEach(viewModel.log) { line in
                            Text(line.text)
                                .font(line.isHeading ? .subheadline.bold() : .system(.footnote, design: .monospaced))
                                .foregroundStyle(line.isHeading ? .primary : .secondary)
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    .padding(.horizontal)
                }
            }
            .padding(.top)
            .navigationTitle("Secure Messenger Demo")
        }
    }
}
