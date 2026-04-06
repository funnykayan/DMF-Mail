"""Helpers for keeping Postfix virtual mailbox flat-files in sync."""
import subprocess
from pathlib import Path
from config import DOMAIN, POSTFIX_VIRTUAL_MAILBOX_MAPS, POSTFIX_VIRTUAL_MAILBOX_DOMAINS, MAILBOX_ROOT
import database


def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)


def _sudo(cmd: list[str]) -> None:
    """Run a command with sudo (allowed via /etc/sudoers.d/dmfmail)."""
    subprocess.run(["sudo"] + cmd, check=True, capture_output=True)


def _rebuild_maps() -> None:
    """Rewrite /etc/postfix/virtual_mailbox_maps and hash it."""
    accounts = database.list_accounts()
    lines = []
    for acc in accounts:
        if acc["is_active"]:
            local = acc["email"].split("@")[0]
            # Dovecot maildir path relative to /var/mail/vhosts
            # Must include Maildir/ suffix to match Dovecot mail_location = maildir:~/Maildir
            lines.append(f"{acc['email']}    {DOMAIN}/{local}/Maildir/")
    POSTFIX_VIRTUAL_MAILBOX_MAPS.write_text("\n".join(lines) + "\n")
    _sudo(["postmap", str(POSTFIX_VIRTUAL_MAILBOX_MAPS)])


def _rebuild_domains() -> None:
    POSTFIX_VIRTUAL_MAILBOX_DOMAINS.write_text(f"{DOMAIN}\n")
    # No postmap needed – this is a plain list


def _reload_postfix() -> None:
    _sudo(["systemctl", "reload", "postfix"])


def _ensure_maildir(email: str) -> None:
    """Create Maildir for email via privileged wrapper script (sudo allowed via sudoers)."""
    _sudo(["/usr/local/bin/dmf-setup-maildir", email])


def _remove_maildir(email: str) -> None:
    import shutil
    local = email.split("@")[0]
    maildir = MAILBOX_ROOT / local
    if maildir.exists():
        shutil.rmtree(maildir)


def sync_account_added(email: str) -> None:
    """Call after a new account is inserted in the DB."""
    _ensure_maildir(email)
    _rebuild_maps()
    _rebuild_domains()
    _reload_postfix()


def sync_account_deleted(email: str) -> None:
    """Call after an account is deleted from the DB."""
    _remove_maildir(email)
    _rebuild_maps()
    _reload_postfix()


def sync_password_changed(email: str, new_password: str) -> None:
    """Update Dovecot passwd-file after a password change."""
    _update_dovecot_passwd(email, new_password)


def _update_dovecot_passwd(email: str, password: str | None = None) -> None:
    """Regenerate /etc/dovecot/users from the database (plus updated password)."""
    import crypt
    import random

    passwd_file = Path("/etc/dovecot/users")
    lines = {}

    # Load existing file
    if passwd_file.exists():
        for line in passwd_file.read_text().splitlines():
            if line.strip() and ":" in line:
                user = line.split(":")[0]
                lines[user] = line

    # Regenerate all accounts from DB if password is None, else just update given one
    accounts = database.list_accounts()
    for acc in accounts:
        if not acc["is_active"]:
            if acc["email"] in lines:
                del lines[acc["email"]]
            continue
        local = acc["email"].split("@")[0]
        uid, gid = 5000, 5000
        home = f"/var/mail/vhosts/{DOMAIN}/{local}"
        # We don't store plain-text passwords, so only update when explicitly given
        if acc["email"] == email and password:
            pw_hash = crypt.crypt(password, crypt.mksalt(crypt.METHOD_SHA512))
            lines[acc["email"]] = (
                f"{acc['email']}:{pw_hash}:{uid}:{gid}::{home}::"
            )
        elif acc["email"] not in lines:
            # Account exists in DB but not in passwd file and no password given
            # → skip rather than insert an unusable placeholder
            print(f"[dovecot] Skipping {acc['email']} — no password provided for sync")

    passwd_file.write_text("\n".join(lines.values()) + "\n")
    passwd_file.chmod(0o640)


def rebuild_dovecot_passwd_full(account_passwords: dict[str, str]) -> None:
    """Rebuild /etc/dovecot/users from scratch given a dict of email→plain_password."""
    import crypt
    passwd_file = Path("/etc/dovecot/users")
    uid, gid = 5000, 5000
    lines = []
    for email_addr, plain_pw in account_passwords.items():
        local = email_addr.split("@")[0]
        home = f"/var/mail/vhosts/{DOMAIN}/{local}"
        pw_hash = crypt.crypt(plain_pw, crypt.mksalt(crypt.METHOD_SHA512))
        lines.append(f"{email_addr}:{pw_hash}:{uid}:{gid}::{home}::")
    passwd_file.write_text("\n".join(lines) + "\n")
    passwd_file.chmod(0o640)
