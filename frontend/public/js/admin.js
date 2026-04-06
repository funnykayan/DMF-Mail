/**
 * DMF Mail – admin page logic (admin.js)
 */

document.addEventListener('DOMContentLoaded', async () => {
  DMFMail.requireAdmin();

  const tbody         = document.getElementById('accounts-tbody');
  const loadingEl     = document.getElementById('accounts-loading');
  const errorEl       = document.getElementById('accounts-error');
  const accountModal  = document.getElementById('account-modal');
  const deleteModal   = document.getElementById('delete-modal');

  let editingId = null;

  // ── Load accounts ─────────────────────────────────────────────────────
  async function loadAccounts() {
    loadingEl.classList.remove('hidden');
    errorEl.classList.add('hidden');
    try {
      const accounts = await DMFMail.get('/api/accounts');
      renderAccounts(accounts);
    } catch (err) {
      errorEl.textContent = err.message;
      errorEl.classList.remove('hidden');
    } finally {
      loadingEl.classList.add('hidden');
    }
  }

  function renderAccounts(accounts) {
    tbody.innerHTML = '';
    if (!accounts.length) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:var(--color-text-muted);padding:32px">No accounts yet.</td></tr>';
      return;
    }
    const me = DMFMail.getEmail();
    accounts.forEach(acc => {
      const tr = document.createElement('tr');
      const created = acc.created_at ? new Date(acc.created_at).toLocaleDateString() : '–';
      tr.innerHTML = `
        <td><strong>${DMFMail.esc(acc.email)}</strong>${acc.email === me ? ' <span style="font-size:10px;color:var(--color-text-muted)">(you)</span>' : ''}</td>
        <td><span class="role-badge ${acc.is_admin ? 'role-admin' : 'role-user'}">${acc.is_admin ? 'Admin' : 'User'}</span></td>
        <td>${DMFMail.esc(String(acc.quota_mb))}</td>
        <td><span class="status-badge ${acc.is_active ? 'status-active' : 'status-inactive'}">${acc.is_active ? 'Active' : 'Inactive'}</span></td>
        <td>${DMFMail.esc(created)}</td>
        <td>
          <div class="action-btns">
            <button class="btn btn-ghost btn-sm edit-btn" data-id="${acc.id}">Edit</button>
            ${acc.email !== me ? `<button class="btn btn-danger btn-sm delete-btn" data-id="${acc.id}" data-email="${DMFMail.esc(acc.email)}">Delete</button>` : ''}
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    });

    // Edit buttons
    tbody.querySelectorAll('.edit-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        const id   = parseInt(btn.dataset.id);
        const row  = accounts.find(a => a.id === id);
        openEditModal(row);
      });
    });

    // Delete buttons
    tbody.querySelectorAll('.delete-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        openDeleteModal(parseInt(btn.dataset.id), btn.dataset.email);
      });
    });
  }

  // ── Create / Edit modal ───────────────────────────────────────────────
  function openCreateModal() {
    editingId = null;
    document.getElementById('modal-title').textContent = 'New Account';
    document.getElementById('modal-save').textContent  = 'Create Account';
    document.getElementById('acc-username').value = '';
    document.getElementById('acc-username').disabled = false;
    document.getElementById('acc-password').value = '';
    document.getElementById('acc-quota').value   = 500;
    document.getElementById('acc-admin').checked = false;
    document.getElementById('acc-active').checked = true;
    document.getElementById('password-group').querySelector('label').textContent = 'Password';
    document.getElementById('active-group').classList.add('hidden');
    document.getElementById('modal-error').classList.add('hidden');
    accountModal.classList.remove('hidden');
    document.getElementById('acc-username').focus();
  }

  function openEditModal(acc) {
    editingId = acc.id;
    document.getElementById('modal-title').textContent = 'Edit Account';
    document.getElementById('modal-save').textContent  = 'Save Changes';
    document.getElementById('acc-username').value = acc.email.split('@')[0];
    document.getElementById('acc-username').disabled = true;
    document.getElementById('acc-password').value = '';
    document.getElementById('acc-quota').value   = acc.quota_mb;
    document.getElementById('acc-admin').checked = acc.is_admin;
    document.getElementById('acc-active').checked = acc.is_active;
    document.getElementById('password-group').querySelector('label').textContent = 'New Password (leave blank to keep)';
    document.getElementById('active-group').classList.remove('hidden');
    document.getElementById('modal-error').classList.add('hidden');
    accountModal.classList.remove('hidden');
  }

  document.getElementById('new-account-btn').addEventListener('click', openCreateModal);
  document.getElementById('modal-close').addEventListener('click',  () => accountModal.classList.add('hidden'));
  document.getElementById('modal-cancel').addEventListener('click', () => accountModal.classList.add('hidden'));

  document.getElementById('modal-save').addEventListener('click', async () => {
    const saveBtn   = document.getElementById('modal-save');
    const modalErr  = document.getElementById('modal-error');
    const username  = document.getElementById('acc-username').value.trim();
    const password  = document.getElementById('acc-password').value;
    const quotaMb   = parseInt(document.getElementById('acc-quota').value);
    const isAdmin   = document.getElementById('acc-admin').checked;
    const isActive  = document.getElementById('acc-active').checked;

    modalErr.classList.add('hidden');

    if (!editingId && (!username || !password)) {
      modalErr.textContent = 'Username and password are required.'; modalErr.classList.remove('hidden'); return;
    }
    if (!editingId && password.length < 8) {
      modalErr.textContent = 'Password must be at least 8 characters.'; modalErr.classList.remove('hidden'); return;
    }

    saveBtn.disabled = true; saveBtn.textContent = 'Saving…';

    try {
      if (!editingId) {
        // Create
        await DMFMail.post('/api/accounts', {
          email:     `${username}@dutchforcesrp.nl`,
          password,
          is_admin:  isAdmin,
          quota_mb:  quotaMb,
        });
      } else {
        // Update
        const payload = { quota_mb: quotaMb, is_admin: isAdmin, is_active: isActive };
        if (password) payload.password = password;
        await DMFMail.put(`/api/accounts/${editingId}`, payload);
      }
      accountModal.classList.add('hidden');
      await loadAccounts();
    } catch (err) {
      modalErr.textContent = err.message; modalErr.classList.remove('hidden');
    } finally {
      saveBtn.disabled = false; saveBtn.textContent = editingId ? 'Save Changes' : 'Create Account';
    }
  });

  // ── Delete modal ──────────────────────────────────────────────────────
  let deleteTargetId = null;

  function openDeleteModal(id, email) {
    deleteTargetId = id;
    document.getElementById('delete-email-label').textContent = email;
    deleteModal.classList.remove('hidden');
  }

  document.getElementById('delete-cancel').addEventListener('click',  () => deleteModal.classList.add('hidden'));

  document.getElementById('delete-confirm').addEventListener('click', async () => {
    const btn = document.getElementById('delete-confirm');
    btn.disabled = true; btn.textContent = 'Deleting…';
    try {
      await DMFMail.del(`/api/accounts/${deleteTargetId}`);
      deleteModal.classList.add('hidden');
      await loadAccounts();
    } catch (err) {
      alert(err.message);
    } finally {
      btn.disabled = false; btn.textContent = 'Delete';
    }
  });

  // ── Init ──────────────────────────────────────────────────────────────
  await loadAccounts();
});
