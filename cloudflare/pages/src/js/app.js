// cloudflare/pages/src/js/app.js — Google Sign-In + tab router + auth state (<200 lines)
import { authApi } from './api.js';

// Google OAuth 2.0 Client ID
const GOOGLE_CLIENT_ID = 'YOUR_GOOGLE_CLIENT_ID.apps.googleusercontent.com';

// ============================
// Toast Notifications
// ============================

export function showToast(message, type = 'info', duration = 3500) {
  const container = document.getElementById('toast-container');
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
// Tab Router
// ============================

function activateTab(tabId) {
  // Update nav tabs
  document.querySelectorAll('.nav-tab').forEach((t) => {
    t.classList.toggle('active', t.dataset.tab === tabId);
  });
  // Update page sections
  document.querySelectorAll('.page-section').forEach((s) => {
    s.classList.toggle('active', s.id === `page-${tabId}`);
  });
  // Lazy-load page data
  window.__onTabActivate?.(tabId);
}

// ============================
// Auth State
// ============================

let _currentUser = null;

export function getCurrentUser() { return _currentUser; }

function renderAuthScreen() {
  document.getElementById('auth-screen').classList.remove('hidden');
  document.getElementById('app-shell').classList.add('hidden');
}

function renderApp(user) {
  _currentUser = user;
  document.getElementById('auth-screen').classList.add('hidden');
  document.getElementById('app-shell').classList.remove('hidden');
  // Update user info in topbar
  const avatarEl = document.getElementById('user-avatar');
  const nameEl = document.getElementById('user-name');
  if (avatarEl && user.picture) avatarEl.src = user.picture;
  if (nameEl) nameEl.textContent = user.name || user.email;
  // Activate default tab
  activateTab('dashboard');
}

// ============================
// Google Sign-In handlers
// ============================

window.handleGoogleCredentialResponse = async function (response) {
  const idToken = response.credential;
  window._googleIdToken = idToken;  // Store for API calls
  try {
    const user = await authApi.login(idToken);
    renderApp(user);
    showToast(`Chào mừng, ${user.name || user.email}!`, 'success');
  } catch (err) {
    showToast(`Đăng nhập thất bại: ${err.message}`, 'error');
    window._googleIdToken = null;
  }
};

function signOut() {
  window._googleIdToken = null;
  _currentUser = null;
  renderAuthScreen();
  showToast('Đã đăng xuất.', 'info');
}

// ============================
// NLM Connection Badge
// ============================

async function checkNLMStatus() {
  const badge = document.getElementById('nlm-status-badge');
  if (!badge) return;

  // Kiểm tra Worker health (Worker sẽ check NLM status từ Firestore user profile)
  try {
    const resp = await fetch('https://ths-organizer-api.workers.dev/health');
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
  // Tab navigation click handlers
  document.querySelectorAll('.nav-tab').forEach((tab) => {
    tab.addEventListener('click', () => activateTab(tab.dataset.tab));
  });

  // Sign out button
  const signOutBtn = document.getElementById('btn-sign-out');
  if (signOutBtn) signOutBtn.addEventListener('click', signOut);

  // Load Google Sign-In SDK
  const script = document.createElement('script');
  script.src = 'https://accounts.google.com/gsi/client';
  script.async = true;
  script.defer = true;
  script.onload = () => {
    if (window.google?.accounts?.id) {
      google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: window.handleGoogleCredentialResponse,
        auto_select: true,   // Auto sign-in nếu đã đăng nhập trước đó
        cancel_on_tap_outside: false,
      });
      google.accounts.id.renderButton(
        document.getElementById('google-signin-btn'),
        { theme: 'outline', size: 'large', type: 'standard', shape: 'rectangular', text: 'signin_with' }
      );
      google.accounts.id.prompt();   // Show One Tap nếu có session cũ
    }
  };
  document.head.appendChild(script);

  // Check NLM status sau khi tải xong
  setTimeout(checkNLMStatus, 2000);

  // Expose activateTab để các pages có thể navigate
  window.activateTab = activateTab;
});
