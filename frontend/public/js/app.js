/**
 * DMF Mail – shared utilities (app.js)
 * Loaded on every page.
 */

const DMFMail = (() => {
  const API = '/api';  // Proxied by Express: /api/* → FastAPI

  // ── Token storage ──────────────────────────────────────────────────────
  function getToken()    { return localStorage.getItem('dmf_token'); }
  function getEmail()    { return localStorage.getItem('dmf_email'); }
  function isAdmin()     { return localStorage.getItem('dmf_is_admin') === 'true'; }
  function getPassword() { return sessionStorage.getItem('dmf_password'); }

  function setSession(token, email, admin) {
    localStorage.setItem('dmf_token', token);
    localStorage.setItem('dmf_email', email);
    localStorage.setItem('dmf_is_admin', admin ? 'true' : 'false');
  }

  function clearSession() {
    localStorage.removeItem('dmf_token');
    localStorage.removeItem('dmf_email');
    localStorage.removeItem('dmf_is_admin');
    sessionStorage.removeItem('dmf_password');
  }

  // ── HTTP helpers ───────────────────────────────────────────────────────
  async function request(method, path, body = null, extraHeaders = {}) {
    const headers = { ...extraHeaders };
    const token = getToken();
    if (token) headers['Authorization'] = `Bearer ${token}`;

    let init = { method, headers };

    if (body !== null) {
      if (body instanceof URLSearchParams) {
        headers['Content-Type'] = 'application/x-www-form-urlencoded';
        init.body = body.toString();
      } else {
        headers['Content-Type'] = 'application/json';
        init.body = JSON.stringify(body);
      }
    }

    const res = await fetch(API + path, init);

    if (res.status === 204) return null;

    let data;
    try { data = await res.json(); } catch { data = {}; }

    if (!res.ok) {
      const msg = data?.detail || data?.message || `HTTP ${res.status}`;
      throw new Error(Array.isArray(msg) ? msg.map(e => e.msg).join(', ') : msg);
    }
    return data;
  }

  const get  = (path)       => request('GET',    path);
  const post = (path, body) => request('POST',   path, body);
  const put  = (path, body) => request('PUT',    path, body);
  const del  = (path)       => request('DELETE', path);

  // ── Auth ───────────────────────────────────────────────────────────────
  async function login(email, password) {
    const form = new URLSearchParams({ username: email, password });
    const data = await request('POST', '/api/auth/login', form);
    setSession(data.access_token, data.email, data.is_admin);
    // Store plain password in sessionStorage for IMAP/SMTP (cleared on tab close)
    sessionStorage.setItem('dmf_password', password);
    return data;
  }

  function logout() {
    clearSession();
    window.location.href = '/';
  }

  // ── Guards ─────────────────────────────────────────────────────────────
  function requireAuth() {
    if (!getToken()) { window.location.href = '/'; }
  }

  function requireAdmin() {
    requireAuth();
    if (!isAdmin()) { window.location.href = '/webmail.html'; }
  }

  // ── Date format ────────────────────────────────────────────────────────
  function formatDate(dateStr) {
    if (!dateStr) return '';
    try {
      const d = new Date(dateStr);
      const now = new Date();
      const diff = now - d;
      if (diff < 86400000 && d.getDate() === now.getDate()) {
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      }
      return d.toLocaleDateString([], { month: 'short', day: 'numeric' });
    } catch { return dateStr; }
  }

  // ── HTML escape ────────────────────────────────────────────────────────
  function esc(str) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(str || ''));
    return div.innerHTML;
  }

  return { getToken, getEmail, isAdmin, getPassword, login, logout, requireAuth, requireAdmin, get, post, put, del, formatDate, esc };
})();

// Global logout handler
document.addEventListener('DOMContentLoaded', () => {
  const logoutBtn = document.getElementById('logout-btn');
  if (logoutBtn) logoutBtn.addEventListener('click', (e) => { e.preventDefault(); DMFMail.logout(); });

  const userEl = document.getElementById('user-email');
  if (userEl) userEl.textContent = DMFMail.getEmail() || '';
});
