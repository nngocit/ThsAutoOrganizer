// cloudflare/pages/src/js/pages/settings.js — Global Settings & System Logs Dashboard
import { settingsApi, logsApi } from '../api.js';
import { showToast } from '../app.js';

let _activeLogs = [];
let _selectedLog = null;

/**
 * Khởi tạo module Cài đặt & Giám sát hệ thống
 */
export function initSettings() {
  const form = document.getElementById('settings-form');
  const refreshBtn = document.getElementById('btn-refresh-logs');
  const levelFilter = document.getElementById('filter-log-level');
  const statusFilter = document.getElementById('filter-log-status');
  const modalCloseBtn = document.getElementById('btn-close-log-modal');
  const modalResolveBtn = document.getElementById('btn-modal-resolve-log');

  if (form) {
    form.addEventListener('submit', handleSaveSettings);
  }

  if (refreshBtn) {
    refreshBtn.addEventListener('click', () => loadSystemLogs());
  }

  if (levelFilter) {
    levelFilter.addEventListener('change', () => loadSystemLogs());
  }

  if (statusFilter) {
    statusFilter.addEventListener('change', () => loadSystemLogs());
  }

  if (modalCloseBtn) {
    modalCloseBtn.addEventListener('click', closeLogModal);
  }

  if (modalResolveBtn) {
    modalResolveBtn.addEventListener('click', handleResolveFromModal);
  }

  // Lắng nghe khi tab Settings được kích hoạt
  const originalOnTab = window.__onTabActivate;
  window.__onTabActivate = (tabId) => {
    if (typeof originalOnTab === 'function') originalOnTab(tabId);
    if (tabId === 'settings') {
      loadSystemConfig();
      loadSystemLogs();
    }
  };

  // Nạp lần đầu nếu đang ở trang settings
  const currentTab = document.querySelector('.nav-tab.active')?.dataset?.tab;
  if (currentTab === 'settings') {
    loadSystemConfig();
    loadSystemLogs();
  }
}

/**
 * Nạp cấu hình hệ thống từ Worker API
 */
async function loadSystemConfig() {
  const statusEl = document.getElementById('settings-status');
  if (statusEl) statusEl.textContent = 'Đang tải cấu hình...';

  try {
    const config = await settingsApi.getConfig();
    if (!config) return;

    const localBasePathInput = document.getElementById('cfg-local-base-path');
    const driveRootIdInput = document.getElementById('cfg-drive-root-id');
    const driveRootNameInput = document.getElementById('cfg-drive-root-name');
    const pollIntervalInput = document.getElementById('cfg-poll-interval');
    const watcherCb = document.getElementById('cfg-file-watcher-enabled');
    const autoSyncNlmCb = document.getElementById('cfg-auto-sync-nlm');

    if (localBasePathInput) localBasePathInput.value = config.local_base_path || '';
    if (driveRootIdInput) driveRootIdInput.value = config.google_drive_root_folder_id || '';
    if (driveRootNameInput) driveRootNameInput.value = config.google_drive_root_name || '02_Mon_Hoc';
    if (pollIntervalInput) pollIntervalInput.value = config.poll_interval_seconds || 10;
    if (watcherCb) watcherCb.checked = config.file_watcher_enabled !== false;
    if (autoSyncNlmCb) autoSyncNlmCb.checked = config.auto_sync_nlm !== false;

    if (statusEl) {
      statusEl.textContent = config.updated_at 
        ? `Đồng bộ lần cuối: ${new Date(config.updated_at).toLocaleString('vi-VN')}`
        : 'Đã sẵn sàng';
    }
  } catch (err) {
    console.warn('Lỗi nạp system config:', err);
    if (statusEl) statusEl.textContent = 'Chưa tải được cấu hình';
  }
}

/**
 * Lưu cấu hình hệ thống lên Firestore
 */
async function handleSaveSettings(e) {
  e.preventDefault();
  const saveBtn = document.getElementById('btn-save-settings');
  const statusEl = document.getElementById('settings-status');

  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<span class="loading-spinner"></span> Đang lưu...';
  }

  const payload = {
    local_base_path: document.getElementById('cfg-local-base-path')?.value?.trim() || '',
    google_drive_root_folder_id: document.getElementById('cfg-drive-root-id')?.value?.trim() || '',
    google_drive_root_name: document.getElementById('cfg-drive-root-name')?.value?.trim() || '02_Mon_Hoc',
    poll_interval_seconds: parseInt(document.getElementById('cfg-poll-interval')?.value, 10) || 10,
    file_watcher_enabled: document.getElementById('cfg-file-watcher-enabled')?.checked ?? true,
    auto_sync_nlm: document.getElementById('cfg-auto-sync-nlm')?.checked ?? true,
  };

  try {
    const res = await settingsApi.updateConfig(payload);
    showToast('✓ Cấu hình đã được lưu và đồng bộ toàn hệ thống!', 'success');
    if (statusEl) {
      statusEl.textContent = `Đã lưu: ${new Date(res.updated_at || Date.now()).toLocaleTimeString('vi-VN')}`;
    }
  } catch (err) {
    showToast(`Lỗi lưu cấu hình: ${err.message}`, 'error');
  } finally {
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.innerHTML = '💾 Lưu Cấu hình';
    }
  }
}

/**
 * Nạp danh sách nhật ký sự cố
 */
async function loadSystemLogs() {
  const container = document.getElementById('logs-table-body');
  const refreshBtn = document.getElementById('btn-refresh-logs');
  const levelFilter = document.getElementById('filter-log-level')?.value || '';
  const statusFilter = document.getElementById('filter-log-status')?.value || '';

  if (refreshBtn) refreshBtn.classList.add('loading-spinner');
  if (container) {
    container.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:24px; color:var(--text-muted)">Đang kiểm tra nhật ký...</td></tr>`;
  }

  try {
    const params = { limit: 100 };
    if (levelFilter) params.level = levelFilter;
    if (statusFilter) params.resolved = statusFilter;

    const data = await logsApi.list(params);
    _activeLogs = data.logs || [];
    renderLogsTable(_activeLogs);
  } catch (err) {
    console.error('Lỗi nạp logs:', err);
    if (container) {
      container.innerHTML = `<tr><td colspan="6" style="text-align:center; padding:20px; color:var(--danger)">Lỗi tải nhật ký: ${err.message}</td></tr>`;
    }
  } finally {
    if (refreshBtn) refreshBtn.classList.remove('loading-spinner');
  }
}

/**
 * Render bảng System Logs
 */
function renderLogsTable(logs) {
  const container = document.getElementById('logs-table-body');
  const countBadge = document.getElementById('logs-count-badge');
  if (!container) return;

  if (countBadge) {
    const unresolvedCount = logs.filter(l => !l.resolved).length;
    countBadge.textContent = unresolvedCount > 0 ? `${unresolvedCount} sự cố` : `${logs.length} bản ghi`;
    countBadge.className = unresolvedCount > 0 ? 'badge badge-failed' : 'badge badge-synced';
  }

  if (!logs || logs.length === 0) {
    container.innerHTML = `
      <tr>
        <td colspan="6" style="text-align:center; padding:32px 16px; color:var(--text-muted)">
          <div style="font-size:1.5rem; margin-bottom:8px">🎉</div>
          <div style="font-weight:600">Hệ thống đang hoạt động tối ưu</div>
          <div style="font-size:0.75rem; margin-top:4px">Không ghi nhận sự cố nào phù hợp với bộ lọc hiện tại.</div>
        </td>
      </tr>`;
    return;
  }

  container.innerHTML = logs.map(log => {
    const timeStr = log.timestamp ? new Date(log.timestamp).toLocaleString('vi-VN') : '—';
    const levelClass = (log.level || 'INFO').toLowerCase();
    const isResolved = !!log.resolved;

    return `
      <tr data-id="${log.id}">
        <td style="white-space:nowrap; font-size:0.75rem; color:var(--text-muted)">${timeStr}</td>
        <td>
          <span class="log-badge ${levelClass}">● ${log.level || 'INFO'}</span>
        </td>
        <td>
          <div style="font-weight:600">${escapeHtml(log.module || log.source || 'system')}</div>
          <div style="font-size:0.7rem; color:var(--text-muted)">${escapeHtml(log.action || 'event')}</div>
        </td>
        <td style="max-width:320px">
          <div style="font-weight:500; overflow:hidden; text-overflow:ellipsis; white-space:nowrap" title="${escapeHtml(log.message || '')}">
            ${escapeHtml(log.message || '—')}
          </div>
          ${log.file_name ? `<div class="mono" style="font-size:0.7rem; color:var(--primary); overflow:hidden; text-overflow:ellipsis; white-space:nowrap">📄 ${escapeHtml(log.file_name)}</div>` : ''}
        </td>
        <td>
          ${isResolved
            ? '<span class="log-status-resolved">✓ Đã khắc phục</span>'
            : '<span class="log-status-unresolved">⚠️ Đang mở</span>'}
        </td>
        <td style="white-space:nowrap">
          <div class="flex gap-1">
            <button class="btn btn-ghost btn-sm btn-view-log" data-id="${log.id}" title="Xem chi tiết Stacktrace">🔍 Chi tiết</button>
            ${!isResolved ? `<button class="btn btn-ghost btn-sm text-success btn-resolve-log" data-id="${log.id}" title="Đánh dấu đã giải quyết">✓ Xong</button>` : ''}
          </div>
        </td>
      </tr>`;
  }).join('');

  // Gắn sự kiện nút
  container.querySelectorAll('.btn-view-log').forEach(btn => {
    btn.addEventListener('click', () => {
      const log = _activeLogs.find(l => l.id === btn.dataset.id);
      if (log) openLogModal(log);
    });
  });

  container.querySelectorAll('.btn-resolve-log').forEach(btn => {
    btn.addEventListener('click', async () => {
      await resolveLogItem(btn.dataset.id);
    });
  });
}

/**
 * Đánh dấu log đã giải quyết
 */
async function resolveLogItem(logId) {
  try {
    await logsApi.resolve(logId);
    showToast('✓ Đã đánh dấu sự cố đã được xử lý', 'success');
    const target = _activeLogs.find(l => l.id === logId);
    if (target) target.resolved = true;
    renderLogsTable(_activeLogs);
  } catch (err) {
    showToast(`Không thể cập nhật: ${err.message}`, 'error');
  }
}

/**
 * Mở modal xem chi tiết lỗi
 */
function openLogModal(log) {
  _selectedLog = log;
  const modal = document.getElementById('system-log-modal');
  if (!modal) return;

  document.getElementById('modal-log-id').textContent = log.id || '—';
  document.getElementById('modal-log-time').textContent = log.timestamp ? new Date(log.timestamp).toLocaleString('vi-VN') : '—';
  document.getElementById('modal-log-level').textContent = log.level || 'INFO';
  document.getElementById('modal-log-level').className = `log-badge ${(log.level || 'info').toLowerCase()}`;
  document.getElementById('modal-log-source').textContent = `${log.source || ''} / ${log.module || ''} (${log.action || ''})`;
  document.getElementById('modal-log-message').textContent = log.message || '—';
  document.getElementById('modal-log-file').textContent = log.file_name || 'Không có';
  
  const detailEl = document.getElementById('modal-log-detail');
  if (detailEl) {
    detailEl.textContent = log.error_detail || 'Không có chi tiết lỗi hoặc Stacktrace.';
  }

  const contextEl = document.getElementById('modal-log-context');
  if (contextEl) {
    contextEl.textContent = log.context ? JSON.stringify(log.context, null, 2) : '{}';
  }

  const resolveBtn = document.getElementById('btn-modal-resolve-log');
  if (resolveBtn) {
    resolveBtn.style.display = log.resolved ? 'none' : 'inline-flex';
  }

  modal.classList.remove('hidden');
}

/**
 * Đóng modal
 */
function closeLogModal() {
  const modal = document.getElementById('system-log-modal');
  if (modal) modal.classList.add('hidden');
  _selectedLog = null;
}

/**
 * Giải quyết từ modal
 */
async function handleResolveFromModal() {
  if (!_selectedLog) return;
  await resolveLogItem(_selectedLog.id);
  closeLogModal();
}

/**
 * Helper escape HTML
 */
function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
