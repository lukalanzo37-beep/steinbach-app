from __future__ import annotations
import os, sqlite3
from pathlib import Path
from datetime import datetime, timezone
from security import hash_password

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv("STEINBACH_DB_PATH", ROOT / "data" / "steinbach.db"))

SCHEMA = r'''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  email TEXT NOT NULL UNIQUE COLLATE NOCASE,
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK(role IN ('customer','employee','admin')),
  name TEXT NOT NULL,
  phone TEXT DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  mfa_secret TEXT,
  mfa_enabled INTEGER NOT NULL DEFAULT 0,
  email_verified INTEGER NOT NULL DEFAULT 0,
  must_change_password INTEGER NOT NULL DEFAULT 0,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash TEXT NOT NULL UNIQUE,
  csrf_token TEXT NOT NULL,
  expires_at TEXT NOT NULL,
  created_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS auth_tokens (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  purpose TEXT NOT NULL CHECK(purpose IN ('password_reset','invite')),
  token_hash TEXT NOT NULL UNIQUE,
  expires_at TEXT NOT NULL,
  used_at TEXT,
  created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS objects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  type TEXT DEFAULT '',
  address TEXT DEFAULT '',
  city TEXT DEFAULT '',
  postal_code TEXT DEFAULT '',
  active INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tickets (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_no TEXT NOT NULL UNIQUE,
  customer_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  object_id INTEGER REFERENCES objects(id) ON DELETE SET NULL,
  category TEXT NOT NULL,
  urgency TEXT NOT NULL CHECK(urgency IN ('Normal','Zeitnah','Dringend','Notfall')),
  location TEXT DEFAULT '',
  description TEXT NOT NULL,
  preferred_contact TEXT DEFAULT 'Portal',
  phone TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'Eingegangen',
  assignee_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  appointment_date TEXT,
  appointment_time TEXT,
  internal_note TEXT DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  closed_at TEXT
);
CREATE TABLE IF NOT EXISTS ticket_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  event TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS appointments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  object_id INTEGER REFERENCES objects(id) ON DELETE SET NULL,
  ticket_id INTEGER REFERENCES tickets(id) ON DELETE CASCADE,
  employee_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  appointment_date TEXT NOT NULL,
  time_start TEXT DEFAULT '',
  time_end TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'Angefragt' CHECK(status IN ('Angefragt','Bestätigt','Verschoben','Abgesagt','Erledigt')),
  note TEXT DEFAULT '',
  created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  ticket_id INTEGER REFERENCES tickets(id) ON DELETE CASCADE,
  sender_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  sender_role TEXT NOT NULL,
  body TEXT NOT NULL,
  created_at TEXT NOT NULL,
  read_at TEXT
);
CREATE TABLE IF NOT EXISTS uploads (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ticket_id INTEGER NOT NULL REFERENCES tickets(id) ON DELETE CASCADE,
  uploaded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
  original_name TEXT NOT NULL,
  stored_name TEXT NOT NULL UNIQUE,
  mime_type TEXT NOT NULL,
  size_bytes INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS service_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  object_id INTEGER REFERENCES objects(id) ON DELETE SET NULL,
  service_code TEXT NOT NULL,
  action TEXT NOT NULL CHECK(action IN ('add','remove','change')),
  note TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS referrals (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  customer_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  referred_name TEXT NOT NULL,
  referred_contact TEXT DEFAULT '',
  reward_type TEXT NOT NULL CHECK(reward_type IN ('discount','credit')),
  note TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',
  reward_value_cents INTEGER,
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  resolved_by INTEGER REFERENCES users(id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'info',
  created_at TEXT NOT NULL,
  read_at TEXT
);
CREATE TABLE IF NOT EXISTS push_subscriptions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  endpoint TEXT NOT NULL UNIQUE,
  p256dh TEXT NOT NULL,
  auth TEXT NOT NULL,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  disabled_at TEXT
);
CREATE TABLE IF NOT EXISTS email_outbox (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  to_email TEXT NOT NULL,
  subject TEXT NOT NULL,
  body TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  created_at TEXT NOT NULL,
  sent_at TEXT,
  error TEXT DEFAULT ''
);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
  action TEXT NOT NULL,
  entity_type TEXT DEFAULT '',
  entity_id TEXT DEFAULT '',
  metadata TEXT DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tickets_customer ON tickets(customer_id, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_tickets_status ON tickets(status, urgency);
CREATE INDEX IF NOT EXISTS idx_messages_customer ON messages(customer_id, created_at);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id, read_at, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_appointments_customer ON appointments(customer_id, appointment_date, time_start);
CREATE INDEX IF NOT EXISTS idx_appointments_employee ON appointments(employee_id, appointment_date, time_start);
CREATE INDEX IF NOT EXISTS idx_auth_tokens_hash ON auth_tokens(token_hash, purpose);
CREATE INDEX IF NOT EXISTS idx_push_user ON push_subscriptions(user_id, disabled_at);
'''

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA busy_timeout=5000")
    return con

def _columns(con: sqlite3.Connection, table: str) -> set[str]:
    return {r["name"] for r in con.execute(f"PRAGMA table_info({table})").fetchall()}

def _ensure_column(con: sqlite3.Connection, table: str, name: str, ddl: str) -> None:
    if name not in _columns(con, table):
        con.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")

def init_db() -> None:
    with connect() as con:
        con.executescript(SCHEMA)
        # Safe additive migrations for existing V14 pilot databases.
        _ensure_column(con, "users", "mfa_secret", "TEXT")
        _ensure_column(con, "users", "mfa_enabled", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(con, "users", "email_verified", "INTEGER NOT NULL DEFAULT 0")
        _ensure_column(con, "users", "must_change_password", "INTEGER NOT NULL DEFAULT 0")
        con.commit()

def seed_demo() -> None:
    if os.getenv("STEINBACH_DEMO_SEED", "0") != "1":
        return
    seed_users = [
        (os.getenv("STEINBACH_ADMIN_EMAIL","admin@steinbach.local"), os.getenv("STEINBACH_ADMIN_PASSWORD","Admin!2026Demo"), "admin", "Steinbach Admin"),
        (os.getenv("STEINBACH_EMPLOYEE_EMAIL","mitarbeiter@steinbach.local"), os.getenv("STEINBACH_EMPLOYEE_PASSWORD","Mitarbeiter!2026Demo"), "employee", "Steinbach Mitarbeiter"),
        (os.getenv("STEINBACH_CUSTOMER_EMAIL","kunde@steinbach.local"), os.getenv("STEINBACH_CUSTOMER_PASSWORD","Kunde!2026Demo"), "customer", "Musterkunde"),
    ]
    with connect() as con:
        for email, pw, role, name in seed_users:
            row = con.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            if not row:
                con.execute("INSERT INTO users(email,password_hash,role,name,email_verified,created_at) VALUES(?,?,?,?,1,?)", (email,hash_password(pw),role,name,now_iso()))
        customer = con.execute("SELECT id FROM users WHERE role='customer' ORDER BY id LIMIT 1").fetchone()
        employee = con.execute("SELECT id FROM users WHERE role='employee' ORDER BY id LIMIT 1").fetchone()
        if customer and not con.execute("SELECT 1 FROM objects WHERE customer_id=? LIMIT 1", (customer['id'],)).fetchone():
            con.execute("INSERT INTO objects(customer_id,name,type,address,city,postal_code,created_at) VALUES(?,?,?,?,?,?,?)", (customer['id'],'Musterobjekt Baden-Baden','Wohnanlage / WEG','Musterstraße 8','Baden-Baden','76530',now_iso()))
        if customer and not con.execute("SELECT 1 FROM tickets WHERE customer_id=? LIMIT 1", (customer['id'],)).fetchone():
            obj = con.execute("SELECT id FROM objects WHERE customer_id=? LIMIT 1", (customer['id'],)).fetchone()
            tnow = now_iso()
            con.execute("INSERT INTO tickets(ticket_no,customer_id,object_id,category,urgency,location,description,status,assignee_user_id,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)", ('ST-DEMO-1001',customer['id'],obj['id'] if obj else None,'Technik','Dringend','Tiefgarage','Beleuchtung im hinteren Bereich ausgefallen.','Eingegangen',employee['id'] if employee else None,tnow,tnow))
            tid = con.execute("SELECT id FROM tickets WHERE ticket_no='ST-DEMO-1001'").fetchone()['id']
            con.execute("INSERT INTO ticket_history(ticket_id,event,created_at) VALUES(?,?,?)", (tid,'Vorgang angelegt',tnow))
        if customer and not con.execute("SELECT 1 FROM appointments WHERE customer_id=? LIMIT 1", (customer['id'],)).fetchone():
            obj = con.execute("SELECT id FROM objects WHERE customer_id=? LIMIT 1", (customer['id'],)).fetchone()
            con.execute("INSERT INTO appointments(customer_id,object_id,employee_id,title,appointment_date,time_start,time_end,status,note,created_by,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                        (customer['id'], obj['id'] if obj else None, employee['id'] if employee else None, 'Gartenpflege', '2026-09-24', '10:00', '12:00', 'Bestätigt', 'Demo-Termin', employee['id'] if employee else customer['id'], now_iso(), now_iso()))
        con.commit()
