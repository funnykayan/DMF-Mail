"""SMTP send + IMAP fetch helpers."""
import smtplib
import imaplib
import email as email_lib
import email.header
import email.utils
import ssl
from typing import Optional
from config import SMTP_HOST, SMTP_PORT, IMAP_HOST, IMAP_PORT


# ── SSL context for localhost mail services ───────────────────────────────────

def _local_ssl_context() -> ssl.SSLContext:
    """SSL context for localhost Dovecot/Postfix connections.
    Hostname verification is disabled because the cert is issued for
    mail.dutchforcesrp.nl, not localhost. The connection is still encrypted."""
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


# ── SEND ─────────────────────────────────────────────────────────────────────

def send_email(
    sender_email: str,
    sender_password: str,
    recipients: list[str],
    subject: str,
    body: str,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
) -> None:
    """Send an email through the local Postfix submission port (587, STARTTLS)."""
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart

    msg = MIMEMultipart("alternative")
    msg["From"] = sender_email
    msg["To"] = ", ".join(recipients)
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "html"))

    all_recipients = recipients + (cc or []) + (bcc or [])

    context = _local_ssl_context()
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.ehlo()
        server.starttls(context=context)
        server.login(sender_email, sender_password)
        server.sendmail(sender_email, all_recipients, msg.as_string())


# ── RECEIVE ───────────────────────────────────────────────────────────────────

def _decode_header_value(value: str) -> str:
    parts = email.header.decode_header(value)
    decoded = []
    for part, charset in parts:
        if isinstance(part, bytes):
            decoded.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            decoded.append(part)
    return " ".join(decoded)


def _get_body(msg: email_lib.message.Message) -> str:
    body = ""
    if msg.is_multipart():
        for part in msg.walk():
            ct = part.get_content_type()
            cd = str(part.get("Content-Disposition", ""))
            if "attachment" in cd:
                continue
            if ct == "text/html":
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset("utf-8")
                body = payload.decode(charset, errors="replace")
                break
            if ct == "text/plain" and not body:
                payload = part.get_payload(decode=True)
                charset = part.get_content_charset("utf-8")
                body = payload.decode(charset, errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset("utf-8")
            body = payload.decode(charset, errors="replace")
    return body


def fetch_emails(
    email_address: str,
    password: str,
    folder: str = "INBOX",
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """Fetch emails from Dovecot IMAP over TLS."""
    context = _local_ssl_context()
    with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=context) as imap:
        imap.login(email_address, password)
        imap.select(folder)

        _, data = imap.search(None, "ALL")
        message_ids: list[bytes] = data[0].split() if data[0] else []
        # Return newest first
        message_ids = list(reversed(message_ids))
        page = message_ids[offset : offset + limit]

        messages = []
        for msg_id in page:
            _, msg_data = imap.fetch(msg_id, "(RFC822)")
            raw = msg_data[0][1]
            msg = email_lib.message_from_bytes(raw)

            messages.append(
                {
                    "id": msg_id.decode(),
                    "from": _decode_header_value(msg.get("From", "")),
                    "to": _decode_header_value(msg.get("To", "")),
                    "subject": _decode_header_value(msg.get("Subject", "(no subject)")),
                    "date": msg.get("Date", ""),
                    "body": _get_body(msg),
                    "read": False,  # Simplified; full impl would check \\Seen flag
                }
            )

        return messages


def get_email_count(email_address: str, password: str, folder: str = "INBOX") -> int:
    context = _local_ssl_context()
    with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=context) as imap:
        imap.login(email_address, password)
        imap.select(folder)
        _, data = imap.search(None, "ALL")
        if data[0]:
            return len(data[0].split())
        return 0


def list_folders(email_address: str, password: str) -> list[str]:
    context = _local_ssl_context()
    with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, ssl_context=context) as imap:
        imap.login(email_address, password)
        _, folders = imap.list()
        result = []
        for f in folders:
            parts = f.decode().split(' "/" ')
            if len(parts) == 2:
                name = parts[1].strip('"')
                result.append(name)
        return result
