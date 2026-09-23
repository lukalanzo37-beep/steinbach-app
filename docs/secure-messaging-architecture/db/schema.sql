-- schema.sql
--
-- Lokales SQLite/Room-Schema fuer die Messaging-App. Die gesamte
-- Datenbankdatei wird transparent per SQLCipher (AES-256, Seitenebene)
-- verschluesselt -- siehe db/android/SecureMessengerDatabase.kt fuer die
-- Passphrase-Ableitung via Envelope Encryption.
--
-- Wichtig: Server-seitige Nachrichten-IDs werden NICHT als Primaerschluessel
-- uebernommen, sondern lokal neu (UUID) vergeben. So laesst sich aus einer
-- kompromittierten lokalen DB keine direkte Zuordnung zu Server-Datensaetzen
-- herstellen.

PRAGMA foreign_keys = ON;

-- Kontakte: nur die anonyme ID + Public Key + lokal vergebener Spitzname.
-- Keine Telefonnummer, keine E-Mail-Adresse.
CREATE TABLE contacts (
    anon_id             TEXT PRIMARY KEY,   -- vom Server vergebene anonyme ID
    public_key          BLOB NOT NULL,      -- Curve25519 Public Key, 32 Byte
    nickname            TEXT,               -- rein lokal, nur auf diesem Geraet sichtbar
    verification_level  INTEGER NOT NULL DEFAULT 0,
        -- 0 = unverifiziert (nur ueber Server-Lookup erhalten)
        -- 1 = per QR-Code persoenlich gescannt
        -- 2 = ueber Vertrauenskette bestaetigt (von einem bereits verifizierten Kontakt)
    added_at            INTEGER NOT NULL    -- Unix-Timestamp, lokal
);

CREATE TABLE conversations (
    id                  TEXT PRIMARY KEY,   -- lokale UUID
    contact_anon_id     TEXT NOT NULL REFERENCES contacts(anon_id) ON DELETE CASCADE,
    last_message_at     INTEGER,
    is_archived         INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE messages (
    id                  TEXT PRIMARY KEY,   -- lokale UUID, NICHT die Server-Message-ID
    conversation_id     TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    direction           INTEGER NOT NULL,   -- 0 = eingehend, 1 = ausgehend
    body                TEXT,               -- Klartext NACH lokaler Entschluesselung
                                             -- (die Datei selbst ist per SQLCipher verschluesselt)
    sent_at             INTEGER,
    received_at         INTEGER,
    delivery_state      INTEGER NOT NULL DEFAULT 0,
        -- 0 = pending, 1 = sent, 2 = delivered, 3 = read, 4 = failed
    sender_public_key   BLOB NOT NULL       -- zur lokalen Nachpruefung der Authentizitaet
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id, sent_at);
CREATE INDEX idx_conversations_contact ON conversations(contact_anon_id);
