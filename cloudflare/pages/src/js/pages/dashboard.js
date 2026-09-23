// cloudflare/pages/src/js/pages/dashboard.js — File list, upload UI, status badges (<200 lines)
import { filesApi, coursesApi } from '../api.js';
import { showToast } from '../app.js';
import { renderFileUpload } from '../components/file_upload.js';

// Subject → emoji icon map
const SUBJECT_ICONS = {
  'Triết học': '🧠', 'Toán KHCL': '📐', 'Cơ sở dữ liệu': '🗃️',
  'Hệ thống thông tin': '💻', 'Kinh tế lượng': '📊',
};

const DOC_TYPE_LABELS = {
  giao_trinh: '📚 Giáo trình', slide: '📊 Slide',
  bai_bao: '🔬 Bài báo', unverified_web: '🌐 Web', ket_qua: '✅ Kết quả',
};

const NLM_BADGE_MAP = {
  synced:     { cls: 'badge-synced',     text: '✓ NLM Synced' },
  pending:    { cls: 'badge-pending',    text: '⏳ Đang đồng bộ' },
  failed:     { cls: 'badge-failed',     text: '✗ Sync thất bại' },
  skipped:    { cls: 'badge-processing', text: '⏭ Bỏ qua (ext)' },
};

function formatBytes(bytes) {
  if (!bytes) return '—';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1048576) return `${(bytes/1024).toFixed(1)} KB`;
  return `${(bytes/1048576).toFixed(1)} MB`;
}

function renderFileCard(file) {
  const icon = SUBJECT_ICONS[file.subject] || '📄';
  const typeLabel = DOC_TYPE_LABELS[file.document_type] || file.document_type;
  const nlm = NLM_BADGE_MAP[file.notebooklm_sync_status] || NLM_BADGE_MAP.pending;
  const isNew = file.is_new;

  return `
    <div class="card file-card" data-id="${file.id}" data-sha="${file.sha256 || ''}">
      <div class="file-card-top">
        <div class="flex items-center gap-2">
          <div class="file-icon">${icon}</div>
          <div>
            <div class="file-name" title="${file.filename}">${file.filename}</div>
            <div class="file-meta">${file.subject} · ${typeLabel}</div>
          </div>
        </div>
        <button class="btn btn-danger btn-sm btn-delete-file" data-id="${file.id}" title="Xóa file">🗑</button>
      </div>
      <div class="flex gap-2 mt-4" style="flex-wrap:wrap; align-items:center">
        <span class="badge ${nlm.cls}"><span class="badge-dot"></span>${nlm.text}</span>
        ${isNew ? '<span class="badge badge-new">Mới</span>' : ''}
        <span class="text-muted mono">${formatBytes(file.size_bytes)}</span>
      </div>
    </div>
  `;
}

async function loadFiles(filters = {}) {
  const container = document.getElementById('files-grid');
  if (!container) return;
  container.innerHTML = '<div class="text-muted" style="padding:24px 0">Đang tải...</div>';
  try {
    const { files } = await filesApi.list(filters);
    if (!files.length) {
      container.innerHTML = '<div class="text-muted" style="padding:24px 0">Chưa có file nào. Hãy upload file đầu tiên!</div>';
      return;
    }
    container.innerHTML = `<div class="card-grid">${files.map(renderFileCard).join('')}</div>`;
    // Attach delete handlers
    container.querySelectorAll('.btn-delete-file').forEach((btn) => {
      btn.addEventListener('click', () => handleDeleteFile(btn.dataset.id));
    });
  } catch (err) {
    container.innerHTML = `<div class="text-danger">Lỗi tải file: ${err.message}</div>`;
  }
}

async function handleDeleteFile(fileId) {
  if (!confirm('Xóa file này? File sẽ vào Thùng rác và bị xóa hoàn toàn sau 90 ngày.')) return;
  try {
    const result = await filesApi.delete(fileId);
    showToast(`Đã xóa file. Sẽ xóa vĩnh viễn lúc ${new Date(result.hard_delete_at).toLocaleDateString('vi')}`, 'success', 5000);
    loadFiles();   // Refresh list
  } catch (err) {
    showToast(`Xóa thất bại: ${err.message}`, 'error');
  }
}

function initFilters() {
  const subjectFilter = document.getElementById('filter-subject');
  const typeFilter = document.getElementById('filter-doc-type');
  if (subjectFilter) {
    subjectFilter.addEventListener('change', () =>
      loadFiles({ subject: subjectFilter.value, document_type: typeFilter?.value }));
  }
  if (typeFilter) {
    typeFilter.addEventListener('change', () =>
      loadFiles({ subject: subjectFilter?.value, document_type: typeFilter.value }));
  }
}

export function initDashboard() {
  // Upload component
  const uploadArea = document.getElementById('upload-area');
  if (uploadArea) {
    renderFileUpload(uploadArea, { onSuccess: () => loadFiles() });
  }
  initFilters();
  loadFiles();

  // Refresh khi tab được activate
  window.__onTabActivate = (tabId) => {
    if (tabId === 'dashboard') loadFiles();
  };
}
