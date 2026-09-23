//! Skizze eines "blinden" Relay-Servers.
//!
//! Der Server kennt ausschliesslich anonyme Public-Key-IDs -- niemals
//! Telefonnummern, E-Mail-Adressen oder Benutzernamen. Er transportiert nur
//! bereits Ende-zu-Ende-verschluesselte Ciphertext-Blobs, deren Inhalt er
//! nicht entschluesseln kann, und haelt zu keinem Zeitpunkt mehr Metadaten
//! im Speicher als fuer die unmittelbare Zustellung noetig.
//!
//! Referenz-/Lehrcode fuer die Architektur-Diskussion, kein auditierter
//! Produktionsserver. Insbesondere fehlen hier: Persistenz-Layer fuer
//! Public-Key-Registrierungen (die duerfen dauerhaft, aber ausschliesslich
//! als Public Key + zufaellige ID gespeichert werden), TLS-Terminierung
//! (gehoert vor den Prozess, z. B. per Reverse-Proxy) und Rate-Limiting.

use axum::{
    extract::{
        ws::{Message, WebSocket, WebSocketUpgrade},
        Path, State,
    },
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use base64::{engine::general_purpose::STANDARD as B64, Engine};
use dashmap::DashMap;
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use rand::RngCore;
use serde::{Deserialize, Serialize};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::mpsc;
use zeroize::Zeroizing;

/// Die anonyme Identitaet eines Nutzers: nur ein zufaelliger, fuer sich
/// bedeutungsloser String. Es gibt keine Verbindung zu einer echten Person
/// auf Server-Seite -- diese Zuordnung existiert (falls ueberhaupt) nur
/// lokal auf den Geraeten der Kontakte (siehe db/schema.sql).
type AnonId = String;

#[derive(Clone)]
struct AppState {
    /// Dauerhaft (verschluesselt-at-rest) gespeicherte Public Keys der
    /// registrierten IDs. Das ist die EINZIGE Information, die der Server
    /// laengerfristig haelt -- kein Name, keine Telefonnummer, keine E-Mail.
    identities: Arc<DashMap<AnonId, VerifyingKey>>,

    /// Offene Challenges fuer die Login-Handshakes. TTL-begrenzt, siehe
    /// `cleanup_expired_challenges`.
    pending_challenges: Arc<DashMap<AnonId, (Vec<u8>, Instant)>>,

    /// Sende-Kanaele fuer aktuell verbundene (online) Clients. Nur solange
    /// der Websocket offen ist -- keine Historie, kein Log.
    online: Arc<DashMap<AnonId, mpsc::Sender<Vec<u8>>>>,

    /// Kurzfristiger Offline-Puffer fuer Nachrichten an nicht verbundene
    /// Empfaenger. Jeder Eintrag wird nach erfolgreicher Zustellung SOFORT
    /// entfernt und aktiv ueberschrieben (siehe `Zeroizing`).
    offline_queue: Arc<DashMap<AnonId, Vec<QueuedMessage>>>,
}

struct QueuedMessage {
    /// Der bereits Ende-zu-Ende-verschluesselte Payload. `Zeroizing` sorgt
    /// dafuer, dass der Speicher beim Drop mit `volatile`-Schreibzugriffen
    /// ueberschrieben wird -- der Compiler darf das NICHT als toten Code
    /// wegoptimieren (anders als bei einem simplen `Vec::clear()`).
    ciphertext: Zeroizing<Vec<u8>>,
    sender_id: AnonId,
    queued_at: Instant,
}

const OFFLINE_MESSAGE_TTL: Duration = Duration::from_secs(60 * 60 * 24 * 3); // 3 Tage
const CHALLENGE_TTL: Duration = Duration::from_secs(60);

// ---------------------------------------------------------------------
// 1. Registrierung: Client meldet NUR seinen Public Key an.
// ---------------------------------------------------------------------

#[derive(Deserialize)]
struct RegisterRequest {
    public_key_b64: String, // Ed25519 Public Key, Base64
}

#[derive(Serialize)]
struct RegisterResponse {
    anon_id: AnonId,
}

async fn register(
    State(state): State<AppState>,
    Json(req): Json<RegisterRequest>,
) -> impl IntoResponse {
    let key_bytes = match B64.decode(&req.public_key_b64) {
        Ok(b) => b,
        Err(_) => return Json(RegisterResponse { anon_id: String::new() }),
    };
    let verifying_key = match VerifyingKey::from_bytes(key_bytes.as_slice().try_into().unwrap_or(&[0u8; 32])) {
        Ok(vk) => vk,
        Err(_) => return Json(RegisterResponse { anon_id: String::new() }),
    };

    // Zufaellige ID -- keinerlei Bezug zu Telefonnummer/E-Mail/Klarname.
    let mut id_bytes = [0u8; 12];
    rand::thread_rng().fill_bytes(&mut id_bytes);
    let anon_id = B64.encode(id_bytes);

    state.identities.insert(anon_id.clone(), verifying_key);
    Json(RegisterResponse { anon_id })
}

// ---------------------------------------------------------------------
// 2. Authentifizierung: Public-Key-Challenge-Response statt Passwort.
//    Der Server haelt zu keinem Zeitpunkt ein Geheimnis des Nutzers.
// ---------------------------------------------------------------------

#[derive(Serialize)]
struct Challenge {
    nonce_b64: String,
}

async fn request_challenge(
    State(state): State<AppState>,
    Path(anon_id): Path<AnonId>,
) -> impl IntoResponse {
    let mut nonce = vec![0u8; 32];
    rand::thread_rng().fill_bytes(&mut nonce);

    state
        .pending_challenges
        .insert(anon_id, (nonce.clone(), Instant::now()));

    Json(Challenge { nonce_b64: B64.encode(nonce) })
}

#[derive(Deserialize)]
struct ChallengeResponse {
    signature_b64: String,
}

/// Prueft, ob die vom Client zurueckgesendete Signatur zur zuvor
/// ausgegebenen Challenge und zum registrierten Public Key passt.
/// Erfolgreiche Verifikation = Login, ohne dass jemals ein Passwort-Hash
/// oder aehnliches Geheimnis server-seitig existiert hat.
async fn verify_challenge(
    State(state): State<AppState>,
    Path(anon_id): Path<AnonId>,
    Json(resp): Json<ChallengeResponse>,
) -> impl IntoResponse {
    let Some((_, (nonce, issued_at))) = state.pending_challenges.remove(&anon_id) else {
        return axum::http::StatusCode::UNAUTHORIZED;
    };
    if issued_at.elapsed() > CHALLENGE_TTL {
        return axum::http::StatusCode::UNAUTHORIZED;
    }

    let Some(verifying_key) = state.identities.get(&anon_id) else {
        return axum::http::StatusCode::UNAUTHORIZED;
    };

    let Ok(sig_bytes) = B64.decode(&resp.signature_b64) else {
        return axum::http::StatusCode::UNAUTHORIZED;
    };
    let Ok(signature) = Signature::from_slice(&sig_bytes) else {
        return axum::http::StatusCode::UNAUTHORIZED;
    };

    match verifying_key.verify(&nonce, &signature) {
        Ok(()) => axum::http::StatusCode::OK,
        Err(_) => axum::http::StatusCode::UNAUTHORIZED,
    }
}

// ---------------------------------------------------------------------
// 3. Websocket-Verbindung: Live-Zustellung, keinerlei Persistenz.
//    Bewusst KEINE Middleware, die die Remote-IP oder Verbindungszeit
//    irgendwo protokolliert oder speichert (vgl. README.md Abschnitt 3.2).
// ---------------------------------------------------------------------

async fn ws_handler(
    ws: WebSocketUpgrade,
    Path(anon_id): Path<AnonId>,
    State(state): State<AppState>,
) -> impl IntoResponse {
    ws.on_upgrade(move |socket| handle_socket(socket, anon_id, state))
}

async fn handle_socket(mut socket: WebSocket, anon_id: AnonId, state: AppState) {
    let (tx, mut rx) = mpsc::channel::<Vec<u8>>(32);
    state.online.insert(anon_id.clone(), tx);

    // Beim Verbindungsaufbau gepufferte Offline-Nachrichten sofort
    // ausliefern und aus dem Puffer entfernen.
    if let Some((_, queued)) = state.offline_queue.remove(&anon_id) {
        for msg in queued {
            let _ = socket.send(Message::Binary(msg.ciphertext.to_vec())).await;
            // `msg` faellt hier aus dem Scope -> Zeroizing ueberschreibt
            // den Ciphertext-Puffer aktiv, bevor der Speicher freigegeben wird.
        }
    }

    loop {
        tokio::select! {
            // Nachricht fuer diesen Client von einem anderen Handler (siehe relay_message).
            Some(payload) = rx.recv() => {
                if socket.send(Message::Binary(payload)).await.is_err() {
                    break;
                }
            }
            // Nachricht/Ereignis vom Client selbst (z. B. Zustellbestaetigung).
            frame = socket.recv() => {
                match frame {
                    Some(Ok(_)) => { /* z. B. ACK verarbeiten, hier ausgelassen */ }
                    _ => break,
                }
            }
        }
    }

    // Verbindung beendet: Eintrag sofort entfernen, kein Nachhalten von
    // "zuletzt online um ..." oder aehnlichen Metadaten.
    state.online.remove(&anon_id);
}

// ---------------------------------------------------------------------
// 4. Nachrichten-Relay: online -> direkte Zustellung, offline -> kurzer
//    TTL-Puffer, danach hartes, aktives Loeschen.
// ---------------------------------------------------------------------

#[derive(Deserialize)]
struct RelayRequest {
    recipient_id: AnonId,
    ciphertext_b64: String, // bereits Ende-zu-Ende-verschluesselt durch den Client
}

async fn relay_message(
    State(state): State<AppState>,
    Path(sender_id): Path<AnonId>,
    Json(req): Json<RelayRequest>,
) -> impl IntoResponse {
    let Ok(ciphertext) = B64.decode(&req.ciphertext_b64) else {
        return axum::http::StatusCode::BAD_REQUEST;
    };

    if let Some(sender) = state.online.get(&req.recipient_id) {
        // Direkt zustellen -- der Server haelt den Inhalt nur so lange im
        // Speicher, wie der `send`-Aufruf laeuft, danach ist die einzige
        // Referenz weg.
        let _ = sender.send(ciphertext).await;
        return axum::http::StatusCode::OK;
    }

    // Empfaenger offline: kurzfristig puffern. Kein Klartext-Log, keine
    // dauerhafte Speicherung -- nur der verschluesselte Blob, TTL-begrenzt.
    state
        .offline_queue
        .entry(req.recipient_id)
        .or_default()
        .push(QueuedMessage {
            ciphertext: Zeroizing::new(ciphertext),
            sender_id,
            queued_at: Instant::now(),
        });

    axum::http::StatusCode::ACCEPTED
}

/// Periodischer Sweep: entfernt und ueberschreibt aktiv alle
/// Offline-Nachrichten, deren TTL abgelaufen ist. Wird als eigener
/// Tokio-Task im Hintergrund betrieben (siehe `main`).
async fn cleanup_expired_messages(state: AppState) {
    let mut interval = tokio::time::interval(Duration::from_secs(60));
    loop {
        interval.tick().await;
        for mut entry in state.offline_queue.iter_mut() {
            entry.value_mut().retain(|msg| {
                let expired = msg.queued_at.elapsed() > OFFLINE_MESSAGE_TTL;
                // `msg` wird bei `retain` verworfen, sobald `false`
                // zurueckgegeben wird -> Zeroizing greift beim Drop.
                !expired
            });
        }
    }
}

async fn cleanup_expired_challenges(state: AppState) {
    let mut interval = tokio::time::interval(Duration::from_secs(30));
    loop {
        interval.tick().await;
        state
            .pending_challenges
            .retain(|_, (_, issued_at)| issued_at.elapsed() <= CHALLENGE_TTL);
    }
}

#[tokio::main]
async fn main() {
    // Hinweis fuer den Betrieb (nicht Teil dieses Sketches, siehe README.md):
    //   - RLIMIT_CORE=0 setzen, damit ein Absturz keinen Speicherauszug
    //     mit Ciphertext/Schluesselmaterial auf Platte schreibt.
    //   - Prozess mit mlockall() ausstatten, damit sensible Puffer nicht
    //     in die Swap-Partition ausgelagert werden.
    //   - Reverse-Proxy davor mit `access_log off;` (nginx) oder
    //     gleichwertig, damit keine IP-Adressen persistiert werden.

    let state = AppState {
        identities: Arc::new(DashMap::new()),
        pending_challenges: Arc::new(DashMap::new()),
        online: Arc::new(DashMap::new()),
        offline_queue: Arc::new(DashMap::new()),
    };

    tokio::spawn(cleanup_expired_messages(state.clone()));
    tokio::spawn(cleanup_expired_challenges(state.clone()));

    let app = Router::new()
        .route("/register", post(register))
        .route("/challenge/:anon_id", get(request_challenge))
        .route("/challenge/:anon_id/verify", post(verify_challenge))
        .route("/relay/:sender_id", post(relay_message))
        .route("/ws/:anon_id", get(ws_handler))
        .with_state(state);

    let listener = tokio::net::TcpListener::bind("127.0.0.1:8443").await.unwrap();
    axum::serve(listener, app).await.unwrap();
}
