// cloudflare/pages/src/js/pages/review.js — Hàng đợi kiểm duyệt nguồn (Phase 4, <150 dòng)
import { reviewApi } from '../api.js';
import { showToast, onTabActivate } from '../app.js';

function esc(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function formatBytes(bytes) {
  if (!bytes) return '—';
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

function renderReviewCard(file) {
  return `
    <div class="card" data-id="${file.id}" style="border-left:4px solid #EAB308">
      <div class="flex items-center gap-2" style="justify-content:space-between; flex-wrap:wrap">
        <div style="flex:1; min-width:200px">
          <div style="font-weight:600">${esc(file.filename)}</div>
          <div class="text-muted" style="font-size:0.8rem">
            ${esc(file.subject || '—')} · ${formatBytes(file.size_bytes)} ·
            nguồn: ${esc(file.source_kind || 'deep_research')}
          </div>
          ${file.url ? `<div class="text-muted mono" style="font-size:0.72rem">${esc(file.url)}</div>` : ''}
        </div>
        <span class="badge badge-pending"><span class="badge-dot"></span>🟡 Chờ duyệt</span>
      </div>
      <div class="flex gap-2 mt-4">
        <button class="btn btn-primary btn-sm btn-approve" data-id="${file.id}">✅ Duyệt</button>
        <button class="btn btn-danger btn-sm btn-reject" data-id="${file.id}">🗑️ Xoá</button>
      </div>
    </div>`;
}

async function loadQueue() {
  const root = document.getElementById('review-root');
  if (!root) return;
  root.innerHTML = '<div class="text-muted">Đang tải hàng đợi duyệt...</div>';
  try {
    const { files, total } = await reviewApi.list('unreviewed');
    if (!files || !files.length) {
      root.innerHTML = `
        <div class="card" style="text-align:center; padding:48px 24px; border-style:dashed">
          <div style="font-size:2.2rem; margin-bottom:10px">✨</div>
          <div style="font-weight:600; font-size:1.05rem; color:var(--text); margin-bottom:6px">Không còn nguồn nào chờ duyệt</div>
          <p class="text-muted" style="font-size:0.85rem">Tất cả tài liệu từ Deep Research đã được kiểm duyệt và sẵn sàng cho NotebookLM.</p>
        </div>`;
      return;
    }
    root.innerHTML = `
      <div class="text-muted" style="margin-bottom:12px">Có <strong>${total ?? files.length}</strong> nguồn
        <span class="badge badge-pending">unreviewed</span> — duyệt để đưa vào NotebookLM, xoá để loại bỏ khỏi nguồn tham khảo.</div>
      <div style="display:flex; flex-direction:column; gap:12px">${files.map(renderReviewCard).join('')}</div>`;
    root.querySelectorAll('.btn-approve').forEach((btn) =>
      btn.addEventListener('click', () => handleReview(btn.dataset.id, 'approved')));
    root.querySelectorAll('.btn-reject').forEach((btn) =>
      btn.addEventListener('click', () => handleReview(btn.dataset.id, 'rejected')));
  } catch (err) {
    root.innerHTML = `<div class="text-danger">Lỗi tải hàng đợi: ${esc(err.message)}</div>`;
  }
}

async function handleReview(fileId, status) {
  let note = '';
  if (status === 'rejected') {
    if (!confirm('Từ chối nguồn này? Nguồn sẽ bị gỡ khỏi NotebookLM (file Drive giữ nguyên).')) return;
    note = prompt('Ghi chú lý do (tuỳ chọn):', '') || '';
  }
  try {
    const result = await reviewApi.review(fileId, { review_status: status, note });
    showToast(
      status === 'approved'
        ? `✅ Đã duyệt — ${result.steps ? result.steps.join(', ') : 'đang đưa vào NotebookLM'}`
        : '🗑️ Đã từ chối nguồn',
      'success'
    );
    loadQueue();
  } catch (err) {
    showToast(`Thao tác thất bại: ${err.message}`, 'error');
  }
}

export function initReview() {
  onTabActivate('review', loadQueue);
}
