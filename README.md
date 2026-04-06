# DMF Mail

A self-hosted mail server for **dutchforcesrp.nl** with:

- **Postfix** – SMTP (send + receive from the internet)
- **Dovecot** – IMAP (read email in the webmail or any email client)
- **OpenDKIM** – DKIM signing for deliverability
- **Python / FastAPI** – REST API + account management backend (systemd)
- **Node.js / Express** – Webmail frontend served via **PM2**

---

## Project structure

```
DMF-Mail/
├── backend/                  Python FastAPI application
│   ├── main.py               REST API (auth, accounts, mail send/receive)
│   ├── auth.py               JWT helpers
│   ├── database.py           SQLite account store
│   ├── mail.py               SMTP send + IMAP fetch helpers
│   ├── postfix_utils.py      Syncs accounts to Postfix/Dovecot files
│   ├── config.py             Configuration constants
│   └── requirements.txt
├── frontend/                 Node.js Express frontend
│   ├── server.js             Express server + /api proxy
│   ├── ecosystem.config.js   PM2 process config
│   ├── package.json
│   └── public/               Static HTML/CSS/JS webmail UI
│       ├── index.html        Login page
│       ├── webmail.html      Webmail inbox / compose
│       ├── admin.html        Admin account management
│       ├── css/style.css
│       └── js/
│           ├── app.js        Shared auth + API helpers
│           ├── webmail.js    Inbox + compose logic
│           └── admin.js      Account CRUD UI
├── postfix/                  Postfix config templates
├── dovecot/                  Dovecot config templates
├── dmf-mail.service          systemd unit for Python backend
├── env.example               Environment variable template
├── setup.sh                  One-shot setup script
└── README.md
```

---

## Requirements

| Component | Notes |
|-----------|-------|
| Ubuntu 22.04 / Debian 12 | This machine — other Debian-based distros should also work |
| Public IP address | Port 25 **must** be open — check with your ISP or hosting provider |
| Domain `dutchforcesrp.nl` | You must control the DNS zone |
| IPv4 reverse DNS (PTR) | Set in your ISP / hosting control panel to `mail.dutchforcesrp.nl` |

---

## 1. DNS records

Add **all** of these records to your `dutchforcesrp.nl` DNS zone **before** running the setup script (the A record for `mail` must be reachable for TLS cert issuance).

To find this machine's public IP run:

```bash
curl -4 https://ifconfig.me
```

Replace `<YOUR_PUBLIC_IP>` below with that address.

### Required records

| Type | Host / Name | Value | TTL | Notes |
|------|-------------|-------|-----|-------|
| **A** | `mail` | `<YOUR_PUBLIC_IP>` | 3600 | Hostname for the mail server |
| **MX** | `@` (root) | `mail.dutchforcesrp.nl` | 3600 | Priority **10** |
| **TXT** (SPF) | `@` (root) | `v=spf1 mx a ip4:<YOUR_PUBLIC_IP> ~all` | 3600 | Marks this machine as authorised sender |
| **TXT** (DMARC) | `_dmarc` | `v=DMARC1; p=quarantine; rua=mailto:postmaster@dutchforcesrp.nl; ruf=mailto:postmaster@dutchforcesrp.nl; pct=100` | 3600 | Quarantine mail that fails SPF/DKIM |

### DKIM record (generated during setup)

After running `setup.sh`, a DKIM key pair is generated. The script prints the TXT record value.
You can also view it at any time:

```bash
sudo cat /etc/opendkim/keys/dutchforcesrp.nl/mail.txt
```

Add it as:

| Type | Host / Name | Value |
|------|-------------|-------|
| **TXT** | `mail._domainkey` | `v=DKIM1; h=sha256; k=rsa; p=<long Base64 key>` |

### Reverse DNS (PTR record)

Log in to your ISP or hosting provider's control panel and set the **Reverse DNS / PTR** for this machine's public IP to:

```
mail.dutchforcesrp.nl
```

This is required for major email providers (Gmail, Outlook, etc.) to accept your outbound emails.

### Example: full zone overview

```
dutchforcesrp.nl.        3600  IN  MX   10 mail.dutchforcesrp.nl.
dutchforcesrp.nl.        3600  IN  TXT  "v=spf1 mx a ip4:<YOUR_PUBLIC_IP> ~all"
_dmarc.dutchforcesrp.nl. 3600  IN  TXT  "v=DMARC1; p=quarantine; rua=mailto:postmaster@dutchforcesrp.nl; pct=100"
mail._domainkey.dutchforcesrp.nl. 3600 IN TXT "v=DKIM1; h=sha256; k=rsa; p=<key>"
mail.dutchforcesrp.nl.   3600  IN  A    <YOUR_PUBLIC_IP>
```

> **DNS propagation** can take minutes to 48 hours. Use https://dnschecker.org to verify records are live before testing email.

---

## 2. Installation

The project is already on this machine. From the project directory, run the setup script:

```bash
cd /home/kayan/Projects/DMF-Dev/DMF-Mail
sudo bash setup.sh
```

The script will:

1. Update system packages
2. Install Postfix, Dovecot, OpenDKIM, **Nginx**, Certbot, Python 3, Node.js 20, PM2
3. Configure UFW firewall (ports 25, 587, 465, 993, 80, 443)
4. Create the `vmail` system user (uid/gid 5000)
5. Write the Nginx HTTP-only config block for `mail.dutchforcesrp.nl` and start Nginx
6. Run `certbot --nginx` — Certbot automatically upgrades the config to HTTPS and sets up the HTTP→HTTPS redirect
7. Configure and start **Postfix**
8. Configure and start **Dovecot**
9. Configure and start **OpenDKIM**
10. Install the Python backend to `/opt/dmf-mail/backend` → **systemd** service `dmf-mail`
11. Install the Node.js frontend to `/opt/dmf-mail/frontend` → **PM2** process `dmf-mail-frontend`
12. Set PM2 to start on boot
13. Configure Certbot auto-renewal (systemd timer or cron)

---

## 3. First login

After setup completes, the webmail is live at:

```
https://mail.dutchforcesrp.nl
```

> HTTP requests to `http://mail.dutchforcesrp.nl` are automatically redirected to HTTPS by Nginx.

Default admin credentials:

- **Email:**    `admin@dutchforcesrp.nl`
- **Password:** value of `INITIAL_ADMIN_PASSWORD` in `/etc/dmf-mail/env`

> Change the admin password immediately after first login via the admin panel.

---

## 4. Creating mail accounts

### Via the web admin panel

1. Log in as an admin at `https://mail.dutchforcesrp.nl`
2. You are redirected to **Admin → Manage Accounts**
3. Click **+ New Account**
4. Enter a username (e.g. `jan`), password, quota, and whether the user is an admin
5. Click **Create Account** – the account `jan@dutchforcesrp.nl` is created

The backend automatically:
- Creates the Maildir at `/var/mail/vhosts/dutchforcesrp.nl/jan/`
- Updates `/etc/postfix/virtual_mailbox_maps` and reloads Postfix
- Adds the user to `/etc/dovecot/users` with a SHA-512 hashed password

### Via the API (curl example)

```bash
# 1. Get a JWT token
TOKEN=$(curl -s -X POST http://localhost:4007/api/auth/login \
  -d "username=admin@dutchforcesrp.nl&password=YourAdminPassword" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

# 2. Create a new account
curl -s -X POST http://localhost:4007/api/accounts \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email":"employee@dutchforcesrp.nl","password":"SecurePass1!","is_admin":false,"quota_mb":500}'
```

---

## 5. Sending and receiving email

### Webmail

Users log in at `https://mail.dutchforcesrp.nl` with their `@dutchforcesrp.nl` email and password.

- **Inbox** – lists all received mail (via IMAP over localhost)
- **Compose** – sends mail through local Postfix on port 587 with STARTTLS
- **Reply** – pre-fills the compose window with the original message

### Email client (Thunderbird, Outlook, Apple Mail, etc.)

Use these settings:

| Setting | Value |
|---------|-------|
| **IMAP server** | `mail.dutchforcesrp.nl` |
| **IMAP port** | `993` (SSL/TLS) |
| **SMTP server** | `mail.dutchforcesrp.nl` |
| **SMTP port** | `587` (STARTTLS) |
| **Username** | Full email (e.g. `jan@dutchforcesrp.nl`) |
| **Password** | Account password |
| **Auth** | Normal password |

---

## 6. Service management

### Python backend (systemd)

```bash
# Status
sudo systemctl status dmf-mail

# Restart
sudo systemctl restart dmf-mail

# View logs
sudo journalctl -u dmf-mail -f

# Stop / start
sudo systemctl stop dmf-mail
sudo systemctl start dmf-mail
```

The service is enabled to **start automatically on boot**.

### Node.js frontend (PM2)

```bash
# List processes
pm2 list

# Status / logs
pm2 status dmf-mail-frontend
pm2 logs dmf-mail-frontend

# Restart
pm2 restart dmf-mail-frontend

# Stop / start
pm2 stop dmf-mail-frontend
pm2 start ecosystem.config.js

# Persist across reboots (re-run if you change the process list)
pm2 save
```

PM2 is configured to **start on boot** via a systemd unit created by `pm2 startup`.

### Postfix

```bash
sudo systemctl status postfix
sudo systemctl restart postfix
sudo tail -f /var/log/mail.log
```

### Dovecot

```bash
sudo systemctl status dovecot
sudo systemctl restart dovecot
sudo journalctl -u dovecot -f
```

---

## 7. Nginx & HTTPS

Nginx is installed and configured automatically by `setup.sh`. It acts as the public HTTPS reverse proxy in front of the Node.js frontend (port 4006, localhost-only).

**What the setup script does:**

1. Writes an HTTP-only config to `/etc/nginx/sites-available/dmf-mail`:

```nginx
server {
    listen 80;
    server_name mail.dutchforcesrp.nl;

    location / {
        proxy_pass         http://127.0.0.1:4006;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_set_header   Upgrade           $http_upgrade;
        proxy_set_header   Connection        "upgrade";
    }
}
```

2. Starts Nginx on port 80.
3. Runs `certbot --nginx -d mail.dutchforcesrp.nl` — Certbot automatically:
   - Obtains the TLS certificate from Let's Encrypt
   - Rewrites the Nginx config to add the HTTPS server block (port 443)
   - Adds the HTTP → HTTPS permanent redirect
   - Configures auto-renewal

Port 4006 is **not** opened in UFW — all public traffic goes through Nginx on ports 80/443.

### Manual Nginx commands

```bash
sudo systemctl status nginx
sudo systemctl reload nginx
sudo nginx -t                    # test config
sudo certbot renew --dry-run     # test renewal
```

---

## 8. Troubleshooting

### Email not delivered (check Postfix queue)

```bash
sudo mailq           # view queue
sudo postqueue -f    # flush / retry
sudo tail -100 /var/log/mail.log
```

### Test SMTP authentication

```bash
sudo swaks --to test@gmail.com \
           --from admin@dutchforcesrp.nl \
           --server mail.dutchforcesrp.nl \
           --port 587 \
           --tls \
           --auth-user admin@dutchforcesrp.nl \
           --auth-password YourPassword
```

### Test DKIM

Send an email to `check-auth@verifier.port25.com` – you will receive a report.  
Or use https://www.mail-tester.com.

### Check SPF / DKIM / DMARC results

```bash
sudo grep "dutchforcesrp" /var/log/mail.log | tail -50
```

### Dovecot auth failure

```bash
sudo doveadm auth test jan@dutchforcesrp.nl
sudo tail -f /var/log/syslog | grep dovecot
```

### Backend API not responding

```bash
sudo systemctl status dmf-mail
sudo journalctl -u dmf-mail --no-pager -n 50
curl http://localhost:4007/api/auth/me   # should return 401
```

---

## 9. Security checklist

- [ ] Change the default admin password
- [ ] Set a strong `SECRET_KEY` in `/etc/dmf-mail/env`
- [ ] Ensure PTR reverse DNS is set at your ISP / hosting provider
- [ ] Verify DKIM, SPF, DMARC with https://www.mail-tester.com
- [ ] Confirm HTTPS is working: `curl -I https://mail.dutchforcesrp.nl`
- [ ] Keep the server updated: `sudo apt-get update && sudo apt-get upgrade`
- [ ] Review Postfix `smtpd_recipient_restrictions` to prevent open relaying
- [ ] Rotate the DKIM key annually (`opendkim-genkey`)

---

## 10. Port reference

| Port | Protocol | Service | Description |
|------|----------|---------|-------------|
| 25 | TCP | Postfix | Inbound SMTP from internet |
| 587 | TCP | Postfix | Submission (authenticated clients) |
| 465 | TCP | Postfix | SMTPS (legacy wrapped TLS) |
| 993 | TCP | Dovecot | IMAPS (TLS) |
| 80 | TCP | Nginx | HTTP (auto-redirects to HTTPS) |
| 443 | TCP | Nginx | HTTPS webmail (`mail.dutchforcesrp.nl`) |
| 4006 | TCP | Node.js/PM2 | Webmail frontend (localhost only — not in UFW) |
| 4007 | TCP | FastAPI | REST API (localhost only) |
