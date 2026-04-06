"""DMF Mail – FastAPI backend.

Endpoints:
  POST /api/auth/login          – get JWT
  GET  /api/auth/me             – current user info
  GET  /api/accounts            – admin: list all accounts
  POST /api/accounts            – admin: create account
  PUT  /api/accounts/{id}       – admin: update (password / quota / active)
  DELETE /api/accounts/{id}     – admin: delete account
  GET  /api/mail/inbox          – user: list inbox (paginated)
  GET  /api/mail/folders        – user: list folders
  GET  /api/mail/count          – user: message count
  POST /api/mail/send           – user: send email
"""

from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from typing import Optional
import re

import database
import auth as auth_module
import mail as mail_module
from config import DOMAIN

try:
    import postfix_utils
    POSTFIX_AVAILABLE = True
except Exception:
    POSTFIX_AVAILABLE = False

# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="DMF Mail API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Startup ───────────────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup() -> None:
    from config import INITIAL_ADMIN_EMAIL, INITIAL_ADMIN_PASSWORD
    from pathlib import Path
    import os, stat
    database.init_db()

    # Always sync admin password from env → SQLite
    database.update_account_password(INITIAL_ADMIN_EMAIL, INITIAL_ADMIN_PASSWORD)

    if POSTFIX_AVAILABLE:
        passwd_file = Path("/etc/dovecot/users")
        # Auto-fix permissions so the service can always write the file
        try:
            passwd_file.parent.mkdir(parents=True, exist_ok=True)
            if not passwd_file.exists():
                passwd_file.touch()
            current = oct(stat.S_IMODE(os.stat(passwd_file).st_mode))
            if current != oct(0o660):
                os.chmod(passwd_file, 0o660)
        except Exception as e:
            print(f"[startup] Warning: could not fix dovecot/users permissions: {e}")

        # Sync admin to Dovecot (password only — maildir is created by root during setup)
        try:
            postfix_utils._update_dovecot_passwd(INITIAL_ADMIN_EMAIL, INITIAL_ADMIN_PASSWORD)
        except Exception as e:
            print(f"[startup] Warning: could not sync admin to Dovecot: {e}")

        # Warn about any accounts missing from Dovecot so they're easy to spot
        try:
            existing = passwd_file.read_text() if passwd_file.exists() else ""
            for acc in database.list_accounts():
                if acc["is_active"] and acc["email"] not in existing:
                    print(f"[startup] WARNING: {acc['email']} is missing from /etc/dovecot/users — reset their password via admin panel")
        except Exception as e:
            print(f"[startup] Warning: could not audit dovecot/users: {e}")


# ── Auth ──────────────────────────────────────────────────────────────────────

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    is_admin: bool
    email: str


@app.post("/api/auth/login", response_model=TokenResponse)
def login(form_data: OAuth2PasswordRequestForm = Depends()):
    account = database.get_account_by_email(form_data.username)
    if account is None or not account["is_active"]:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not database.verify_password(form_data.password, account["pw_hash"], account["salt"]):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    token = auth_module.create_access_token({"sub": account["email"]})
    return TokenResponse(access_token=token, is_admin=bool(account["is_admin"]), email=account["email"])


@app.get("/api/auth/me")
def me(current_user: dict = Depends(auth_module.get_current_user)):
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "username": current_user["username"],
        "is_admin": bool(current_user["is_admin"]),
        "quota_mb": current_user["quota_mb"],
        "created_at": current_user["created_at"],
    }


# ── Accounts (admin) ──────────────────────────────────────────────────────────

class CreateAccountRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    is_admin: bool = False
    quota_mb: int = 500


class UpdateAccountRequest(BaseModel):
    password: Optional[str] = None
    quota_mb: Optional[int] = None
    is_active: Optional[bool] = None
    is_admin: Optional[bool] = None


def account_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "email": row["email"],
        "username": row["username"],
        "is_admin": bool(row["is_admin"]),
        "is_active": bool(row["is_active"]),
        "quota_mb": row["quota_mb"],
        "created_at": row["created_at"],
    }


@app.get("/api/accounts")
def list_accounts(admin: dict = Depends(auth_module.require_admin)):
    return [account_to_dict(a) for a in database.list_accounts()]


@app.post("/api/accounts", status_code=201)
def create_account(req: CreateAccountRequest, admin: dict = Depends(auth_module.require_admin)):
    # Enforce domain
    if not req.email.endswith(f"@{DOMAIN}"):
        raise HTTPException(400, detail=f"Email must end with @{DOMAIN}")
    if database.get_account_by_email(req.email):
        raise HTTPException(409, detail="Account already exists")

    account = database.create_account(req.email, req.password, req.is_admin, req.quota_mb)

    if POSTFIX_AVAILABLE:
        try:
            postfix_utils.sync_account_added(req.email)
        except Exception as e:
            print(f"[postfix] Warning sync_account_added: {e}")
        try:
            postfix_utils._update_dovecot_passwd(req.email, req.password)
        except Exception as e:
            print(f"[postfix] Warning _update_dovecot_passwd: {e}")
            raise HTTPException(500, detail=f"Account created but Dovecot sync failed: {e}")

    return account_to_dict(account)


@app.put("/api/accounts/{account_id}")
def update_account(
    account_id: int,
    req: UpdateAccountRequest,
    admin: dict = Depends(auth_module.require_admin),
):
    account = database.get_account_by_id(account_id)
    if account is None:
        raise HTTPException(404, detail="Account not found")

    email = account["email"]

    if req.password is not None:
        database.update_account_password(email, req.password)
        if POSTFIX_AVAILABLE:
            try:
                postfix_utils._update_dovecot_passwd(email, req.password)
            except Exception as e:
                print(f"[postfix] Warning: {e}")

    import sqlite3, config
    conn = sqlite3.connect(str(config.DB_PATH))
    conn.row_factory = sqlite3.Row
    if req.quota_mb is not None:
        conn.execute("UPDATE accounts SET quota_mb=? WHERE id=?", (req.quota_mb, account_id))
    if req.is_active is not None:
        conn.execute("UPDATE accounts SET is_active=? WHERE id=?", (int(req.is_active), account_id))
    if req.is_admin is not None:
        conn.execute("UPDATE accounts SET is_admin=? WHERE id=?", (int(req.is_admin), account_id))
    conn.commit()
    conn.close()

    updated = database.get_account_by_id(account_id)
    return account_to_dict(updated)


@app.delete("/api/accounts/{account_id}", status_code=204)
def delete_account(account_id: int, admin: dict = Depends(auth_module.require_admin)):
    account = database.get_account_by_id(account_id)
    if account is None:
        raise HTTPException(404, detail="Account not found")

    # Can't delete yourself
    if account["id"] == admin["id"]:
        raise HTTPException(400, detail="Cannot delete your own account")

    email = account["email"]
    database.delete_account(email)

    if POSTFIX_AVAILABLE:
        try:
            postfix_utils.sync_account_deleted(email)
        except Exception as e:
            print(f"[postfix] Warning: {e}")


# ── Mail ──────────────────────────────────────────────────────────────────────

class SendEmailRequest(BaseModel):
    to: list[EmailStr]
    subject: str
    body: str
    cc: Optional[list[EmailStr]] = None
    bcc: Optional[list[EmailStr]] = None
    # The API requires the sender's plain-text password to authenticate SMTP
    # (JWT is used for the API, but SMTP auth uses the actual mail password)
    password: str


@app.post("/api/mail/send", status_code=200)
def send_email(req: SendEmailRequest, current_user: dict = Depends(auth_module.get_current_user)):
    try:
        mail_module.send_email(
            sender_email=current_user["email"],
            sender_password=req.password,
            recipients=req.to,
            subject=req.subject,
            body=req.body,
            cc=req.cc,
            bcc=req.bcc,
        )
    except Exception as e:
        raise HTTPException(500, detail=str(e))
    return {"status": "sent"}


@app.get("/api/mail/inbox")
def inbox(
    folder: str = "INBOX",
    limit: int = 50,
    offset: int = 0,
    password: str = "",
    current_user: dict = Depends(auth_module.get_current_user),
):
    if not password:
        raise HTTPException(400, detail="password query param required for IMAP auth")
    try:
        messages = mail_module.fetch_emails(
            email_address=current_user["email"],
            password=password,
            folder=folder,
            limit=limit,
            offset=offset,
        )
    except Exception as e:
        raise HTTPException(500, detail=str(e))
    return {"messages": messages, "count": len(messages)}


@app.get("/api/mail/count")
def email_count(
    folder: str = "INBOX",
    password: str = "",
    current_user: dict = Depends(auth_module.get_current_user),
):
    if not password:
        raise HTTPException(400, detail="password query param required")
    try:
        count = mail_module.get_email_count(current_user["email"], password, folder)
    except Exception as e:
        raise HTTPException(500, detail=str(e))
    return {"count": count}


@app.get("/api/mail/folders")
def get_folders(
    password: str = "",
    current_user: dict = Depends(auth_module.get_current_user),
):
    if not password:
        raise HTTPException(400, detail="password query param required")
    try:
        folders = mail_module.list_folders(current_user["email"], password)
    except Exception as e:
        raise HTTPException(500, detail=str(e))
    return {"folders": folders}


# ── Dev run ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="127.0.0.1", port=4007, reload=False)
