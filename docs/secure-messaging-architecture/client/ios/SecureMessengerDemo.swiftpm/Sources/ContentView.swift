//
//  ContentView.swift
//
//  UI-Spiegel der Web-Demo (client/web/index.html): eigene Identität,
//  Kontakt per ID hinzufügen, echter Chat über MQTT (siehe
//  ../../../PROTOCOL.md), Gegenproben im Tech-Log.
//

import SwiftUI

struct ContentView: View {
    @StateObject private var model = AppModel()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    header
                    identityCard
                    if model.contact == nil {
                        addContactCard
                    } else {
                        chatCard
                    }
                    techLogSection
                }
                .padding()
            }
            .navigationTitle("Cipher Wire")
        }
    }

    private var header: some View {
        HStack(spacing: 6) {
            Circle()
                .fill(statusColor)
                .frame(width: 8, height: 8)
            Text(model.connectionStatusText)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private var statusColor: Color {
        switch model.connectionStatus {
        case .live: return .green
        case .warn, .connecting: return .yellow
        case .error: return .red
        }
    }

    private var identityCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("MEINE IDENTITÄT").font(.caption.bold()).foregroundStyle(.secondary)
            Text(model.me.idString)
                .font(.system(.caption, design: .monospaced))
                .textSelection(.enabled)
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.secondary.opacity(0.12), in: RoundedRectangle(cornerRadius: 8))
            Button {
                UIPasteboard.general.string = model.me.idString
            } label: {
                Label("ID kopieren", systemImage: "doc.on.doc")
            }
            .buttonStyle(.bordered)
        }
        .padding()
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 14))
    }

    private var addContactCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("KONTAKT HINZUFÜGEN").font(.caption.bold()).foregroundStyle(.secondary)
            Text("ID vom anderen Gerät außerhalb dieses Kanals austauschen (persönlich/QR) — sonst ist eine Man-in-the-Middle-Zuordnung nicht ausgeschlossen.")
                .font(.caption)
                .foregroundStyle(.secondary)
            TextField("boxPubHex.signPubHex", text: $model.contactInputText)
                .font(.system(.footnote, design: .monospaced))
                .textFieldStyle(.roundedBorder)
                .autocorrectionDisabled()
                .textInputAutocapitalization(.never)
            Button("Hinzufügen") { model.addContact() }
                .buttonStyle(.borderedProminent)
        }
        .padding()
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 14))
    }

    private var chatCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(model.contact.map { String($0.boxPublicKey.hexString.prefix(12)) + "…" } ?? "")
                    .font(.subheadline.bold())
                Spacer()
                Button("Entfernen") { model.removeContact() }
                    .font(.caption)
            }

            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 6) {
                        if model.messages.isEmpty {
                            Text("Noch keine Nachrichten.")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .frame(maxWidth: .infinity, alignment: .center)
                        }
                        ForEach(model.messages) { m in
                            HStack {
                                if m.mine { Spacer() }
                                Text(m.text)
                                    .padding(8)
                                    .background(
                                        (m.mine ? Color.green : Color.orange).opacity(0.18),
                                        in: RoundedRectangle(cornerRadius: 10)
                                    )
                                if !m.mine { Spacer() }
                            }
                            .id(m.id)
                        }
                    }
                }
                .frame(maxHeight: 260)
                .onChange(of: model.messages.count) { _, _ in
                    if let last = model.messages.last {
                        withAnimation { proxy.scrollTo(last.id) }
                    }
                }
            }

            HStack {
                TextField("Nachricht…", text: $model.sendText)
                    .textFieldStyle(.roundedBorder)
                    .onSubmit { model.send() }
                Button("Senden") { model.send() }
                    .buttonStyle(.borderedProminent)
            }
        }
        .padding()
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 14))
    }

    private var techLogSection: some View {
        DisclosureGroup("Technisches Log & Gegenproben") {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Button("Manipulierten Ciphertext testen") { model.runTamperTest() }
                    Button("Gefälschte Signatur testen") { model.runForgedSignatureTest() }
                }
                .buttonStyle(.bordered)
                .font(.caption)

                Button("Log leeren") { model.clearLog() }
                    .buttonStyle(.bordered)
                    .font(.caption)

                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 2) {
                        ForEach(model.techLog) { entry in
                            Text(entry.text)
                                .font(.system(.caption2, design: .monospaced))
                                .foregroundStyle(color(for: entry.kind))
                                .frame(maxWidth: .infinity, alignment: .leading)
                        }
                    }
                }
                .frame(maxHeight: 200)
            }
            .padding(.top, 8)
        }
        .padding()
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 14))
    }

    private func color(for kind: LogKind) -> Color {
        switch kind {
        case .ok: return .green
        case .fail: return .red
        case .warn: return .yellow
        case .info: return .secondary
        }
    }
}
