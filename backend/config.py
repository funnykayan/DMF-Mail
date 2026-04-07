import os
from pathlib import Path

# ── Domain ────────────────────────────────────────────────────────────────────
DOMAIN = "dutchforcesrp.nl"
MAIL_DOMAIN = f"mail.{DOMAIN}"

# ── JWT ───────────────────────────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_IN_PRODUCTION_A_VERY_LONG_RANDOM_STRING")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 480  # 8 hours

# ── Database ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "data" / "mail.db"

# ── Mail server ───────────────────────────────────────────────────────────────
SMTP_HOST = "localhost"
SMTP_PORT = 587  # Postfix submission port (starttls)
IMAP_HOST = "localhost"
IMAP_PORT = 993  # Dovecot imaps

# ── Mailbox root (must match Dovecot mail_home) ───────────────────────────────
MAILBOX_ROOT = Path(os.getenv("MAILBOX_ROOT", f"/var/mail/vhosts/{DOMAIN}"))

# ── Admin ─────────────────────────────────────────────────────────────────────
# First user created via API with is_admin=True, or set here for initial seed
INITIAL_ADMIN_EMAIL = os.getenv("INITIAL_ADMIN_EMAIL", f"admin@{DOMAIN}")
INITIAL_ADMIN_PASSWORD = os.getenv("INITIAL_ADMIN_PASSWORD", "ChangeMe123!")

# ── Postfix virtual mailbox files ─────────────────────────────────────────────
POSTFIX_VIRTUAL_MAILBOX_MAPS = Path("/etc/postfix/virtual_mailbox_maps")
POSTFIX_VIRTUAL_MAILBOX_DOMAINS = Path("/etc/postfix/virtual_mailbox_domains")
