#!/usr/bin/env bash
# =============================================================================
# DMF Mail – Setup Script
# Domain: dutchforcesrp.nl
# Tested on: Ubuntu 22.04 / Debian 12
# Run from the project directory on this machine: sudo bash setup.sh
# =============================================================================
set -euo pipefail

## ── Colour helpers ──────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; CYAN='\033[0;36m'; NC='\033[0m'
info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

## ── Root check ───────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && error "This script must be run as root (sudo)."

## ── Variables ────────────────────────────────────────────────────────────────
DOMAIN="dutchforcesrp.nl"
MAIL_HOST="mail.${DOMAIN}"
INSTALL_DIR="/opt/dmf-mail"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="/etc/dmf-mail/env"
VMAIL_UID=5000
VMAIL_GID=5000

## ── Step 0 – Confirm ─────────────────────────────────────────────────────────
echo ""
echo "=================================================================="
echo "  DMF Mail Setup – ${DOMAIN}"
echo "=================================================================="
echo ""
warn "This script will:"
echo "  • Install Postfix, Dovecot, OpenDKIM, Nginx, Certbot, Node.js, PM2 on THIS machine"
echo "  • Configure the mail server for ${DOMAIN}"
echo "  • Install the DMF Mail Python backend + JS frontend"
echo "  • Set up Nginx as the public HTTPS reverse proxy"
echo "  • Obtain a Let's Encrypt TLS certificate via Certbot for ${MAIL_HOST}"
echo ""
echo "  Your public IP: $(curl -s -4 https://ifconfig.me 2>/dev/null || echo 'unknown (no internet?)')"
echo ""
read -rp "Continue? [y/N] " CONFIRM
[[ "${CONFIRM,,}" == "y" ]] || { echo "Aborted."; exit 0; }

## ── Step 1 – System update ───────────────────────────────────────────────────
info "Updating system packages…"
apt-get update -qq
apt-get upgrade -y -qq
success "System updated."

## ── Step 2 – Install dependencies ───────────────────────────────────────────
info "Installing Postfix, Dovecot, OpenDKIM, Nginx, Certbot, Python, Node.js…"
DEBIAN_FRONTEND=noninteractive apt-get install -y -qq \
    postfix postfix-pcre \
    dovecot-core dovecot-imapd dovecot-lmtpd \
    opendkim opendkim-tools \
    nginx \
    certbot python3-certbot-nginx \
    python3 python3-pip python3-venv \
    curl unzip ufw \
    ca-certificates gnupg

# Node.js 20 LTS (NodeSource)
if ! command -v node &>/dev/null || [[ "$(node --version | cut -d. -f1 | tr -d v)" -lt 18 ]]; then
    info "Installing Node.js 20 LTS…"
    curl -fsSL https://deb.nodesource.com/setup_20.x | bash - -q
    apt-get install -y -qq nodejs
fi
success "All packages installed."

## ── Step 3 – Firewall ────────────────────────────────────────────────────────
info "Configuring UFW firewall…"
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh
ufw allow 25/tcp    comment "SMTP"
ufw allow 465/tcp   comment "SMTPS"
ufw allow 587/tcp   comment "Submission"
ufw allow 993/tcp   comment "IMAPS"
ufw allow 80/tcp    comment "HTTP / Certbot"
ufw allow 443/tcp   comment "HTTPS (Nginx webmail)"
# Port 4006 is NOT opened – Nginx is the only public entrypoint for the webmail
ufw --force enable
success "Firewall configured."

## ── Step 4 – vmail user ──────────────────────────────────────────────────────
info "Creating vmail system user (uid/gid ${VMAIL_UID})…"
if ! getent group vmail &>/dev/null; then
    groupadd -g "${VMAIL_GID}" vmail
fi
if ! id vmail &>/dev/null; then
    useradd -u "${VMAIL_UID}" -g vmail -d /var/mail/vhosts -s /sbin/nologin vmail
fi
mkdir -p "/var/mail/vhosts/${DOMAIN}"
chown -R vmail:vmail /var/mail/vhosts
success "vmail user ready."

## ── Step 5 – Nginx HTTP block (Certbot will upgrade to HTTPS) ───────────────
info "Writing Nginx HTTP config for ${MAIL_HOST}…"
warn "Make sure the A record for ${MAIL_HOST} already points to this machine's public IP!"
warn "Current public IP: $(curl -s -4 https://ifconfig.me 2>/dev/null || echo 'could not detect')"

cat > /etc/nginx/sites-available/dmf-mail <<NGINXCONF
server {
    listen 80;
    listen [::]:80;
    server_name ${MAIL_HOST};

    # Certbot will insert its ACME challenge block here automatically.
    # After running certbot --nginx it will also add the HTTPS server block
    # and the HTTP→HTTPS redirect.

    location / {
        proxy_pass         http://127.0.0.1:4006;
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_set_header   Upgrade           \$http_upgrade;
        proxy_set_header   Connection        "upgrade";
        proxy_read_timeout 60s;
    }
}
NGINXCONF

# Enable the site
ln -sf /etc/nginx/sites-available/dmf-mail /etc/nginx/sites-enabled/dmf-mail
rm -f /etc/nginx/sites-enabled/default   # remove default placeholder

# Ensure log directory exists (may be missing before nginx first starts)
mkdir -p /var/log/nginx
touch /var/log/nginx/error.log /var/log/nginx/access.log
chown -R www-data:adm /var/log/nginx

nginx -t
systemctl enable nginx
systemctl restart nginx
success "Nginx HTTP block created and started."

## ── Step 5b – Certbot (upgrades Nginx block to HTTPS automatically) ─────────
info "Running Certbot to obtain TLS certificate and configure HTTPS…"
certbot --nginx \
    --non-interactive \
    --agree-tos \
    --redirect \
    --email "admin@${DOMAIN}" \
    -d "${MAIL_HOST}" \
    || warn "Certbot failed – DNS may not have propagated yet. Run manually: certbot --nginx -d ${MAIL_HOST}"

# Renewal hook – reload Postfix, Dovecot, and Nginx after cert renewal
mkdir -p /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/dmf-mail.sh <<'HOOK'
#!/bin/bash
systemctl reload nginx postfix dovecot 2>/dev/null || true
HOOK
chmod +x /etc/letsencrypt/renewal-hooks/deploy/dmf-mail.sh
success "TLS certificate obtained and Nginx upgraded to HTTPS."

## ── Step 6 – Postfix ─────────────────────────────────────────────────────────
info "Configuring Postfix…"
cp -f "${REPO_DIR}/postfix/main.cf"                   /etc/postfix/main.cf
cp -f "${REPO_DIR}/postfix/master.cf"                 /etc/postfix/master.cf
cp -f "${REPO_DIR}/postfix/virtual_mailbox_domains"   /etc/postfix/virtual_mailbox_domains
cp -f "${REPO_DIR}/postfix/virtual_mailbox_maps"      /etc/postfix/virtual_mailbox_maps

postmap /etc/postfix/virtual_mailbox_maps
newaliases
postfix set-permissions

# Allow dmfmail service user to write virtual map files (needed for _rebuild_maps)
chown dmfmail:root /etc/postfix/virtual_mailbox_maps \
                   /etc/postfix/virtual_mailbox_maps.db \
                   /etc/postfix/virtual_mailbox_domains

# Configure SMTP relay credentials if supplied in env
if [[ -n "${RELAY_LOGIN:-}" && -n "${RELAY_PASSWORD:-}" && -n "${RELAY_HOST:-}" ]]; then
    echo "${RELAY_HOST} ${RELAY_LOGIN}:${RELAY_PASSWORD}" > /etc/postfix/sasl_passwd
    chmod 600 /etc/postfix/sasl_passwd
    postmap /etc/postfix/sasl_passwd
    info "Postfix relay credentials written."
fi

systemctl enable postfix
systemctl restart postfix
success "Postfix configured and started."

## ── Step 7 – Dovecot ─────────────────────────────────────────────────────────
info "Configuring Dovecot…"
cp -f "${REPO_DIR}/dovecot/dovecot.conf"               /etc/dovecot/dovecot.conf
cp -f "${REPO_DIR}/dovecot/10-auth.conf"               /etc/dovecot/conf.d/10-auth.conf
cp -f "${REPO_DIR}/dovecot/10-mail.conf"               /etc/dovecot/conf.d/10-mail.conf
cp -f "${REPO_DIR}/dovecot/10-ssl.conf"                /etc/dovecot/conf.d/10-ssl.conf
cp -f "${REPO_DIR}/dovecot/10-master.conf"             /etc/dovecot/conf.d/10-master.conf
cp -f "${REPO_DIR}/dovecot/auth-passwdfile.conf.ext"   /etc/dovecot/auth-passwdfile.conf.ext

# Create empty users file if not present
touch /etc/dovecot/users
chmod 660 /etc/dovecot/users
chown dmfmail:dovecot /etc/dovecot/users

# Ensure Dovecot socket dir is writable
mkdir -p /var/spool/postfix/private
chown root:postfix /var/spool/postfix/private

systemctl enable dovecot
systemctl restart dovecot
success "Dovecot configured and started."

## ── Step 8 – OpenDKIM ────────────────────────────────────────────────────────
info "Configuring OpenDKIM…"
mkdir -p /etc/opendkim/keys/${DOMAIN}

# Generate DKIM key pair if not already present
if [[ ! -f "/etc/opendkim/keys/${DOMAIN}/mail.private" ]]; then
    opendkim-genkey -D /etc/opendkim/keys/${DOMAIN}/ -d "${DOMAIN}" -s mail
    chown -R opendkim:opendkim /etc/opendkim
fi

# Print public key so user can add DNS record
DKIM_PUBLIC=$(cat "/etc/opendkim/keys/${DOMAIN}/mail.txt" 2>/dev/null || echo "key not found")

cat > /etc/opendkim.conf <<DKIM
Syslog        yes
SyslogSuccess yes
LogWhy        yes
Canonicalization relaxed/simple
Domain        ${DOMAIN}
Selector      mail
KeyFile       /etc/opendkim/keys/${DOMAIN}/mail.private
PidFile       /var/run/opendkim/opendkim.pid
SignatureAlgorithm rsa-sha256
UserID        opendkim:opendkim
Socket        inet:8891@localhost
DKIM

mkdir -p /var/run/opendkim
chown -R opendkim:opendkim /var/run/opendkim

systemctl enable opendkim
systemctl restart opendkim
success "OpenDKIM configured."
echo ""
warn "DKIM DNS TXT record (add to dutchforcesrp.nl):"
echo "${DKIM_PUBLIC}"
echo ""

## ── Step 9 – Python backend ───────────────────────────────────────────────────
info "Installing DMF Mail Python backend to ${INSTALL_DIR}…"
mkdir -p "${INSTALL_DIR}/backend"
cp -rf "${REPO_DIR}/backend/." "${INSTALL_DIR}/backend/"
mkdir -p "${INSTALL_DIR}/backend/data"

# Virtual environment
python3 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --quiet --upgrade pip
"${INSTALL_DIR}/venv/bin/pip" install --quiet -r "${INSTALL_DIR}/backend/requirements.txt"

# App user
if ! id dmfmail &>/dev/null; then
    useradd -r -s /sbin/nologin -d "${INSTALL_DIR}" -g vmail dmfmail || true
fi
chown -R dmfmail:vmail "${INSTALL_DIR}"

# Sudoers rule – allows dmfmail to run privileged mail commands without a password
cat > /usr/local/bin/dmf-setup-maildir <<'WRAPPER'
#!/bin/bash
# Called by dmfmail service to create a Maildir for a new account.
# Usage: dmf-setup-maildir <email>
set -e
EMAIL="$1"
[[ -z "$EMAIL" ]] && { echo "Usage: $0 <email>"; exit 1; }
LOCAL="${EMAIL%%@*}"
BASE="/var/mail/vhosts/dutchforcesrp.nl/${LOCAL}"
MDIR="${BASE}/Maildir"
mkdir -p "${MDIR}/cur" "${MDIR}/new" "${MDIR}/tmp"
chown -R vmail:vmail "${BASE}"
WRAPPER
chmod 755 /usr/local/bin/dmf-setup-maildir

printf '%s\n' \
  '# Allow dmfmail service user to run mail infrastructure commands without password' \
  'dmfmail ALL=(root) NOPASSWD: /usr/sbin/postmap /etc/postfix/virtual_mailbox_maps' \
  'dmfmail ALL=(root) NOPASSWD: /usr/bin/systemctl reload postfix' \
  'dmfmail ALL=(root) NOPASSWD: /usr/local/bin/dmf-setup-maildir *' \
  > /etc/sudoers.d/dmfmail
chmod 440 /etc/sudoers.d/dmfmail

# Environment file
mkdir -p /etc/dmf-mail
if [[ ! -f "${ENV_FILE}" ]]; then
    cp "${REPO_DIR}/env.example" "${ENV_FILE}"
    RANDOM_SECRET=$(openssl rand -hex 32)
    sed -i "s/CHANGE_THIS_TO_A_LONG_RANDOM_SECRET/${RANDOM_SECRET}/" "${ENV_FILE}"
    chmod 640 "${ENV_FILE}"
    chown root:vmail "${ENV_FILE}"
    warn "Environment file created at ${ENV_FILE}"
    warn "Edit it to set INITIAL_ADMIN_PASSWORD before starting the service!"
fi

# Systemd service
cp -f "${REPO_DIR}/dmf-mail.service" /etc/systemd/system/dmf-mail.service
systemctl daemon-reload
systemctl enable dmf-mail
systemctl restart dmf-mail
success "DMF Mail backend installed and started (port 4007)."

## ── Step 10 – Node.js frontend ───────────────────────────────────────────────
info "Installing DMF Mail frontend…"
mkdir -p "${INSTALL_DIR}/frontend"
cp -rf "${REPO_DIR}/frontend/." "${INSTALL_DIR}/frontend/"
cd "${INSTALL_DIR}/frontend"
npm install --silent --production

# Install PM2 globally
if ! command -v pm2 &>/dev/null; then
    npm install -g pm2 --silent
fi

chown -R dmfmail:vmail "${INSTALL_DIR}/frontend"
# The frontend runs under the invoking user's PM2 daemon (not dmfmail),
# so that it shares the same pm2 startup context as other services.
REAL_USER="${SUDO_USER:-$(whoami)}"
REAL_HOME=$(getent passwd "${REAL_USER}" | cut -d: -f6)

# Stop and remove any stale dmfmail-owned PM2 instance to avoid port conflicts
su -s /bin/bash dmfmail -c "pm2 delete dmf-mail-frontend 2>/dev/null; pm2 save --force 2>/dev/null" || true

# Start frontend as the real (invoking) user
su -s /bin/bash "${REAL_USER}" -c "cd ${INSTALL_DIR}/frontend && pm2 delete dmf-mail-frontend 2>/dev/null; pm2 start ecosystem.config.js --env production && pm2 save" || true

# Make PM2 start on boot for the real user
su -s /bin/bash "${REAL_USER}" -c "pm2 startup systemd -u ${REAL_USER} --hp ${REAL_HOME}" | tail -1 | bash || \
    warn "PM2 startup cmd failed – run 'pm2 startup' manually as ${REAL_USER}."

success "DMF Mail frontend installed and running (port 4006)."

## ── Step 11 – Certbot auto-renewal ─────────────────────────────────────────
info "Ensuring Certbot renewal is active…"
# certbot --nginx enables the systemd timer automatically; fall back to cron
if systemctl is-active --quiet snap.certbot.renew.timer 2>/dev/null || \
   systemctl is-active --quiet certbot.timer 2>/dev/null; then
    info "Certbot systemd renewal timer is already active."
else
    (crontab -l 2>/dev/null | grep -v certbot; echo "0 3 * * * certbot renew --quiet --post-hook 'systemctl reload nginx postfix dovecot'") | crontab -
    info "Added certbot renew to cron (runs daily at 03:00)."
fi
success "Certbot auto-renewal configured."

## ── Step 12 – Summary ────────────────────────────────────────────────────────
echo ""
echo "=================================================================="
echo -e "  ${GREEN}DMF Mail setup complete!${NC}"
echo "=================================================================="
echo ""
echo "  Webmail (HTTPS)    : https://${MAIL_HOST}"
echo "  Webmail (HTTP)     : http://${MAIL_HOST}  (redirects to HTTPS)"
echo "  API (backend)      : http://127.0.0.1:4007  (localhost only)"
echo ""
echo "  Default admin login:"
echo "    Email    : admin@${DOMAIN}"
echo "    Password : (set in ${ENV_FILE})"
echo ""
echo "  Important next steps:"
echo "  1. Verify DNS records are live: https://dnschecker.org"
echo "  2. Edit ${ENV_FILE} to set a secure admin password"
echo "  3. Restart the backend:  sudo systemctl restart dmf-mail"
echo "  4. Add your DKIM TXT record (shown above) to your DNS"
echo ""
echo "  Service status:"
systemctl is-active --quiet postfix   && echo -e "    postfix  : ${GREEN}running${NC}" || echo -e "    postfix  : ${RED}stopped${NC}"
systemctl is-active --quiet dovecot   && echo -e "    dovecot  : ${GREEN}running${NC}" || echo -e "    dovecot  : ${RED}stopped${NC}"
systemctl is-active --quiet opendkim  && echo -e "    opendkim : ${GREEN}running${NC}" || echo -e "    opendkim : ${RED}stopped${NC}"
systemctl is-active --quiet dmf-mail  && echo -e "    dmf-mail : ${GREEN}running${NC}" || echo -e "    dmf-mail : ${RED}stopped${NC}"
echo ""
