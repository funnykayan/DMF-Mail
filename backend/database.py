"""SQLite database bootstrap + helpers."""

import hashlib
import secrets
import sqlite3

from config import DB_PATH, INITIAL_ADMIN_EMAIL, INITIAL_ADMIN_PASSWORD


def _get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    pw_hash = hashlib.sha256((salt + password).encode()).hexdigest()
    return pw_hash, salt


def verify_password(password: str, pw_hash: str, salt: str) -> bool:
    candidate, _ = hash_password(password, salt)
    return secrets.compare_digest(candidate, pw_hash)


def init_db() -> None:
    conn = _get_conn()
    c = conn.cursor()
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS accounts (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT    UNIQUE NOT NULL,
            username    TEXT    NOT NULL,
            pw_hash     TEXT    NOT NULL,
            salt        TEXT    NOT NULL,
            is_admin    INTEGER NOT NULL DEFAULT 0,
            is_active   INTEGER NOT NULL DEFAULT 1,
            quota_mb    INTEGER NOT NULL DEFAULT 500,
            created_at  TEXT    NOT NULL DEFAULT (datetime('now'))
        );
        """
    )
    conn.commit()

    # Seed the initial admin account if the table is empty
    c.execute("SELECT COUNT(*) FROM accounts")
    if c.fetchone()[0] == 0:
        pw_hash, salt = hash_password(INITIAL_ADMIN_PASSWORD)
        username = INITIAL_ADMIN_EMAIL.split("@")[0]
        c.execute(
            "INSERT INTO accounts (email, username, pw_hash, salt, is_admin) VALUES (?,?,?,?,1)",
            (INITIAL_ADMIN_EMAIL, username, pw_hash, salt),
        )
        conn.commit()
        print(f"[db] Seeded initial admin: {INITIAL_ADMIN_EMAIL}")

    conn.close()


# ── CRUD ──────────────────────────────────────────────────────────────────────


def get_account_by_email(email: str) -> sqlite3.Row | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM accounts WHERE email=?", (email,)).fetchone()
    conn.close()
    return row


def get_account_by_id(account_id: int) -> sqlite3.Row | None:
    conn = _get_conn()
    row = conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    conn.close()
    return row


def list_accounts() -> list[sqlite3.Row]:
    conn = _get_conn()
    rows = conn.execute("SELECT * FROM accounts ORDER BY id").fetchall()
    conn.close()
    return rows


def create_account(email: str, password: str, is_admin: bool = False, quota_mb: int = 500) -> sqlite3.Row:
    pw_hash, salt = hash_password(password)
    username = email.split("@")[0]
    conn = _get_conn()
    conn.execute(
        "INSERT INTO accounts (email, username, pw_hash, salt, is_admin, quota_mb) VALUES (?,?,?,?,?,?)",
        (email, username, pw_hash, salt, int(is_admin), quota_mb),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM accounts WHERE email=?", (email,)).fetchone()
    conn.close()
    return row


def update_account_password(email: str, new_password: str) -> None:
    pw_hash, salt = hash_password(new_password)
    conn = _get_conn()
    conn.execute(
        "UPDATE accounts SET pw_hash=?, salt=? WHERE email=?",
        (pw_hash, salt, email),
    )
    conn.commit()
    conn.close()


def delete_account(email: str) -> None:
    conn = _get_conn()
    conn.execute("DELETE FROM accounts WHERE email=?", (email,))
    conn.commit()
    conn.close()


def set_account_active(email: str, active: bool) -> None:
    conn = _get_conn()
    conn.execute("UPDATE accounts SET is_active=? WHERE email=?", (int(active), email))
    conn.commit()
    conn.close()
