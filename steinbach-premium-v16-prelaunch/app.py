from __future__ import annotations

import json
import os
import re
import secrets
import smtplib
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Request, Response, HTTPException, UploadFile, File, Form
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from db import connect, init_db, seed_demo, now_iso, DB_PATH
from security import (
    verify_password, hash_password, new_token, token_hash, constant_equals,
    generate_totp_secret, verify_totp, otpauth_uri,
)

try:
    from pywebpush import webpush, WebPushException
except Exception:  # optional at source level; required in requirements.txt for pilot
    webpush = None
    class WebPushException(Exception):
        response = None

ROOT = Path(__file__).resolve().parent
STATIC = ROOT / "static"
UPLOADS = ROOT / "uploads"
UPLOADS.mkdir(exist_ok=True)
COOKIE_NAME = "steinbach_session"
COOKIE_SECURE = os.getenv("STEINBACH_COOKIE_SECURE", "0") == "1"
SESSION_HOURS = int(os.getenv("STEINBACH_SESSION_HOURS", "12"))
MAX_UPLOAD_BYTES = 8 * 1024 * 1024
ALLOWED_MIME = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp", "application/pdf": ".pdf"}
LOGIN_ATTEMPTS = defaultdict(deque)
LOGIN_WINDOW_SECONDS = 600
LOGIN_MAX_ATTEMPTS = 10
TICKET_STATUSES = {"Eingegangen","Übernommen","Termin geplant","In Arbeit","Rückfrage","Erledigt"}
URGENCIES = {"Normal","Zeitnah","Dringend","Notfall"}
APPOINTMENT_STATUSES = {"Angefragt","Bestätigt","Verschoben","Abgesagt","Erledigt"}
PUBLIC_BASE_URL = os.getenv("STEINBACH_PUBLIC_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
DEV_SHOW_TOKENS = os.getenv("STEINBACH_DEV_SHOW_TOKENS", "1" if os.getenv("STEINBACH_DEMO_SEED", "0") == "1" else "0") == "1"
VAPID_PRIVATE_KEY = os.getenv("STEINBACH_VAPID_PRIVATE_KEY", "")
VAPID_PUBLIC_KEY = os.getenv("STEINBACH_VAPID_PUBLIC_KEY", "")
VAPID_SUBJECT = os.getenv("STEINBACH_VAPID_SUBJECT", "mailto:info@immobilienservice-steinbach.de")

@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db(); seed_demo()
    yield

app = FastAPI(title="Immobilienservice Steinbach Pre-Launch API", version="16.0-prelaunch", lifespan=lifespan, docs_url=None if os.getenv("STEINBACH_PRODUCTION","0")=="1" else "/docs", redoc_url=None)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

# ---------- Models ----------
class LoginIn(BaseModel):
    email: str
    password: str
    mfa_code: str = ""

class PasswordResetRequestIn(BaseModel):
    email: str

class PasswordResetIn(BaseModel):
    token: str
    new_password: str = Field(min_length=10, max_length=200)

class InviteIn(BaseModel):
    email: str
    role: str
    name: str = Field(min_length=2, max_length=120)
    phone: str = Field(default="", max_length=50)

class AcceptInviteIn(BaseModel):
    token: str
    new_password: str = Field(min_length=10, max_length=200)

class MfaCodeIn(BaseModel):
    code: str = Field(min_length=6, max_length=12)

class ObjectIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    type: str = Field(default="", max_length=100)
    address: str = Field(default="", max_length=180)
    city: str = Field(default="", max_length=100)
    postal_code: str = Field(default="", max_length=12)

class TicketIn(BaseModel):
    object_id: Optional[int] = None
    category: str = Field(min_length=2, max_length=100)
    urgency: str
    location: str = Field(default="", max_length=160)
    description: str = Field(min_length=5, max_length=5000)
    preferred_contact: str = Field(default="Portal", max_length=30)
    phone: str = Field(default="", max_length=50)

class TicketPatch(BaseModel):
    status: Optional[str] = None
    assignee_user_id: Optional[int] = None
    appointment_date: Optional[str] = None
    appointment_time: Optional[str] = None
    internal_note: Optional[str] = Field(default=None, max_length=5000)
    customer_message: Optional[str] = Field(default=None, max_length=5000)

class MessageIn(BaseModel):
    ticket_id: Optional[int] = None
    customer_id: Optional[int] = None
    body: str = Field(min_length=1, max_length=5000)

class ServiceRequestIn(BaseModel):
    object_id: Optional[int] = None
    service_code: str = Field(min_length=2, max_length=80)
    action: str
    note: str = Field(default="", max_length=1500)

class ReferralIn(BaseModel):
    referred_name: str = Field(min_length=2, max_length=120)
    referred_contact: str = Field(default="", max_length=180)
    reward_type: str
    note: str = Field(default="", max_length=1500)

class ResolveIn(BaseModel):
    status: str
    reward_value_cents: Optional[int] = None

class AppointmentIn(BaseModel):
    object_id: Optional[int] = None
    ticket_id: Optional[int] = None
    employee_id: Optional[int] = None
    title: str = Field(min_length=2, max_length=160)
    appointment_date: str
    time_start: str = Field(default="", max_length=10)
    time_end: str = Field(default="", max_length=10)
    note: str = Field(default="", max_length=2000)

class AppointmentPatch(BaseModel):
    employee_id: Optional[int] = None
    title: Optional[str] = Field(default=None, min_length=2, max_length=160)
    appointment_date: Optional[str] = None
    time_start: Optional[str] = Field(default=None, max_length=10)
    time_end: Optional[str] = Field(default=None, max_length=10)
    status: Optional[str] = None
    note: Optional[str] = Field(default=None, max_length=2000)

class PushSubscriptionIn(BaseModel):
    endpoint: str = Field(min_length=10, max_length=3000)
    p256dh: str = Field(min_length=10, max_length=1000)
    auth: str = Field(min_length=4, max_length=1000)

class AdminTicketIn(TicketIn):
    customer_id: int
    assignee_user_id: Optional[int] = None

# ---------- Helpers ----------
def utcnow() -> datetime:
    return datetime.now(timezone.utc)

def parse_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)

def rowdict(row) -> dict[str, Any]:
    return dict(row) if row else {}

def audit(con, user_id: Optional[int], action: str, entity_type: str = "", entity_id: str = "", metadata: Any = None):
    con.execute(
        "INSERT INTO audit_log(user_id,action,entity_type,entity_id,metadata,created_at) VALUES(?,?,?,?,?,?)",
        (user_id, action, entity_type, entity_id, json.dumps(metadata or {}, ensure_ascii=False), now_iso()),
    )

def notify(con, user_id: int, title: str, body: str, kind: str = "info"):
    con.execute("INSERT INTO notifications(user_id,title,body,kind,created_at) VALUES(?,?,?,?,?)", (user_id,title,body,kind,now_iso()))

def make_ticket_no(con) -> str:
    year = datetime.now().year
    prefix = f"ST-{year}-"
    row = con.execute("SELECT ticket_no FROM tickets WHERE ticket_no LIKE ? ORDER BY id DESC LIMIT 1", (prefix+"%",)).fetchone()
    seq = 1
    if row:
        try: seq = int(row["ticket_no"].rsplit("-",1)[1]) + 1
        except Exception: seq = 1
    return f"{prefix}{seq:05d}"

def current_session(request: Request, *, required: bool = True):
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        if required: raise HTTPException(401, "Nicht angemeldet")
        return None
    th = token_hash(token)
    with connect() as con:
        row = con.execute("""
            SELECT s.id session_id,s.csrf_token,s.expires_at,s.user_id,u.email,u.role,u.name,u.phone,u.active,u.mfa_enabled,u.email_verified
            FROM sessions s JOIN users u ON u.id=s.user_id WHERE s.token_hash=?
        """, (th,)).fetchone()
        if not row or not row["active"]:
            if required: raise HTTPException(401, "Sitzung ungültig")
            return None
        if parse_dt(row["expires_at"]) <= utcnow():
            con.execute("DELETE FROM sessions WHERE id=?", (row["session_id"],)); con.commit()
            if required: raise HTTPException(401, "Sitzung abgelaufen")
            return None
        con.execute("UPDATE sessions SET last_seen_at=? WHERE id=?", (now_iso(),row["session_id"])); con.commit()
        return rowdict(row)

def require_role(session: dict, *roles: str):
    if session["role"] not in roles:
        raise HTTPException(403, "Keine Berechtigung")

def require_csrf(request: Request, session: dict):
    supplied = request.headers.get("X-CSRF-Token", "")
    if not supplied or not constant_equals(supplied, session["csrf_token"]):
        raise HTTPException(403, "CSRF-Prüfung fehlgeschlagen")

def ticket_access_clause(session: dict):
    if session["role"] == "customer":
        return " WHERE t.customer_id=? ", [session["user_id"]]
    return " ", []

def serialize_ticket(con, row) -> dict[str, Any]:
    d = rowdict(row)
    hist = con.execute("SELECT event,created_at FROM ticket_history WHERE ticket_id=? ORDER BY id", (d["id"],)).fetchall()
    files = con.execute("SELECT id,original_name,mime_type,size_bytes,created_at FROM uploads WHERE ticket_id=? ORDER BY id", (d["id"],)).fetchall()
    d["history"] = [rowdict(x) for x in hist]
    d["files"] = [rowdict(x) for x in files]
    return d

def serialize_appointment(row) -> dict[str, Any]:
    return rowdict(row)

def login_rate_key(request: Request, email: str) -> str:
    ip = request.client.host if request.client else "unknown"
    return f"{ip}:{email.lower()}"

def check_login_rate(request: Request, email: str):
    key = login_rate_key(request, email)
    now = time.time()
    q = LOGIN_ATTEMPTS[key]
    while q and now - q[0] > LOGIN_WINDOW_SECONDS:
        q.popleft()
    if len(q) >= LOGIN_MAX_ATTEMPTS:
        raise HTTPException(429, "Zu viele Anmeldeversuche. Bitte später erneut versuchen.")
    return q

def valid_file_signature(mime: str, data: bytes) -> bool:
    if mime == "image/jpeg": return data.startswith(b"\xff\xd8\xff")
    if mime == "image/png": return data.startswith(b"\x89PNG\r\n\x1a\n")
    if mime == "image/webp": return len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP"
    if mime == "application/pdf": return data.startswith(b"%PDF-")
    return False

def staff_can_access_ticket(con, session: dict, ticket_row) -> bool:
    """Admins may access all tickets. Employees may access unassigned or their own tickets."""
    if session["role"] == "admin":
        return True
    if session["role"] == "employee":
        return ticket_row["assignee_user_id"] in (None, session["user_id"])
    return ticket_row["customer_id"] == session["user_id"]

def require_staff_ticket_access(con, session: dict, ticket_row):
    if session["role"] in {"employee", "admin"} and not staff_can_access_ticket(con, session, ticket_row):
        raise HTTPException(403, "Vorgang ist einem anderen Mitarbeiter zugewiesen")

def validate_customer_object(con, customer_id: int, object_id: Optional[int]):
    if object_id is None:
        return
    if not con.execute("SELECT 1 FROM objects WHERE id=? AND customer_id=? AND active=1", (object_id, customer_id)).fetchone():
        raise HTTPException(400, "Objekt nicht gefunden oder nicht aktiv")

def validate_date(s: str) -> str:
    try: datetime.strptime(s, "%Y-%m-%d")
    except Exception: raise HTTPException(400, "Ungültiges Datum")
    return s

def validate_time(s: str) -> str:
    if not s: return ""
    try: datetime.strptime(s, "%H:%M")
    except Exception: raise HTTPException(400, "Ungültige Uhrzeit")
    return s

def public_user(user) -> dict[str, Any]:
    return {"id":user["id"],"email":user["email"],"role":user["role"],"name":user["name"],"phone":user["phone"],"mfa_enabled":bool(user["mfa_enabled"]),"email_verified":bool(user["email_verified"])}

def queue_email(to_email: str, subject: str, body: str) -> int:
    with connect() as con:
        cur = con.execute("INSERT INTO email_outbox(to_email,subject,body,created_at) VALUES(?,?,?,?)", (to_email,subject,body,now_iso()))
        con.commit(); email_id = cur.lastrowid
    host = os.getenv("STEINBACH_SMTP_HOST", "")
    if not host:
        return email_id
    port = int(os.getenv("STEINBACH_SMTP_PORT", "587"))
    username = os.getenv("STEINBACH_SMTP_USER", "")
    password = os.getenv("STEINBACH_SMTP_PASSWORD", "")
    sender = os.getenv("STEINBACH_SMTP_FROM", "info@immobilienservice-steinbach.de")
    use_tls = os.getenv("STEINBACH_SMTP_TLS", "1") == "1"
    msg = EmailMessage(); msg["From"] = sender; msg["To"] = to_email; msg["Subject"] = subject; msg.set_content(body)
    try:
        with smtplib.SMTP(host, port, timeout=12) as smtp:
            if use_tls: smtp.starttls()
            if username: smtp.login(username, password)
            smtp.send_message(msg)
        with connect() as con:
            con.execute("UPDATE email_outbox SET status='sent',sent_at=? WHERE id=?", (now_iso(),email_id)); con.commit()
    except Exception as exc:
        with connect() as con:
            con.execute("UPDATE email_outbox SET status='error',error=? WHERE id=?", (str(exc)[:500],email_id)); con.commit()
    return email_id

def create_auth_token(con, user_id: int, purpose: str, minutes: int, created_by: Optional[int] = None) -> str:
    raw = new_token(32)
    expires = utcnow() + timedelta(minutes=minutes)
    con.execute("UPDATE auth_tokens SET used_at=? WHERE user_id=? AND purpose=? AND used_at IS NULL", (now_iso(),user_id,purpose))
    con.execute("INSERT INTO auth_tokens(user_id,purpose,token_hash,expires_at,created_by,created_at) VALUES(?,?,?,?,?,?)",
                (user_id,purpose,token_hash(raw),expires.isoformat(),created_by,now_iso()))
    return raw

def consume_auth_token(con, raw: str, purpose: str):
    row = con.execute("SELECT * FROM auth_tokens WHERE token_hash=? AND purpose=?", (token_hash(raw),purpose)).fetchone()
    if not row or row["used_at"] or parse_dt(row["expires_at"]) <= utcnow():
        raise HTTPException(400, "Link ist ungültig oder abgelaufen")
    con.execute("UPDATE auth_tokens SET used_at=? WHERE id=?", (now_iso(),row["id"]))
    return row

def push_enabled() -> bool:
    return bool(webpush and VAPID_PRIVATE_KEY and VAPID_PUBLIC_KEY)

def send_push_to_user(user_id: int, title: str, body: str, url: str = "/") -> int:
    if not push_enabled():
        return 0
    with connect() as con:
        subs = con.execute("SELECT * FROM push_subscriptions WHERE user_id=? AND disabled_at IS NULL", (user_id,)).fetchall()
    sent = 0
    for sub in subs:
        info = {"endpoint":sub["endpoint"], "keys":{"p256dh":sub["p256dh"],"auth":sub["auth"]}}
        payload = json.dumps({"title":title,"body":body,"url":url}, ensure_ascii=False)
        try:
            webpush(subscription_info=info, data=payload, vapid_private_key=VAPID_PRIVATE_KEY, vapid_claims={"sub":VAPID_SUBJECT})
            sent += 1
        except WebPushException as exc:
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status in (404,410):
                with connect() as con:
                    con.execute("UPDATE push_subscriptions SET disabled_at=?,updated_at=? WHERE id=?", (now_iso(),now_iso(),sub["id"])); con.commit()
        except Exception:
            pass
    return sent

def send_push_roles(roles: tuple[str,...], title: str, body: str, url: str = "/") -> int:
    if not push_enabled(): return 0
    qs = ",".join("?" for _ in roles)
    with connect() as con:
        ids = [r["id"] for r in con.execute(f"SELECT id FROM users WHERE active=1 AND role IN ({qs})", roles).fetchall()]
    return sum(send_push_to_user(uid,title,body,url) for uid in ids)

def upsert_ticket_appointment(con, ticket_id: int, actor_user_id: int):
    t = con.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,)).fetchone()
    if not t: return
    existing = con.execute("SELECT * FROM appointments WHERE ticket_id=? ORDER BY id DESC LIMIT 1", (ticket_id,)).fetchone()
    if not t["appointment_date"]:
        if existing and existing["status"] not in {"Abgesagt","Erledigt"}:
            con.execute("UPDATE appointments SET status='Abgesagt',updated_at=? WHERE id=?", (now_iso(),existing["id"]))
        return
    status = "Erledigt" if t["status"] == "Erledigt" else "Bestätigt"
    title = f"{t['category']} · {t['ticket_no']}"
    if existing:
        con.execute("""UPDATE appointments SET customer_id=?,object_id=?,employee_id=?,title=?,appointment_date=?,time_start=?,status=?,updated_at=? WHERE id=?""",
                    (t["customer_id"],t["object_id"],t["assignee_user_id"],title,t["appointment_date"],t["appointment_time"] or "",status,now_iso(),existing["id"]))
    else:
        con.execute("""INSERT INTO appointments(customer_id,object_id,ticket_id,employee_id,title,appointment_date,time_start,status,note,created_by,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (t["customer_id"],t["object_id"],ticket_id,t["assignee_user_id"],title,t["appointment_date"],t["appointment_time"] or "",status,"Termin aus Ticket",actor_user_id,now_iso(),now_iso()))

# ---------- Middleware / static ----------
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["X-Permitted-Cross-Domain-Policies"] = "none"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; img-src 'self' data: blob: https://www.immobilienservice-steinbach.de; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self' mailto: https://wa.me"
    if COOKIE_SECURE:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response

@app.get("/")
def root(): return FileResponse(STATIC / "index.html")
@app.get("/manifest.webmanifest")
def manifest(): return FileResponse(STATIC / "manifest.webmanifest")
@app.get("/sw.js")
def sw(): return FileResponse(STATIC / "sw.js", media_type="application/javascript", headers={"Service-Worker-Allowed":"/"})
@app.get("/robots.txt")
def robots(): return FileResponse(STATIC / "robots.txt")
@app.get("/sitemap.xml")
def sitemap(): return FileResponse(STATIC / "sitemap.xml")
@app.get("/config.js")
def config(): return FileResponse(STATIC / "config.js", media_type="application/javascript")

# ---------- Health ----------
@app.get("/api/health")
def health():
    ok = True
    try:
        with connect() as con: con.execute("SELECT 1").fetchone()
    except Exception: ok = False
    return {"ok":ok,"version":"16.0-prelaunch","database":str(DB_PATH.name),"push_configured":push_enabled(),"smtp_configured":bool(os.getenv("STEINBACH_SMTP_HOST","")),"secure_cookie":COOKIE_SECURE,"production":os.getenv("STEINBACH_PRODUCTION","0")=="1"}

@app.get("/api/readiness")
def readiness():
    """Launch gate: operational checks without exposing secrets."""
    production = os.getenv("STEINBACH_PRODUCTION","0") == "1"
    checks = {
        "database": True,
        "https_base_url": PUBLIC_BASE_URL.startswith("https://"),
        "secure_cookie": COOKIE_SECURE,
        "demo_seed_disabled": os.getenv("STEINBACH_DEMO_SEED","0") != "1",
        "dev_tokens_disabled": not DEV_SHOW_TOKENS,
        "smtp_configured": bool(os.getenv("STEINBACH_SMTP_HOST","")),
        "push_configured": push_enabled(),
    }
    try:
        with connect() as con:
            con.execute("SELECT 1").fetchone()
    except Exception:
        checks["database"] = False
    required = ["database"] if not production else ["database","https_base_url","secure_cookie","demo_seed_disabled","dev_tokens_disabled"]
    ready = all(checks[k] for k in required)
    return {"ready":ready,"production":production,"checks":checks,"required":required}

# ---------- Authentication ----------
@app.post("/api/auth/login")
def login(data: LoginIn, response: Response, request: Request):
    email = data.email.strip().lower()
    attempts = check_login_rate(request, email)
    with connect() as con:
        user = con.execute("SELECT * FROM users WHERE email=?", (email,)).fetchone()
        if not user or not user["active"] or not verify_password(data.password, user["password_hash"]):
            attempts.append(time.time()); audit(con, user["id"] if user else None, "login_failed", metadata={"email":email}); con.commit()
            raise HTTPException(401, "E-Mail oder Passwort falsch")
        if user["role"] == "admin" and user["mfa_enabled"]:
            if not data.mfa_code:
                audit(con,user["id"],"login_mfa_required"); con.commit(); raise HTTPException(428,"MFA-Code erforderlich")
            if not user["mfa_secret"] or not verify_totp(user["mfa_secret"], data.mfa_code):
                attempts.append(time.time()); audit(con,user["id"],"login_mfa_failed"); con.commit(); raise HTTPException(401,"MFA-Code ungültig")
        attempts.clear()
        raw = new_token(); csrf = new_token(18); expires = utcnow() + timedelta(hours=SESSION_HOURS)
        con.execute("DELETE FROM sessions WHERE expires_at<=?", (now_iso(),))
        con.execute("INSERT INTO sessions(user_id,token_hash,csrf_token,expires_at,created_at,last_seen_at) VALUES(?,?,?,?,?,?)", (user["id"],token_hash(raw),csrf,expires.isoformat(),now_iso(),now_iso()))
        audit(con,user["id"],"login_success"); con.commit()
    response.set_cookie(COOKIE_NAME, raw, httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=SESSION_HOURS*3600, path="/")
    return {"user":public_user(user),"csrf":csrf}

@app.post("/api/auth/logout")
def logout(request: Request, response: Response):
    session = current_session(request); require_csrf(request, session)
    token = request.cookies.get(COOKIE_NAME)
    with connect() as con:
        con.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash(token),)); audit(con,session["user_id"],"logout"); con.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok":True}

@app.get("/api/auth/me")
def me(request: Request):
    s = current_session(request)
    return {"user":{"id":s["user_id"],"email":s["email"],"role":s["role"],"name":s["name"],"phone":s["phone"],"mfa_enabled":bool(s["mfa_enabled"]),"email_verified":bool(s["email_verified"])},"csrf":s["csrf_token"]}

@app.post("/api/auth/request-password-reset")
def request_password_reset(data: PasswordResetRequestIn):
    email = data.email.strip().lower(); raw = None
    with connect() as con:
        user = con.execute("SELECT * FROM users WHERE email=? AND active=1", (email,)).fetchone()
        if user:
            raw = create_auth_token(con,user["id"],"password_reset",30)
            audit(con,user["id"],"password_reset_requested"); con.commit()
    result = {"ok":True,"message":"Falls ein aktives Konto existiert, wurde ein Reset-Link erstellt."}
    if raw:
        link = f"{PUBLIC_BASE_URL}/?reset_token={raw}"
        queue_email(email,"Passwort zurücksetzen – Immobilienservice Steinbach",f"Über diesen Link können Sie Ihr Passwort innerhalb von 30 Minuten zurücksetzen:\n\n{link}\n\nFalls Sie das nicht angefordert haben, ignorieren Sie diese Nachricht.")
        if DEV_SHOW_TOKENS: result.update({"dev_reset_token":raw,"dev_reset_link":link})
    return result

@app.post("/api/auth/reset-password")
def reset_password(data: PasswordResetIn):
    with connect() as con:
        tok = consume_auth_token(con,data.token,"password_reset")
        try: ph = hash_password(data.new_password)
        except ValueError: raise HTTPException(400,"Passwort muss mindestens 10 Zeichen lang sein")
        con.execute("UPDATE users SET password_hash=?,must_change_password=0 WHERE id=?", (ph,tok["user_id"]))
        con.execute("DELETE FROM sessions WHERE user_id=?", (tok["user_id"],))
        audit(con,tok["user_id"],"password_reset_completed"); con.commit()
    return {"ok":True}

@app.post("/api/admin/invitations")
def create_invitation(data: InviteIn, request: Request):
    s=current_session(request); require_csrf(request,s); require_role(s,"admin")
    if data.role not in {"customer","employee","admin"}: raise HTTPException(400,"Ungültige Rolle")
    email=data.email.strip().lower()
    with connect() as con:
        user=con.execute("SELECT * FROM users WHERE email=?",(email,)).fetchone()
        if user and user["active"]: raise HTTPException(409,"E-Mail ist bereits einem aktiven Konto zugeordnet")
        if user:
            uid=user["id"]; con.execute("UPDATE users SET name=?,phone=?,role=?,active=0 WHERE id=?",(data.name.strip(),data.phone.strip(),data.role,uid))
        else:
            placeholder=hash_password(new_token(24)); cur=con.execute("INSERT INTO users(email,password_hash,role,name,phone,active,email_verified,must_change_password,created_at) VALUES(?,?,?,?,?,0,0,1,?)",(email,placeholder,data.role,data.name.strip(),data.phone.strip(),now_iso())); uid=cur.lastrowid
        raw=create_auth_token(con,uid,"invite",72*60,s["user_id"]); audit(con,s["user_id"],"user_invited","user",str(uid),{"email":email,"role":data.role}); con.commit()
    link=f"{PUBLIC_BASE_URL}/?invite_token={raw}"
    queue_email(email,"Einladung zum Steinbach Portal",f"Sie wurden zum Steinbach Portal eingeladen. Der Link ist 72 Stunden gültig:\n\n{link}")
    out={"ok":True,"user_id":uid}
    if DEV_SHOW_TOKENS: out.update({"dev_invite_token":raw,"dev_invite_link":link})
    return out

@app.post("/api/auth/accept-invite")
def accept_invite(data: AcceptInviteIn):
    with connect() as con:
        tok=consume_auth_token(con,data.token,"invite")
        try: ph=hash_password(data.new_password)
        except ValueError: raise HTTPException(400,"Passwort muss mindestens 10 Zeichen lang sein")
        con.execute("UPDATE users SET password_hash=?,active=1,email_verified=1,must_change_password=0 WHERE id=?",(ph,tok["user_id"]))
        audit(con,tok["user_id"],"invite_accepted"); con.commit()
    return {"ok":True}

@app.get("/api/auth/mfa/status")
def mfa_status(request: Request):
    s=current_session(request); require_role(s,"admin")
    with connect() as con: u=con.execute("SELECT mfa_enabled,mfa_secret FROM users WHERE id=?",(s["user_id"],)).fetchone()
    return {"enabled":bool(u["mfa_enabled"]),"configured":bool(u["mfa_secret"])}

@app.post("/api/auth/mfa/setup")
def mfa_setup(request: Request):
    s=current_session(request); require_csrf(request,s); require_role(s,"admin")
    secret=generate_totp_secret()
    with connect() as con:
        con.execute("UPDATE users SET mfa_secret=?,mfa_enabled=0 WHERE id=?",(secret,s["user_id"])); audit(con,s["user_id"],"mfa_setup_started"); con.commit()
    return {"secret":secret,"otpauth_uri":otpauth_uri(secret,s["email"]),"message":"Secret in einer Authenticator-App hinzufügen und anschließend Code bestätigen."}

@app.post("/api/auth/mfa/confirm")
def mfa_confirm(data:MfaCodeIn, request:Request):
    s=current_session(request); require_csrf(request,s); require_role(s,"admin")
    with connect() as con:
        u=con.execute("SELECT mfa_secret FROM users WHERE id=?",(s["user_id"],)).fetchone()
        if not u or not u["mfa_secret"] or not verify_totp(u["mfa_secret"],data.code): raise HTTPException(400,"MFA-Code ungültig")
        con.execute("UPDATE users SET mfa_enabled=1 WHERE id=?",(s["user_id"],)); audit(con,s["user_id"],"mfa_enabled"); con.commit()
    return {"ok":True}

@app.delete("/api/auth/mfa")
def mfa_disable(data:MfaCodeIn, request:Request):
    s=current_session(request); require_csrf(request,s); require_role(s,"admin")
    with connect() as con:
        u=con.execute("SELECT mfa_secret,mfa_enabled FROM users WHERE id=?",(s["user_id"],)).fetchone()
        if u and u["mfa_enabled"] and (not u["mfa_secret"] or not verify_totp(u["mfa_secret"],data.code)): raise HTTPException(400,"MFA-Code ungültig")
        con.execute("UPDATE users SET mfa_secret=NULL,mfa_enabled=0 WHERE id=?",(s["user_id"],)); audit(con,s["user_id"],"mfa_disabled"); con.commit()
    return {"ok":True}

# ---------- Objects ----------
@app.get("/api/objects")
def list_objects(request: Request):
    s=current_session(request)
    with connect() as con:
        if s["role"]=="customer": rows=con.execute("SELECT * FROM objects WHERE customer_id=? AND active=1 ORDER BY id",(s["user_id"],)).fetchall()
        else: rows=con.execute("SELECT o.*,u.name customer_name FROM objects o JOIN users u ON u.id=o.customer_id ORDER BY o.id DESC").fetchall()
        return [rowdict(r) for r in rows]

@app.post("/api/objects")
def create_object(data:ObjectIn, request:Request):
    s=current_session(request); require_csrf(request,s)
    if s["role"]!="customer": raise HTTPException(403,"Nur Kunden können über diesen Endpunkt Objekte anlegen")
    with connect() as con:
        cur=con.execute("INSERT INTO objects(customer_id,name,type,address,city,postal_code,created_at) VALUES(?,?,?,?,?,?,?)",(s["user_id"],data.name.strip(),data.type.strip(),data.address.strip(),data.city.strip(),data.postal_code.strip(),now_iso()))
        audit(con,s["user_id"],"object_created","object",str(cur.lastrowid)); con.commit(); return {"id":cur.lastrowid,"ok":True}

# ---------- Tickets ----------
@app.get("/api/tickets")
def list_tickets(request:Request, status:Optional[str]=None, urgency:Optional[str]=None):
    s=current_session(request); where,params=ticket_access_clause(s); clauses=[]
    if where.strip(): clauses.append(where.replace("WHERE","",1).strip())
    if s["role"] == "employee":
        clauses.append("(t.assignee_user_id IS NULL OR t.assignee_user_id=?)"); params.append(s["user_id"])
    if status: clauses.append("t.status=?"); params.append(status)
    if urgency: clauses.append("t.urgency=?"); params.append(urgency)
    w=(" WHERE "+" AND ".join(clauses)) if clauses else ""
    sql=f"""SELECT t.*,o.name object_name,u.name assignee_name,c.name customer_name
             FROM tickets t LEFT JOIN objects o ON o.id=t.object_id LEFT JOIN users u ON u.id=t.assignee_user_id LEFT JOIN users c ON c.id=t.customer_id {w}
             ORDER BY CASE t.urgency WHEN 'Notfall' THEN 4 WHEN 'Dringend' THEN 3 WHEN 'Zeitnah' THEN 2 ELSE 1 END DESC, t.updated_at DESC"""
    with connect() as con:
        rows=con.execute(sql,params).fetchall(); return [serialize_ticket(con,r) for r in rows]

@app.post("/api/tickets")
def create_ticket(data:TicketIn, request:Request):
    s=current_session(request); require_csrf(request,s)
    if data.urgency not in URGENCIES: raise HTTPException(400,"Ungültige Priorität")
    if s["role"]!="customer": raise HTTPException(403,"Interne Auftragserstellung nutzt /api/admin/tickets-json")
    customer_id=s["user_id"]
    with connect() as con:
        validate_customer_object(con, customer_id, data.object_id)
        now=now_iso(); no=make_ticket_no(con)
        cur=con.execute("""INSERT INTO tickets(ticket_no,customer_id,object_id,category,urgency,location,description,preferred_contact,phone,status,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,'Eingegangen',?,?)""",(no,customer_id,data.object_id,data.category.strip(),data.urgency,data.location.strip(),data.description.strip(),data.preferred_contact.strip(),data.phone.strip(),now,now))
        tid=cur.lastrowid; con.execute("INSERT INTO ticket_history(ticket_id,actor_user_id,event,created_at) VALUES(?,?,?,?)",(tid,s["user_id"],"Vorgang angelegt",now))
        staff=con.execute("SELECT id FROM users WHERE role IN ('employee','admin') AND active=1").fetchall()
        for u in staff: notify(con,u["id"],f"Neue Meldung {no}",f"{data.urgency}: {data.category} · {data.location}","urgent" if data.urgency in {"Dringend","Notfall"} else "ticket")
        audit(con,s["user_id"],"ticket_created","ticket",str(tid),{"ticket_no":no,"urgency":data.urgency}); con.commit()
    send_push_roles(("employee","admin"),f"Neue Meldung {no}",f"{data.urgency}: {data.category} · {data.location}","/?portal=team")
    return {"id":tid,"ticket_no":no,"ok":True}

@app.post("/api/admin/tickets")
def admin_create_ticket(data:TicketIn, request:Request, customer_id:int=Form(...)):
    raise HTTPException(501,"Für interne Auftragserstellung bitte /api/admin/tickets-json verwenden")

@app.post("/api/admin/tickets-json")
def admin_create_ticket_json(data:AdminTicketIn, request:Request):
    s=current_session(request); require_csrf(request,s); require_role(s,"employee","admin")
    if data.urgency not in URGENCIES: raise HTTPException(400,"Ungültige Priorität")
    with connect() as con:
        cust=con.execute("SELECT id FROM users WHERE id=? AND role='customer' AND active=1",(data.customer_id,)).fetchone()
        if not cust: raise HTTPException(400,"Kunde nicht gefunden")
        validate_customer_object(con, data.customer_id, data.object_id)
        if data.assignee_user_id is not None and not con.execute("SELECT 1 FROM users WHERE id=? AND role IN ('employee','admin') AND active=1", (data.assignee_user_id,)).fetchone(): raise HTTPException(400,"Mitarbeiter nicht gefunden")
        if s["role"] == "employee" and data.assignee_user_id not in (None, s["user_id"]): raise HTTPException(403,"Mitarbeiter dürfen nur sich selbst zuweisen")
        now=now_iso(); no=make_ticket_no(con)
        cur=con.execute("""INSERT INTO tickets(ticket_no,customer_id,object_id,category,urgency,location,description,preferred_contact,phone,status,assignee_user_id,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,'Eingegangen',?,?,?)""",(no,data.customer_id,data.object_id,data.category,data.urgency,data.location,data.description,data.preferred_contact,data.phone,data.assignee_user_id,now,now))
        tid=cur.lastrowid; con.execute("INSERT INTO ticket_history(ticket_id,actor_user_id,event,created_at) VALUES(?,?,?,?)",(tid,s["user_id"],"Vorgang intern angelegt",now)); notify(con,data.customer_id,"Neuer Vorgang",f"{no} wurde für Ihr Objekt angelegt.","ticket"); audit(con,s["user_id"],"ticket_created_internal","ticket",str(tid)); con.commit()
    send_push_to_user(data.customer_id,"Neuer Vorgang",f"{no} wurde für Ihr Objekt angelegt.","/?portal=customer")
    return {"id":tid,"ticket_no":no,"ok":True}

@app.get("/api/tickets/{ticket_id}")
def get_ticket(ticket_id:int, request:Request):
    s=current_session(request)
    with connect() as con:
        row=con.execute("""SELECT t.*,o.name object_name,u.name assignee_name,c.name customer_name FROM tickets t LEFT JOIN objects o ON o.id=t.object_id LEFT JOIN users u ON u.id=t.assignee_user_id LEFT JOIN users c ON c.id=t.customer_id WHERE t.id=?""",(ticket_id,)).fetchone()
        if not row: raise HTTPException(404,"Ticket nicht gefunden")
        if s["role"]=="customer" and row["customer_id"]!=s["user_id"]: raise HTTPException(403,"Keine Berechtigung")
        require_staff_ticket_access(con, s, row)
        return serialize_ticket(con,row)

@app.patch("/api/tickets/{ticket_id}")
def patch_ticket(ticket_id:int, data:TicketPatch, request:Request):
    s=current_session(request); require_csrf(request,s); require_role(s,"employee","admin")
    push_customer=None; push_text=None
    with connect() as con:
        row=con.execute("SELECT * FROM tickets WHERE id=?",(ticket_id,)).fetchone()
        if not row: raise HTTPException(404,"Ticket nicht gefunden")
        require_staff_ticket_access(con, s, row)
        fields=[]; vals=[]; events=[]
        if data.status is not None:
            if data.status not in TICKET_STATUSES: raise HTTPException(400,"Ungültiger Status")
            fields.append("status=?"); vals.append(data.status); events.append(f"Status: {data.status}")
            if data.status=="Erledigt": fields.append("closed_at=?"); vals.append(now_iso())
        if data.assignee_user_id is not None:
            if data.assignee_user_id and not con.execute("SELECT 1 FROM users WHERE id=? AND role IN ('employee','admin') AND active=1",(data.assignee_user_id,)).fetchone(): raise HTTPException(400,"Mitarbeiter nicht gefunden")
            if s["role"] == "employee" and data.assignee_user_id not in (0, s["user_id"]): raise HTTPException(403,"Mitarbeiter dürfen nur sich selbst zuweisen")
            fields.append("assignee_user_id=?"); vals.append(data.assignee_user_id or None); events.append("Zuständigkeit geändert")
        if data.appointment_date is not None:
            fields.append("appointment_date=?"); vals.append(validate_date(data.appointment_date) if data.appointment_date else None); events.append("Termin geändert")
        if data.appointment_time is not None: fields.append("appointment_time=?"); vals.append(validate_time(data.appointment_time))
        if data.internal_note is not None: fields.append("internal_note=?"); vals.append(data.internal_note); events.append("Interne Notiz aktualisiert")
        fields.append("updated_at=?"); vals.append(now_iso()); vals.append(ticket_id)
        con.execute(f"UPDATE tickets SET {','.join(fields)} WHERE id=?",vals)
        for ev in events: con.execute("INSERT INTO ticket_history(ticket_id,actor_user_id,event,created_at) VALUES(?,?,?,?)",(ticket_id,s["user_id"],ev,now_iso()))
        if data.customer_message and row["customer_id"]:
            con.execute("INSERT INTO messages(customer_id,ticket_id,sender_user_id,sender_role,body,created_at) VALUES(?,?,?,?,?,?)",(row["customer_id"],ticket_id,s["user_id"],s["role"],data.customer_message.strip(),now_iso())); notify(con,row["customer_id"],"Neue Nachricht zu Ihrem Vorgang",data.customer_message.strip()[:180],"message")
        if row["customer_id"] and data.status:
            notify(con,row["customer_id"],"Status geändert",f"{row['ticket_no']}: {data.status}","status"); push_customer=row["customer_id"]; push_text=f"{row['ticket_no']}: {data.status}"
        upsert_ticket_appointment(con,ticket_id,s["user_id"])
        if row["customer_id"] and data.appointment_date:
            notify(con,row["customer_id"],"Termin geplant",f"{row['ticket_no']}: {data.appointment_date} {data.appointment_time or ''}".strip(),"appointment")
            push_customer=row["customer_id"]; push_text=f"Termin für {row['ticket_no']}: {data.appointment_date} {data.appointment_time or ''}".strip()
        audit(con,s["user_id"],"ticket_updated","ticket",str(ticket_id),data.model_dump(exclude_none=True)); con.commit()
    if push_customer and push_text: send_push_to_user(push_customer,"Steinbach Portal",push_text,"/?portal=customer")
    return {"ok":True}

# ---------- Appointments ----------
@app.get("/api/appointments")
def list_appointments(request:Request, status:Optional[str]=None):
    s=current_session(request)
    with connect() as con:
        base="""SELECT a.*,o.name object_name,c.name customer_name,e.name employee_name,t.ticket_no
                FROM appointments a JOIN users c ON c.id=a.customer_id LEFT JOIN objects o ON o.id=a.object_id LEFT JOIN users e ON e.id=a.employee_id LEFT JOIN tickets t ON t.id=a.ticket_id"""
        clauses=[]; params=[]
        if s["role"]=="customer": clauses.append("a.customer_id=?"); params.append(s["user_id"])
        elif s["role"]=="employee":
            # Employees see assigned appointments and unassigned requests they may take over.
            clauses.append("(a.employee_id=? OR a.employee_id IS NULL)"); params.append(s["user_id"])
        if status: clauses.append("a.status=?"); params.append(status)
        if clauses: base += " WHERE " + " AND ".join(clauses)
        base += " ORDER BY a.appointment_date ASC, a.time_start ASC, a.id ASC"
        return [serialize_appointment(r) for r in con.execute(base,params).fetchall()]

@app.post("/api/appointments")
def create_appointment(data:AppointmentIn, request:Request):
    s=current_session(request); require_csrf(request,s); validate_date(data.appointment_date); validate_time(data.time_start); validate_time(data.time_end)
    with connect() as con:
        if s["role"]=="customer":
            customer_id=s["user_id"]; employee_id=None; status="Angefragt"
            validate_customer_object(con, customer_id, data.object_id)
            if data.ticket_id and not con.execute("SELECT 1 FROM tickets WHERE id=? AND customer_id=?",(data.ticket_id,customer_id)).fetchone(): raise HTTPException(400,"Ticket nicht gefunden")
        else:
            require_role(s,"employee","admin")
            if data.ticket_id:
                t=con.execute("SELECT customer_id,object_id FROM tickets WHERE id=?",(data.ticket_id,)).fetchone()
                if not t or not t["customer_id"]: raise HTTPException(400,"Ticket/Kunde nicht gefunden")
                customer_id=t["customer_id"]
                object_id=data.object_id or t["object_id"]
            elif data.object_id:
                o=con.execute("SELECT customer_id FROM objects WHERE id=?",(data.object_id,)).fetchone()
                if not o: raise HTTPException(400,"Objekt nicht gefunden")
                customer_id=o["customer_id"]; object_id=data.object_id
            else: raise HTTPException(400,"Für Teamtermine ist Objekt oder Ticket erforderlich")
            employee_id=data.employee_id or (s["user_id"] if s["role"]=="employee" else None); status="Bestätigt"; data.object_id=object_id
        now=now_iso(); cur=con.execute("""INSERT INTO appointments(customer_id,object_id,ticket_id,employee_id,title,appointment_date,time_start,time_end,status,note,created_by,created_at,updated_at)
                                      VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",(customer_id,data.object_id,data.ticket_id,employee_id,data.title.strip(),data.appointment_date,data.time_start,data.time_end,status,data.note.strip(),s["user_id"],now,now))
        aid=cur.lastrowid
        if s["role"]=="customer":
            for r in con.execute("SELECT id FROM users WHERE role IN ('employee','admin') AND active=1").fetchall(): notify(con,r["id"],"Neue Terminanfrage",f"{data.title} · {data.appointment_date} {data.time_start}","appointment")
        else: notify(con,customer_id,"Termin bestätigt",f"{data.title} · {data.appointment_date} {data.time_start}","appointment")
        audit(con,s["user_id"],"appointment_created","appointment",str(aid),{"status":status}); con.commit()
    if s["role"]=="customer": send_push_roles(("employee","admin"),"Neue Terminanfrage",f"{data.title} · {data.appointment_date} {data.time_start}","/?portal=team")
    else: send_push_to_user(customer_id,"Termin bestätigt",f"{data.title} · {data.appointment_date} {data.time_start}","/?portal=customer")
    return {"id":aid,"status":status,"ok":True}

@app.patch("/api/appointments/{appointment_id}")
def patch_appointment(appointment_id:int, data:AppointmentPatch, request:Request):
    s=current_session(request); require_csrf(request,s); require_role(s,"employee","admin")
    with connect() as con:
        row=con.execute("SELECT * FROM appointments WHERE id=?",(appointment_id,)).fetchone()
        if not row: raise HTTPException(404,"Termin nicht gefunden")
        if s["role"]=="employee" and row["employee_id"] not in (None,s["user_id"]): raise HTTPException(403,"Termin ist einem anderen Mitarbeiter zugewiesen")
        fields=[]; vals=[]
        if data.employee_id is not None:
            if data.employee_id and not con.execute("SELECT 1 FROM users WHERE id=? AND role IN ('employee','admin') AND active=1",(data.employee_id,)).fetchone(): raise HTTPException(400,"Mitarbeiter nicht gefunden")
            fields.append("employee_id=?"); vals.append(data.employee_id)
        if data.title is not None: fields.append("title=?"); vals.append(data.title.strip())
        if data.appointment_date is not None: fields.append("appointment_date=?"); vals.append(validate_date(data.appointment_date))
        if data.time_start is not None: fields.append("time_start=?"); vals.append(validate_time(data.time_start))
        if data.time_end is not None: fields.append("time_end=?"); vals.append(validate_time(data.time_end))
        if data.status is not None:
            if data.status not in APPOINTMENT_STATUSES: raise HTTPException(400,"Ungültiger Terminstatus")
            fields.append("status=?"); vals.append(data.status)
        if data.note is not None: fields.append("note=?"); vals.append(data.note)
        fields.append("updated_at=?"); vals.append(now_iso()); vals.append(appointment_id)
        con.execute(f"UPDATE appointments SET {','.join(fields)} WHERE id=?",vals)
        updated=con.execute("SELECT * FROM appointments WHERE id=?",(appointment_id,)).fetchone()
        if updated["ticket_id"]:
            con.execute("UPDATE tickets SET appointment_date=?,appointment_time=?,assignee_user_id=COALESCE(?,assignee_user_id),status=CASE WHEN status='Eingegangen' THEN 'Termin geplant' ELSE status END,updated_at=? WHERE id=?",(updated["appointment_date"],updated["time_start"],updated["employee_id"],now_iso(),updated["ticket_id"]))
            con.execute("INSERT INTO ticket_history(ticket_id,actor_user_id,event,created_at) VALUES(?,?,?,?)",(updated["ticket_id"],s["user_id"],f"Termin: {updated['status']} · {updated['appointment_date']} {updated['time_start']}",now_iso()))
        notify(con,updated["customer_id"],"Termin aktualisiert",f"{updated['title']} · {updated['appointment_date']} {updated['time_start']} · {updated['status']}","appointment")
        audit(con,s["user_id"],"appointment_updated","appointment",str(appointment_id),data.model_dump(exclude_none=True)); con.commit()
    send_push_to_user(updated["customer_id"],"Termin aktualisiert",f"{updated['title']} · {updated['appointment_date']} {updated['time_start']} · {updated['status']}","/?portal=customer")
    return {"ok":True}

# ---------- Messages ----------
@app.get("/api/messages")
def list_messages(request:Request, ticket_id:Optional[int]=None):
    s=current_session(request)
    with connect() as con:
        if ticket_id and s["role"] in {"employee","admin"}:
            tr=con.execute("SELECT * FROM tickets WHERE id=?",(ticket_id,)).fetchone()
            if not tr: raise HTTPException(404,"Ticket nicht gefunden")
            require_staff_ticket_access(con, s, tr)
        if s["role"]=="customer": q="SELECT m.*,u.name sender_name FROM messages m LEFT JOIN users u ON u.id=m.sender_user_id WHERE m.customer_id=?"; params=[s["user_id"]]
        elif s["role"]=="employee": q="SELECT m.*,u.name sender_name,c.name customer_name FROM messages m LEFT JOIN users u ON u.id=m.sender_user_id JOIN users c ON c.id=m.customer_id LEFT JOIN tickets t ON t.id=m.ticket_id WHERE (m.ticket_id IS NULL OR t.assignee_user_id IS NULL OR t.assignee_user_id=?)"; params=[s["user_id"]]
        else: q="SELECT m.*,u.name sender_name,c.name customer_name FROM messages m LEFT JOIN users u ON u.id=m.sender_user_id JOIN users c ON c.id=m.customer_id WHERE 1=1"; params=[]
        if ticket_id: q+=" AND m.ticket_id=?"; params.append(ticket_id)
        q+=" ORDER BY m.created_at ASC"
        return [rowdict(r) for r in con.execute(q,params).fetchall()]

@app.post("/api/messages")
def send_message(data:MessageIn, request:Request):
    s=current_session(request); require_csrf(request,s); push_targets=[]; title="Neue Nachricht"
    with connect() as con:
        if s["role"]=="customer":
            customer_id=s["user_id"]
            if data.ticket_id:
                t=con.execute("SELECT * FROM tickets WHERE id=?",(data.ticket_id,)).fetchone()
                if not t or t["customer_id"] != customer_id: raise HTTPException(403,"Ticket gehört nicht zu diesem Kundenkonto")
        else:
            if data.ticket_id:
                t=con.execute("SELECT * FROM tickets WHERE id=?",(data.ticket_id,)).fetchone()
                if not t or not t["customer_id"]: raise HTTPException(400,"Ticket/Kunde nicht gefunden")
                require_staff_ticket_access(con, s, t)
                customer_id=t["customer_id"]
            elif data.customer_id:
                c=con.execute("SELECT id FROM users WHERE id=? AND role='customer' AND active=1",(data.customer_id,)).fetchone()
                if not c: raise HTTPException(400,"Kunde nicht gefunden")
                customer_id=c["id"]
            else: raise HTTPException(400,"Für Teamnachrichten ist Ticket oder Kunde erforderlich")
        cur=con.execute("INSERT INTO messages(customer_id,ticket_id,sender_user_id,sender_role,body,created_at) VALUES(?,?,?,?,?,?)",(customer_id,data.ticket_id,s["user_id"],s["role"],data.body.strip(),now_iso()))
        if s["role"]=="customer":
            push_targets=[r["id"] for r in con.execute("SELECT id FROM users WHERE role IN ('employee','admin') AND active=1").fetchall()]
            for uid in push_targets: notify(con,uid,"Neue Kundennachricht",data.body.strip()[:180],"message")
            title="Neue Kundennachricht"
        else:
            push_targets=[customer_id]; notify(con,customer_id,"Neue Nachricht vom Steinbach-Team",data.body.strip()[:180],"message"); title="Neue Nachricht vom Steinbach-Team"
        audit(con,s["user_id"],"message_sent","message",str(cur.lastrowid)); con.commit()
    for uid in push_targets: send_push_to_user(uid,title,data.body.strip()[:180],"/?portal=customer" if s["role"]!="customer" else "/?portal=team")
    return {"id":cur.lastrowid,"ok":True}

# ---------- Files ----------
@app.post("/api/tickets/{ticket_id}/files")
async def upload_ticket_file(ticket_id:int, request:Request, file:UploadFile=File(...)):
    s=current_session(request); require_csrf(request,s)
    with connect() as con:
        t=con.execute("SELECT * FROM tickets WHERE id=?",(ticket_id,)).fetchone()
        if not t: raise HTTPException(404,"Ticket nicht gefunden")
        if s["role"]=="customer" and t["customer_id"]!=s["user_id"]: raise HTTPException(403,"Keine Berechtigung")
        require_staff_ticket_access(con, s, t)
    mime=(file.content_type or "").lower()
    if mime not in ALLOWED_MIME: raise HTTPException(400,"Nur JPG, PNG, WebP oder PDF")
    data=await file.read(MAX_UPLOAD_BYTES+1)
    if len(data)>MAX_UPLOAD_BYTES: raise HTTPException(413,"Datei ist größer als 8 MB")
    if not valid_file_signature(mime, data): raise HTTPException(400,"Dateiinhalt passt nicht zum angegebenen Dateityp")
    ext=ALLOWED_MIME[mime]; stored=f"{secrets.token_hex(18)}{ext}"; path=UPLOADS/stored; path.write_bytes(data)
    original=re.sub(r"[^\w.()\- ]+","_",Path(file.filename or 'datei').name)[:180]
    with connect() as con:
        cur=con.execute("INSERT INTO uploads(ticket_id,uploaded_by,original_name,stored_name,mime_type,size_bytes,created_at) VALUES(?,?,?,?,?,?,?)",(ticket_id,s["user_id"],original,stored,mime,len(data),now_iso()))
        con.execute("INSERT INTO ticket_history(ticket_id,actor_user_id,event,created_at) VALUES(?,?,?,?)",(ticket_id,s["user_id"],f"Datei hinzugefügt: {original}",now_iso())); audit(con,s["user_id"],"file_uploaded","ticket",str(ticket_id),{"name":original,"size":len(data)}); con.commit(); return {"id":cur.lastrowid,"name":original,"ok":True}

@app.get("/api/files/{file_id}")
def download_file(file_id:int, request:Request):
    s=current_session(request)
    with connect() as con:
        row=con.execute("SELECT up.*,t.customer_id FROM uploads up JOIN tickets t ON t.id=up.ticket_id WHERE up.id=?",(file_id,)).fetchone()
        if not row: raise HTTPException(404,"Datei nicht gefunden")
        if s["role"]=="customer" and row["customer_id"]!=s["user_id"]: raise HTTPException(403,"Keine Berechtigung")
    path=UPLOADS/row["stored_name"]
    if not path.exists(): raise HTTPException(404,"Datei fehlt")
    return FileResponse(path,media_type=row["mime_type"],filename=row["original_name"])

# ---------- Service changes / referrals ----------
@app.get("/api/service-requests")
def list_service_requests(request:Request):
    s=current_session(request)
    with connect() as con:
        if s["role"]=="customer": rows=con.execute("SELECT * FROM service_requests WHERE customer_id=? ORDER BY id DESC",(s["user_id"],)).fetchall()
        else: rows=con.execute("SELECT sr.*,u.name customer_name,o.name object_name FROM service_requests sr JOIN users u ON u.id=sr.customer_id LEFT JOIN objects o ON o.id=sr.object_id ORDER BY sr.id DESC").fetchall()
        return [rowdict(r) for r in rows]

@app.post("/api/service-requests")
def create_service_request(data:ServiceRequestIn, request:Request):
    s=current_session(request); require_csrf(request,s); require_role(s,"customer")
    if data.action not in {"add","remove","change"}: raise HTTPException(400,"Ungültige Aktion")
    with connect() as con:
        validate_customer_object(con, s["user_id"], data.object_id)
        cur=con.execute("INSERT INTO service_requests(customer_id,object_id,service_code,action,note,created_at) VALUES(?,?,?,?,?,?)",(s["user_id"],data.object_id,data.service_code.strip(),data.action,data.note.strip(),now_iso()))
        for r in con.execute("SELECT id FROM users WHERE role='admin' AND active=1").fetchall(): notify(con,r["id"],"Leistungsänderung angefragt",f"{data.action}: {data.service_code}","service")
        audit(con,s["user_id"],"service_request_created","service_request",str(cur.lastrowid)); con.commit()
    send_push_roles(("admin",),"Leistungsänderung angefragt",f"{data.action}: {data.service_code}","/?portal=team")
    return {"id":cur.lastrowid,"ok":True}

@app.delete("/api/service-requests/{request_id}")
def cancel_service_request(request_id:int, request:Request):
    s=current_session(request); require_csrf(request,s); require_role(s,"customer")
    with connect() as con:
        row=con.execute("SELECT * FROM service_requests WHERE id=? AND customer_id=?",(request_id,s["user_id"])).fetchone()
        if not row: raise HTTPException(404,"Nicht gefunden")
        if row["status"]!="pending": raise HTTPException(409,"Nur offene Anfragen können zurückgenommen werden")
        con.execute("DELETE FROM service_requests WHERE id=?",(request_id,)); audit(con,s["user_id"],"service_request_cancelled","service_request",str(request_id)); con.commit(); return {"ok":True}

@app.patch("/api/service-requests/{request_id}")
def resolve_service_request(request_id:int, data:ResolveIn, request:Request):
    s=current_session(request); require_csrf(request,s); require_role(s,"admin")
    if data.status not in {"approved","rejected"}: raise HTTPException(400,"Ungültiger Status")
    with connect() as con:
        row=con.execute("SELECT * FROM service_requests WHERE id=?",(request_id,)).fetchone()
        if not row: raise HTTPException(404,"Nicht gefunden")
        con.execute("UPDATE service_requests SET status=?,resolved_at=?,resolved_by=? WHERE id=?",(data.status,now_iso(),s["user_id"],request_id)); notify(con,row["customer_id"],"Leistungsanfrage bearbeitet",f"{row['service_code']}: {data.status}","service"); audit(con,s["user_id"],"service_request_resolved","service_request",str(request_id),{"status":data.status}); con.commit()
    send_push_to_user(row["customer_id"],"Leistungsanfrage bearbeitet",f"{row['service_code']}: {data.status}","/?portal=customer")
    return {"ok":True}

@app.get("/api/referrals")
def list_referrals(request:Request):
    s=current_session(request)
    with connect() as con:
        if s["role"]=="customer": rows=con.execute("SELECT * FROM referrals WHERE customer_id=? ORDER BY id DESC",(s["user_id"],)).fetchall()
        else: rows=con.execute("SELECT r.*,u.name customer_name FROM referrals r JOIN users u ON u.id=r.customer_id ORDER BY r.id DESC").fetchall()
        return [rowdict(r) for r in rows]

@app.post("/api/referrals")
def create_referral(data:ReferralIn, request:Request):
    s=current_session(request); require_csrf(request,s); require_role(s,"customer")
    if data.reward_type not in {"discount","credit"}: raise HTTPException(400,"Ungültiger Vorteilstyp")
    with connect() as con:
        cur=con.execute("INSERT INTO referrals(customer_id,referred_name,referred_contact,reward_type,note,created_at) VALUES(?,?,?,?,?,?)",(s["user_id"],data.referred_name,data.referred_contact,data.reward_type,data.note,now_iso()))
        for r in con.execute("SELECT id FROM users WHERE role='admin' AND active=1").fetchall(): notify(con,r["id"],"Neue Empfehlung",data.referred_name,"referral")
        audit(con,s["user_id"],"referral_created","referral",str(cur.lastrowid)); con.commit()
    send_push_roles(("admin",),"Neue Empfehlung",data.referred_name,"/?portal=team")
    return {"id":cur.lastrowid,"ok":True}

@app.patch("/api/referrals/{referral_id}")
def resolve_referral(referral_id:int, data:ResolveIn, request:Request):
    s=current_session(request); require_csrf(request,s); require_role(s,"admin")
    if data.status not in {"approved","rejected"}: raise HTTPException(400,"Ungültiger Status")
    if data.reward_value_cents is not None and data.reward_value_cents < 0: raise HTTPException(400,"Ungültiger Betrag")
    with connect() as con:
        row=con.execute("SELECT * FROM referrals WHERE id=?",(referral_id,)).fetchone()
        if not row: raise HTTPException(404,"Nicht gefunden")
        con.execute("UPDATE referrals SET status=?,reward_value_cents=?,resolved_at=?,resolved_by=? WHERE id=?",(data.status,data.reward_value_cents,now_iso(),s["user_id"],referral_id)); notify(con,row["customer_id"],"Empfehlung bearbeitet",f"{row['referred_name']}: {data.status}","referral"); audit(con,s["user_id"],"referral_resolved","referral",str(referral_id),{"status":data.status,"value":data.reward_value_cents}); con.commit()
    send_push_to_user(row["customer_id"],"Empfehlung bearbeitet",f"{row['referred_name']}: {data.status}","/?portal=customer")
    return {"ok":True}

# ---------- Notifications / Push ----------
@app.get("/api/notifications")
def list_notifications(request:Request):
    s=current_session(request)
    with connect() as con: return [rowdict(r) for r in con.execute("SELECT * FROM notifications WHERE user_id=? ORDER BY id DESC LIMIT 100",(s["user_id"],)).fetchall()]

@app.post("/api/notifications/read-all")
def read_notifications(request:Request):
    s=current_session(request); require_csrf(request,s)
    with connect() as con: con.execute("UPDATE notifications SET read_at=? WHERE user_id=? AND read_at IS NULL",(now_iso(),s["user_id"])); con.commit(); return {"ok":True}

@app.get("/api/push/public-key")
def push_public_key():
    return {"enabled":push_enabled(),"public_key":VAPID_PUBLIC_KEY if push_enabled() else ""}

@app.get("/api/push/status")
def push_status(request:Request):
    s=current_session(request)
    with connect() as con: count=con.execute("SELECT COUNT(*) c FROM push_subscriptions WHERE user_id=? AND disabled_at IS NULL",(s["user_id"],)).fetchone()["c"]
    return {"configured":push_enabled(),"subscribed":count>0,"subscriptions":count}

@app.post("/api/push/subscribe")
def push_subscribe(data:PushSubscriptionIn, request:Request):
    s=current_session(request); require_csrf(request,s)
    now=now_iso()
    with connect() as con:
        row=con.execute("SELECT id FROM push_subscriptions WHERE endpoint=?",(data.endpoint,)).fetchone()
        if row: con.execute("UPDATE push_subscriptions SET user_id=?,p256dh=?,auth=?,updated_at=?,disabled_at=NULL WHERE id=?",(s["user_id"],data.p256dh,data.auth,now,row["id"]))
        else: con.execute("INSERT INTO push_subscriptions(user_id,endpoint,p256dh,auth,created_at,updated_at) VALUES(?,?,?,?,?,?)",(s["user_id"],data.endpoint,data.p256dh,data.auth,now,now))
        audit(con,s["user_id"],"push_subscribed"); con.commit()
    return {"ok":True,"configured":push_enabled()}

@app.delete("/api/push/subscribe")
def push_unsubscribe(data:PushSubscriptionIn, request:Request):
    s=current_session(request); require_csrf(request,s)
    with connect() as con:
        con.execute("UPDATE push_subscriptions SET disabled_at=?,updated_at=? WHERE user_id=? AND endpoint=?",(now_iso(),now_iso(),s["user_id"],data.endpoint)); audit(con,s["user_id"],"push_unsubscribed"); con.commit()
    return {"ok":True}

@app.post("/api/push/test")
def push_test(request:Request):
    s=current_session(request); require_csrf(request,s)
    if not push_enabled(): raise HTTPException(503,"Web-Push ist serverseitig noch nicht konfiguriert")
    sent=send_push_to_user(s["user_id"],"Steinbach Push-Test","Push-Benachrichtigungen funktionieren auf diesem Gerät.","/?portal=customer")
    return {"ok":sent>0,"sent":sent}

# ---------- Team / Admin ----------
@app.get("/api/team/users")
def team_users(request:Request):
    s=current_session(request); require_role(s,"employee","admin")
    with connect() as con: return [rowdict(r) for r in con.execute("SELECT id,name,email,role,phone,active,mfa_enabled,email_verified FROM users WHERE active=1 ORDER BY role,name").fetchall()]

@app.get("/api/admin/audit")
def audit_log(request:Request):
    s=current_session(request); require_role(s,"admin")
    with connect() as con: return [rowdict(r) for r in con.execute("SELECT a.*,u.name user_name FROM audit_log a LEFT JOIN users u ON u.id=a.user_id ORDER BY a.id DESC LIMIT 200").fetchall()]

@app.get("/api/admin/email-outbox")
def email_outbox(request:Request):
    s=current_session(request); require_role(s,"admin")
    with connect() as con: return [rowdict(r) for r in con.execute("SELECT id,to_email,subject,status,created_at,sent_at,error FROM email_outbox ORDER BY id DESC LIMIT 100").fetchall()]

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="127.0.0.1", port=int(os.getenv("PORT","8000")), reload=False)
