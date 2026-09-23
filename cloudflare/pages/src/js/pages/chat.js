// cloudflare/pages/src/js/pages/chat.js — Multi-turn Chat AI + Source Selector (Phase 3, <250 dòng)
import { chatApi } from '../api.js';
import { showToast, onTabActivate } from '../app.js';
import { subscribeMessages } from '../realtime.js';
import { CITATION_STYLES } from '../constants.js';

let _sessions = [];
let _currentId = null;
let _messages = [];
let _knownIds = new Set();
let _unsubscribe = null;
let _selectedSources = new Set();
let _sourcesLoaded = false;

function esc(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function parseJsonArray(v) {
  if (typeof v === 'string') { try { return JSON.parse(v); } catch { return []; } }
  return Array.isArray(v) ? v : [];
}

// ---------- Shell ----------
function renderShell() {
  const root = document.getElementById('chat-root');
  if (!root || root.dataset.ready) return;
  root.dataset.ready = '1';
  root.innerHTML = `
    <div style="display:grid; grid-template-columns:260px 1fr; gap:16px; align-items:start">
      <div>
        <button class="btn btn-primary" id="btn-new-session" style="width:100%">＋ Phiên chat mới</button>
        <div id="session-list" style="margin-top:12px; display:flex; flex-direction:column; gap:8px"></div>
      </div>
      <div class="card" style="min-height:480px; display:flex; flex-direction:column">
        <div class="flex gap-2" style="align-items:center; margin-bottom:8px; flex-wrap:wrap">
          <strong id="chat-title" style="flex:1">Chọn hoặc tạo phiên chat</strong>
          <select id="chat-citation-style" class="btn btn-ghost btn-sm">
            ${CITATION_STYLES.map((s) => `<option value="${s.value}">Trích dẫn: ${s.label}</option>`).join('')}
          </select>
          <button class="btn btn-ghost btn-sm" id="btn-toggle-sources">📚 Nguồn (<span id="source-count">0</span>)</button>
          <button class="btn btn-danger btn-sm" id="btn-delete-session" title="Xoá phiên">🗑</button>
        </div>
        <div id="source-panel" class="hidden"
             style="border:1px solid var(--border); border-radius:var(--r-sm); padding:8px; margin-bottom:8px; max-height:160px; overflow-y:auto"></div>
        <div id="chat-messages"
             style="flex:1; overflow-y:auto; max-height:420px; min-height:280px; display:flex; flex-direction:column; gap:8px; padding:4px"></div>
        <div class="flex gap-2 mt-4">
          <input id="chat-input" type="text" placeholder="Nhập câu hỏi cho NotebookLM..."
                 style="flex:1; background:var(--bg-elevated); border:1px solid var(--border); border-radius:var(--r-sm); padding:8px 12px; color:var(--text); font-family:inherit; font-size:0.875rem">
          <button class="btn btn-primary" id="btn-send-chat">Gửi →</button>
        </div>
      </div>
    </div>`;

  document.getElementById('btn-new-session').addEventListener('click', createSession);
  document.getElementById('btn-send-chat').addEventListener('click', sendPrompt);
  document.getElementById('btn-delete-session').addEventListener('click', deleteSession);
  document.getElementById('btn-toggle-sources').addEventListener('click', toggleSourcePanel);
  document.getElementById('chat-input').addEventListener('keydown', (e) => { if (e.key === 'Enter') sendPrompt(); });
}

// ---------- Session list ----------
async function loadSessions() {
  renderShell();
  const list = document.getElementById('session-list');
  try {
    const data = await chatApi.listSessions({ status: 'active' });
    _sessions = data.sessions || [];
    list.innerHTML = _sessions.length
      ? _sessions.map((s) => `
        <div class="card session-item" data-id="${s.id}"
             style="padding:10px; cursor:pointer; ${s.id === _currentId ? 'border-color:var(--accent)' : ''}">
          <div class="flex items-center gap-2" style="justify-content:space-between">
            <span style="font-size:0.85rem; font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">${esc(s.title) || 'Không tên'}</span>
            <button class="btn btn-ghost btn-sm btn-rename" data-id="${s.id}" title="Đổi tên">✏️</button>
          </div>
          <div class="text-muted" style="font-size:0.72rem">${s.message_count || 0} tin nhắn</div>
        </div>`).join('')
      : '<div class="text-muted" style="font-size:0.85rem">Chưa có phiên nào.</div>';
    list.querySelectorAll('.session-item').forEach((el) =>
      el.addEventListener('click', (e) => { if (!e.target.closest('.btn-rename')) selectSession(el.dataset.id); }));
    list.querySelectorAll('.btn-rename').forEach((btn) =>
      btn.addEventListener('click', () => renameSession(btn.dataset.id)));
    // Chỉ auto-select khi session có id hợp lệ — tránh loop GET /sessions/undefined
    if (!_currentId && _sessions.length && (_sessions[0].id || _sessions[0]._id)) {
      selectSession(_sessions[0].id || _sessions[0]._id);
    }
  } catch (err) {
    list.innerHTML = `<div class="text-danger">Lỗi: ${esc(err.message)}</div>`;
  }
}

async function createSession() {
  const title = prompt('Tên phiên chat mới:', `Chat ${new Date().toLocaleString('vi')}`);
  if (title === null) return;
  try {
    const { id } = await chatApi.createSession({ title, source_ids: [..._selectedSources] });
    showToast('Đã tạo phiên chat', 'success');
    _currentId = id;
    await loadSessions();
    selectSession(id);
  } catch (err) { showToast(`Tạo phiên thất bại: ${err.message}`, 'error'); }
}

async function renameSession(id) {
  const s = _sessions.find((x) => x.id === id);
  const title = prompt('Tên mới:', s?.title || '');
  if (!title) return;
  try {
    await chatApi.updateSession(id, { title });
    showToast('Đã đổi tên', 'success');
    loadSessions();
    if (id === _currentId) document.getElementById('chat-title').textContent = title;
  } catch (err) { showToast(`Đổi tên thất bại: ${err.message}`, 'error'); }
}

async function deleteSession() {
  if (!_currentId) { showToast('Chưa chọn phiên nào', 'error'); return; }
  if (!confirm('Xoá phiên chat này?')) return;
  const hard = confirm('Xoá VĨNH VIỄN cả messages?\nOK = xoá hẳn · Cancel = chỉ lưu trữ (archive)');
  try {
    await chatApi.deleteSession(_currentId, hard);
    showToast(hard ? 'Đã xoá vĩnh viễn' : 'Đã lưu trữ phiên', 'success');
    _unsubscribe?.(); _unsubscribe = null;
    _currentId = null; _messages = []; _knownIds.clear();
    document.getElementById('chat-messages').innerHTML = '';
    document.getElementById('chat-title').textContent = 'Chọn hoặc tạo phiên chat';
    loadSessions();
  } catch (err) { showToast(`Xoá thất bại: ${err.message}`, 'error'); }
}

// ---------- Source Selector ----------
async function toggleSourcePanel() {
  const panel = document.getElementById('source-panel');
  panel.classList.toggle('hidden');
  if (panel.classList.contains('hidden') || _sourcesLoaded) return;
  try {
    const { sources } = await chatApi.listSources();
    _sourcesLoaded = true;
    panel.innerHTML = (sources && sources.length)
      ? sources.map((s) => {
          const sid = s.source_id || s.file_id;
          return `
        <label class="flex items-center gap-2" style="font-size:0.82rem; padding:2px 0; cursor:pointer">
          <input type="checkbox" class="source-cb" value="${esc(sid)}" ${_selectedSources.has(sid) ? 'checked' : ''}>
          <span>${esc(s.filename)}</span>
          <span class="text-muted" style="font-size:0.72rem">(${esc(s.document_type || '')}${s.review_status === 'unreviewed' ? ' · 🟡 chờ duyệt' : ''})</span>
        </label>`;
        }).join('')
      : '<div class="text-muted">Chưa có nguồn nào đã đồng bộ.</div>';
    panel.querySelectorAll('.source-cb').forEach((cb) => cb.addEventListener('change', () => {
      if (cb.checked) _selectedSources.add(cb.value); else _selectedSources.delete(cb.value);
      document.getElementById('source-count').textContent = _selectedSources.size;
      if (_currentId) {
        chatApi.updateSession(_currentId, { selected_source_ids: [..._selectedSources] }).catch(() => {});
      }
    }));
  } catch (err) {
    panel.innerHTML = `<div class="text-danger">Lỗi tải nguồn: ${esc(err.message)}</div>`;
  }
}

// ---------- Messages ----------
function renderMessage(m) {
  const citations = parseJsonArray(m.citations);
  const isUser = m.role === 'user';
  const failed = m.status === 'failed';
  const align = isUser
    ? 'align-self:flex-end; background:var(--accent)22; border-color:var(--accent)'
    : 'align-self:flex-start';
  const citHtml = citations.length ? `
    <div class="citations-drawer" style="margin-top:6px">
      <button class="citations-toggle" onclick="this.nextElementSibling.classList.toggle('open')">📎 Trích dẫn (${citations.length}) ▸</button>
      <div class="citations-list">${citations.map((c) =>
        `<div>• ${esc(c.source_name || c.title || c.source_id || '')}${c.page ? ` trang ${c.page}` : ''}${c.quote ? `: "${esc(c.quote)}"` : ''}</div>`).join('')}
      </div>
    </div>` : '';
  const refHtml = m.reference_block
    ? `<div style="margin-top:8px; border-top:1px solid var(--border); padding-top:6px; font-size:0.8rem; white-space:pre-line; color:var(--text-muted)">${esc(m.reference_block)}</div>`
    : '';
  return `
    <div class="card" data-mid="${m.id}" style="max-width:85%; padding:10px 12px; ${align}">
      <div style="font-size:0.875rem; white-space:pre-line">${esc(m.content)}</div>
      ${failed ? '<div class="text-danger" style="font-size:0.75rem">✗ Gửi thất bại</div>' : ''}
      ${citHtml}${refHtml}
    </div>`;
}

function appendMessages(msgs) {
  const box = document.getElementById('chat-messages');
  if (!box) return;
  let added = false;
  for (const m of msgs) {
    if (_knownIds.has(m.id)) continue;
    _knownIds.add(m.id);
    _messages.push(m);
    box.insertAdjacentHTML('beforeend', renderMessage(m));
    added = true;
  }
  if (added) box.scrollTop = box.scrollHeight;
}

async function selectSession(id) {
  if (!id || id === 'undefined') return; // chặn loop 404 khi doc thiếu field id
  _currentId = id;
  _unsubscribe?.(); _unsubscribe = null;
  _messages = []; _knownIds.clear();
  const s = _sessions.find((x) => x.id === id);
  document.getElementById('chat-title').textContent = s?.title || 'Phiên chat';
  const box = document.getElementById('chat-messages');
  box.innerHTML = '<div class="text-muted">Đang tải hội thoại...</div>';
  loadSessions();
  try {
    const { session, messages } = await chatApi.getSession(id);
    box.innerHTML = '';
    parseJsonArray(session?.selected_source_ids).forEach((sid) => _selectedSources.add(sid));
    document.getElementById('source-count').textContent = _selectedSources.size;
    appendMessages(messages || []);
    _unsubscribe = subscribeMessages(id, {
      onMessages: appendMessages,
      onError: (err) => console.warn('[chat] realtime lỗi:', err.message),
    });
  } catch (err) {
    box.innerHTML = `<div class="text-danger">Lỗi: ${esc(err.message)}</div>`;
  }
}

async function sendPrompt() {
  const input = document.getElementById('chat-input');
  const content = input.value.trim();
  if (!content) return;
  if (!_currentId) { showToast('Hãy tạo/chọn phiên chat trước', 'error'); return; }
  input.value = '';
  const style = document.getElementById('chat-citation-style').value;
  try {
    await chatApi.sendMessage(_currentId, {
      content, source_ids: [..._selectedSources], citation_style: style,
    });
    // Polling (realtime.js) sẽ tự nhặt message mới; fetch ngay 1 lần cho nhanh
    const { messages } = await chatApi.getMessages(_currentId);
    appendMessages(messages || []);
  } catch (err) { showToast(`Gửi thất bại: ${err.message}`, 'error'); }
}

export function initChat() {
  onTabActivate('chat', () => { renderShell(); loadSessions(); });
}
