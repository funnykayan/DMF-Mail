/**
 * DMF Mail – webmail page logic (webmail.js)
 */

document.addEventListener('DOMContentLoaded', async () => {
  DMFMail.requireAuth();

  let currentFolder = 'INBOX';
  let currentOffset = 0;
  const PAGE_SIZE = 50;
  let allMessages = [];
  let currentMsg  = null;

  // ── Elements ─────────────────────────────────────────────────────────
  const mailList      = document.getElementById('mail-list');
  const folderTitle   = document.getElementById('folder-title');
  const listPanel     = document.getElementById('mail-list-panel');
  const viewPanel     = document.getElementById('mail-view-panel');
  const viewContent   = document.getElementById('mail-view-content');
  const inboxCount    = document.getElementById('inbox-count');
  const pagination    = document.getElementById('pagination');
  const listLoading   = document.getElementById('mail-list-loading');
  const listEmpty     = document.getElementById('mail-list-empty');

  // ── Folder navigation ─────────────────────────────────────────────────
  document.querySelectorAll('.nav-item[data-folder]').forEach(el => {
    el.addEventListener('click', (e) => {
      e.preventDefault();
      document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'));
      el.classList.add('active');
      currentFolder = el.dataset.folder;
      currentOffset = 0;
      folderTitle.textContent = el.textContent.trim().replace(/\d+$/, '').trim();
      loadMailList();
      showListPanel();
    });
  });

  // ── Load mail list ────────────────────────────────────────────────────
  async function loadMailList() {
    const pw = DMFMail.getPassword();
    if (!pw) { showPasswordPrompt(); return; }

    listLoading.classList.remove('hidden');
    listEmpty.classList.add('hidden');
    mailList.innerHTML = '';
    pagination.innerHTML = '';

    try {
      const data = await DMFMail.get(
        `/api/mail/inbox?folder=${encodeURIComponent(currentFolder)}&limit=${PAGE_SIZE}&offset=${currentOffset}&password=${encodeURIComponent(pw)}`
      );
      allMessages = data.messages || [];
      renderMailList(allMessages);
    } catch (err) {
      mailList.innerHTML = `<div class="error-msg" style="margin:16px">${DMFMail.esc(err.message)}</div>`;
    } finally {
      listLoading.classList.add('hidden');
    }
  }

  function renderMailList(messages) {
    mailList.innerHTML = '';
    if (messages.length === 0) {
      listEmpty.classList.remove('hidden');
      return;
    }
    listEmpty.classList.add('hidden');
    messages.forEach((msg, idx) => {
      const item = document.createElement('div');
      item.className = 'mail-item';
      item.dataset.idx = idx;
      item.innerHTML = `
        <div class="mail-item-from">${DMFMail.esc(msg.from)}</div>
        <div class="mail-item-subject">${DMFMail.esc(msg.subject)}</div>
        <div class="mail-item-date">${DMFMail.esc(DMFMail.formatDate(msg.date))}</div>
      `;
      item.addEventListener('click', () => openMessage(msg, item));
      mailList.appendChild(item);
    });

    // Pagination
    if (currentOffset > 0) {
      const prev = document.createElement('button');
      prev.className = 'btn btn-ghost btn-sm'; prev.textContent = '← Prev';
      prev.addEventListener('click', () => { currentOffset -= PAGE_SIZE; loadMailList(); });
      pagination.appendChild(prev);
    }
    if (messages.length === PAGE_SIZE) {
      const next = document.createElement('button');
      next.className = 'btn btn-ghost btn-sm'; next.textContent = 'Next →';
      next.addEventListener('click', () => { currentOffset += PAGE_SIZE; loadMailList(); });
      pagination.appendChild(next);
    }
  }

  function openMessage(msg, itemEl) {
    document.querySelectorAll('.mail-item').forEach(el => el.classList.remove('active'));
    itemEl.classList.add('active');
    currentMsg = msg;
    showViewPanel();

    const isHtml = /<[a-z][\s\S]*>/i.test(msg.body);

    viewContent.innerHTML = `
      <div class="mail-view-header">
        <h2>${DMFMail.esc(msg.subject)}</h2>
        <div class="mail-meta-row"><strong>From:</strong> ${DMFMail.esc(msg.from)}</div>
        <div class="mail-meta-row"><strong>To:</strong> ${DMFMail.esc(msg.to)}</div>
        <div class="mail-meta-row"><strong>Date:</strong> ${DMFMail.esc(msg.date)}</div>
      </div>
      <div class="mail-body" id="mail-body-content"></div>
    `;

    const bodyEl = document.getElementById('mail-body-content');
    if (isHtml) {
      const iframe = document.createElement('iframe');
      iframe.sandbox = 'allow-same-origin';
      iframe.style.cssText = 'width:100%;min-height:500px;border:none;background:#fff;border-radius:8px;';
      bodyEl.appendChild(iframe);
      const doc = iframe.contentDocument || iframe.contentWindow.document;
      doc.open(); doc.write(msg.body); doc.close();
    } else {
      bodyEl.textContent = msg.body;
    }
  }

  // ── Panel switching ───────────────────────────────────────────────────
  function showListPanel() {
    listPanel.style.display = 'flex';
    viewPanel.classList.add('hidden');
  }

  function showViewPanel() {
    viewPanel.classList.remove('hidden');
  }

  document.getElementById('back-btn').addEventListener('click', () => {
    viewPanel.classList.add('hidden');
    document.querySelectorAll('.mail-item').forEach(el => el.classList.remove('active'));
    currentMsg = null;
  });

  // ── Refresh ───────────────────────────────────────────────────────────
  document.getElementById('refresh-btn').addEventListener('click', () => loadMailList());

  // ── Compose ───────────────────────────────────────────────────────────
  const composeModal  = document.getElementById('compose-modal');
  const composeTo     = document.getElementById('compose-to');
  const composeCc     = document.getElementById('compose-cc');
  const composeSubj   = document.getElementById('compose-subject');
  const composeBody   = document.getElementById('compose-body');
  const composeError  = document.getElementById('compose-error');

  function openCompose(replyTo = null) {
    composeTo.value   = replyTo ? (replyTo.from || '') : '';
    composeCc.value   = '';
    composeSubj.value = replyTo ? `Re: ${replyTo.subject}` : '';
    composeBody.value = replyTo ? `\n\n--- Original Message ---\nFrom: ${replyTo.from}\n${replyTo.body}` : '';
    composeError.classList.add('hidden');
    composeModal.classList.remove('hidden');
    composeTo.focus();
  }

  document.getElementById('compose-btn').addEventListener('click', () => openCompose());
  document.getElementById('compose-close').addEventListener('click', () => composeModal.classList.add('hidden'));
  document.getElementById('compose-cancel').addEventListener('click', () => composeModal.classList.add('hidden'));

  document.getElementById('reply-btn').addEventListener('click', () => {
    if (currentMsg) openCompose(currentMsg);
  });

  document.getElementById('compose-send').addEventListener('click', async () => {
    const sendBtn = document.getElementById('compose-send');
    const pw = DMFMail.getPassword();
    if (!pw) { composeError.textContent = 'Session expired. Please log in again.'; composeError.classList.remove('hidden'); return; }

    const toRaw = composeTo.value.trim();
    const ccRaw = composeCc.value.trim();
    if (!toRaw) { composeError.textContent = '"To" field is required.'; composeError.classList.remove('hidden'); return; }
    if (!composeSubj.value.trim()) { composeError.textContent = 'Subject is required.'; composeError.classList.remove('hidden'); return; }

    sendBtn.disabled = true; sendBtn.textContent = 'Sending…';
    composeError.classList.add('hidden');

    try {
      await DMFMail.post('/api/mail/send', {
        to:       toRaw.split(',').map(s => s.trim()).filter(Boolean),
        cc:       ccRaw ? ccRaw.split(',').map(s => s.trim()).filter(Boolean) : [],
        subject:  composeSubj.value.trim(),
        body:     composeBody.value,
        password: pw,
      });
      composeModal.classList.add('hidden');
      composeTo.value = composeCc.value = composeSubj.value = composeBody.value = '';
    } catch (err) {
      composeError.textContent = err.message;
      composeError.classList.remove('hidden');
    } finally {
      sendBtn.disabled = false; sendBtn.textContent = 'Send';
    }
  });

  // ── Password prompt (if session cleared) ─────────────────────────────
  function showPasswordPrompt() {
    const pw = prompt('Enter your mail password to continue:');
    if (pw) {
      sessionStorage.setItem('dmf_password', pw);
      loadMailList();
    }
  }

  // ── Init ──────────────────────────────────────────────────────────────
  await loadMailList();
});
