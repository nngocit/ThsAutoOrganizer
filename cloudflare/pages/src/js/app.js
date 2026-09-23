// cloudflare/pages/src/js/app.js — Google AI Studio & NotebookLM App Shell (<250 lines)
import { authApi, coursesApi, filesApi, insightsApi, setUnauthorizedHandler } from './api.js';

// Google OAuth 2.0 Client ID
const GOOGLE_CLIENT_ID = '437903639644-img3tmoj4hdji3nkocknmitmk197k3lv.apps.googleusercontent.com';

/** Decode exp (giây) từ JWT */
function decodeTokenExp(token) {
  try {
    const part = (token || '').split('.')[1];
    const payload = JSON.parse(atob(part.replace(/-/g, '+').replace(/_/g, '/')));
    return Number(payload.exp) || 0;
  } catch { return 0; }
}

/** Token còn dùng được (còn hạn > 30s nữa)? */
function isTokenUsable(token) {
  return !!token && decodeTokenExp(token) > Math.floor(Date.now() / 1000) + 30;
}

// ============================
// Toast Notifications
// ============================
export function showToast(message, type = 'info', duration = 3500) {
  const container = document.getElementById('toast-container');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateY(10px)';
    toast.style.transition = 'all 0.3s ease';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}

// ============================
// Theme Switcher (Dark / Light)
// ============================
function initTheme() {
  const saved = localStorage.getItem('ths_theme') || 'dark';
  applyTheme(saved);

  const toggleBtn = document.getElementById('theme-toggle-btn');
  if (toggleBtn) {
    toggleBtn.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme') || 'dark';
      const next = current === 'dark' ? 'light' : 'dark';
      applyTheme(next);
      localStorage.setItem('ths_theme', next);
      showToast(`Đã chuyển sang giao diện ${next === 'dark' ? 'Tối (Studio Dark)' : 'Sáng (Studio Light)'}`, 'info', 2000);
    });
  }
}

function applyTheme(theme) {
  document.documentElement.setAttribute('data-theme', theme);
  const toggleBtn = document.getElementById('theme-toggle-btn');
  if (toggleBtn) {
    toggleBtn.textContent = theme === 'dark' ? '☀️' : '🌙';
    toggleBtn.title = theme === 'dark' ? 'Chuyển sang giao diện Sáng' : 'Chuyển sang giao diện Tối';
  }
}

// ============================
// Studio 3-Column Layout & Panels
// ============================
function initStudioLayout() {
  const toggleStudioBtn = document.getElementById('btn-toggle-studio-panel');
  const studioBody = document.getElementById('studio-body');
  if (toggleStudioBtn && studioBody) {
    toggleStudioBtn.addEventListener('click', () => {
      studioBody.classList.toggle('studio-collapsed');
    });
  }

  const addSourceBtn = document.getElementById('btn-quick-add-source');
  if (addSourceBtn) {
    addSourceBtn.addEventListener('click', () => {
      activateTab('dashboard');
      document.getElementById('upload-area')?.scrollIntoView({ behavior: 'smooth' });
    });
  }
}

// ============================
// Global Course & Sources Sync
// ============================
export async function loadGlobalCourses() {
  const select = document.getElementById('global-course-select');
  if (!select) return;
  try {
    const data = await coursesApi.list();
    const courses = (data.courses || []).filter(c => c.kind === 'subject');
    select.innerHTML = '<option value="">-- Tất cả môn học --</option>' +
      courses.map(c => {
        const id = c.id || c._id;
        const tag = (c.notebook_id || c.notebooklm_id) ? ' (✓ NLM)' : '';
        return `<option value="${id}">${c.name || c.folder_name}${tag}</option>`;
      }).join('');

    // Ưu tiên chọn môn có NLM nếu chưa chọn gì
    if (!window._activeCourseId) {
      const linked = courses.find(c => c.notebook_id || c.notebooklm_id);
      if (linked) {
        window._activeCourseId = linked.id || linked._id;
        select.value = window._activeCourseId;
      }
    } else {
      select.value = window._activeCourseId;
    }

    await onCourseChanged(select.value);
  } catch (err) {
    console.warn('Lỗi tải danh sách môn học toàn cục:', err);
  }
}

async function onCourseChanged(courseId) {
  window._activeCourseId = courseId;
  const listEl = document.getElementById('panel-sources-list');
  const recentEl = document.getElementById('studio-recent-items');
  if (!listEl) return;

  listEl.innerHTML = '<div class="text-muted" style="padding:8px; font-size:0.8rem">Đang nạp nguồn...</div>';

  try {
    // 1. Nạp file nguồn
    const { files } = await filesApi.list({ course_id: courseId });
    if (!files || !files.length) {
      listEl.innerHTML = '<div class="text-muted" style="padding:8px; font-size:0.8rem">Chưa có tài liệu nào. Bấm ＋ Thêm để tải lên.</div>';
    } else {
      listEl.innerHTML = files.map(f => {
        const fid = f.id || f._id;
        const isSynced = f.notebooklm_sync_status === 'synced';
        const badgeColor = isSynced ? 'var(--success)' : 'var(--warning)';
        return `
          <label class="source-item" title="${f.filename}">
            <input type="checkbox" class="global-source-cb" value="${fid}" checked>
            <span style="color:${badgeColor}; font-size:0.75rem">●</span>
            <span class="source-name">${f.filename}</span>
          </label>`;
      }).join('');
    }

    // 2. Nạp ấn phẩm gần đây ở cột Studio
    if (recentEl) {
      const { insights } = await insightsApi.list({ course_id: courseId, limit: 10 });
      if (!insights || !insights.length) {
        recentEl.innerHTML = '<div class="text-muted" style="font-size:0.75rem">Chưa có ấn phẩm nào.</div>';
      } else {
        recentEl.innerHTML = insights.map(ins => `
          <div class="card cursor-pointer studio-recent-card" data-id="${ins.id}" style="padding:8px; font-size:0.78rem; cursor:pointer" title="Bấm để xem trong Study Hub">
            <div style="font-weight:600; overflow:hidden; text-overflow:ellipsis; white-space:nowrap">${ins.title}</div>
            <div class="text-muted" style="font-size:0.7rem; margin-top:2px">${ins.insight_type}</div>
          </div>`).join('');
        recentEl.querySelectorAll('.studio-recent-card').forEach(card => {
          card.addEventListener('click', () => {
            activateTab('study-hub');
            const target = document.getElementById(`insight-${card.dataset.id}`);
            if (target) {
              target.scrollIntoView({ behavior: 'smooth', block: 'center' });
              target.style.boxShadow = '0 0 0 2px var(--accent)';
              setTimeout(() => { target.style.boxShadow = ''; }, 2000);
            }
          });
        });
      }
    }

    // 3. Đồng bộ dropdown ở các tab nếu có
    const qrSelect = document.getElementById('quick-research-course');
    if (qrSelect && courseId) qrSelect.value = courseId;
    const examSelect = document.getElementById('exam-course');
    if (examSelect && courseId) examSelect.value = courseId;
  } catch (err) {
    listEl.innerHTML = `<div class="text-danger" style="padding:8px; font-size:0.8rem">Lỗi: ${err.message}</div>`;
  }
}

// ============================
// Tab Router
// ============================
const _tabHandlers = {};

export function onTabActivate(tabId, handler) {
  _tabHandlers[tabId] = handler;
}

function activateTab(tabId) {
  document.querySelectorAll('.nav-tab').forEach((t) => {
    t.classList.toggle('active', t.dataset.tab === tabId);
  });
  document.querySelectorAll('.page-section').forEach((s) => {
    s.classList.toggle('active', s.id === `page-${tabId}`);
  });
  window.__onTabActivate?.(tabId);
}

// ============================
// Auth State
// ============================
let _currentUser = null;
export function getCurrentUser() { return _currentUser; }

function renderAuthScreen() {
  document.getElementById('auth-screen')?.classList.remove('hidden');
  document.getElementById('app-shell')?.classList.add('hidden');
}

function renderApp(user) {
  _currentUser = user;
  document.getElementById('auth-screen')?.classList.add('hidden');
  document.getElementById('app-shell')?.classList.remove('hidden');

  const avatarEl = document.getElementById('user-avatar');
  const nameEl = document.getElementById('user-name');
  if (avatarEl && user.picture) avatarEl.src = user.picture;
  if (nameEl) nameEl.textContent = user.name || user.email;

  loadGlobalCourses();
  activateTab('dashboard');
}

// ============================
// Google Sign-In handlers
// ============================
window.handleGoogleCredentialResponse = async function (response) {
  const idToken = response.credential;
  window._googleIdToken = idToken;
  localStorage.setItem('ths_google_id_token', idToken);

  try {
    const user = await authApi.login(idToken);
    localStorage.setItem('ths_user_data', JSON.stringify(user));
    renderApp(user);
    showToast(`Chào mừng, ${user.name || user.email}!`, 'success');
  } catch (err) {
    showToast(`Đăng nhập thất bại: ${err.message}`, 'error');
    signOut();
  }
};

function signOut() {
  window._googleIdToken = null;
  _currentUser = null;
  localStorage.removeItem('ths_google_id_token');
  localStorage.removeItem('ths_user_data');
  renderAuthScreen();
  showToast('Đã đăng xuất.', 'info');
}

function handleSessionExpired() {
  window._googleIdToken = null;
  _currentUser = null;
  localStorage.removeItem('ths_google_id_token');
  localStorage.removeItem('ths_user_data');
  renderAuthScreen();
  showToast('Phiên đăng nhập đã hết hạn — đang đăng nhập lại...', 'error', 6000);
  try { google.accounts.id.prompt(); } catch {}
}
setUnauthorizedHandler(handleSessionExpired);

// ============================
// NLM Status
// ============================
async function checkNLMStatus() {
  const badge = document.getElementById('nlm-status-badge');
  if (!badge) return;
  try {
    const resp = await fetch('https://ths-organizer-api.ths-organizer-nngocit.workers.dev/health');
    const data = await resp.json();
    if (data.status === 'ok') {
      badge.className = 'nlm-status-badge connected';
      badge.innerHTML = '<span class="badge-dot"></span> NotebookLM Plus ✓';
    }
  } catch {
    badge.className = 'nlm-status-badge needs-login';
    badge.innerHTML = '<span class="badge-dot"></span> Worker offline';
  }
}

// ============================
// Init
// ============================
document.addEventListener('DOMContentLoaded', () => {
  initTheme();
  initStudioLayout();

  const courseSelect = document.getElementById('global-course-select');
  if (courseSelect) {
    courseSelect.addEventListener('change', (e) => onCourseChanged(e.target.value));
  }

  const addSourceBtn = document.getElementById('btn-quick-add-source');
  if (addSourceBtn) {
    addSourceBtn.addEventListener('click', () => {
      activateTab('dashboard');
      document.getElementById('upload-area')?.scrollIntoView({ behavior: 'smooth' });
    });
  }

  document.querySelectorAll('.nav-tab').forEach((tab) => {
    tab.addEventListener('click', () => activateTab(tab.dataset.tab));
  });

  const signOutBtn = document.getElementById('btn-sign-out');
  if (signOutBtn) signOutBtn.addEventListener('click', signOut);

  const script = document.createElement('script');
  script.src = 'https://accounts.google.com/gsi/client';
  script.async = true;
  script.defer = true;
  script.onload = () => {
    if (window.google?.accounts?.id) {
      google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: window.handleGoogleCredentialResponse,
        auto_select: true,
        cancel_on_tap_outside: false,
      });
      google.accounts.id.renderButton(
        document.getElementById('google-signin-btn'),
        { theme: 'outline', size: 'large', type: 'standard', shape: 'rectangular', text: 'signin_with' }
      );
      google.accounts.id.prompt();
    }
    const savedToken = localStorage.getItem('ths_google_id_token');
    const savedUser = localStorage.getItem('ths_user_data');

    if (savedToken && savedUser && isTokenUsable(savedToken)) {
      try {
        window._googleIdToken = savedToken;
        const user = JSON.parse(savedUser);
        renderApp(user);
      } catch (e) {
        signOut();
      }
    } else if (savedToken || savedUser) {
      localStorage.removeItem('ths_google_id_token');
      localStorage.removeItem('ths_user_data');
      renderAuthScreen();
      google.accounts.id.prompt();
    } else {
      renderAuthScreen();
    }
  };
  document.head.appendChild(script);

  setTimeout(checkNLMStatus, 2000);

  window.activateTab = activateTab;
  window.__onTabActivate = (tabId) => { _tabHandlers[tabId]?.(tabId); };
});
