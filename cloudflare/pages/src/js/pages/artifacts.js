// cloudflare/pages/src/js/pages/artifacts.js — Artifacts .pptx/.docx trong 04_Ket_Qua_Xuat_Ban (<180 dòng)
import { artifactApi, coursesApi } from '../api.js';
import { showToast, onTabActivate } from '../app.js';
import { OUTPUT_FOLDER, getExtension } from '../constants.js';

function esc(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function formatBytes(bytes) {
  if (!bytes) return '—';
  if (bytes < 1048576) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1048576).toFixed(1)} MB`;
}

const EXT_BADGE = {
  '.pptx': { icon: '📊', cls: 'badge-synced' },
  '.docx': { icon: '📄', cls: 'badge-processing' },
  '.pdf':  { icon: '📕', cls: 'badge-pending' },
};

// ---------- Shell ----------
function renderShell() {
  const root = document.getElementById('artifacts-root');
  if (!root || root.dataset.ready) return;
  root.dataset.ready = '1';
  root.innerHTML = `
    <div class="card" style="margin-bottom:16px">
      <div style="font-weight:600; margin-bottom:12px">⬇ Tải artifact mới từ NotebookLM về <span class="mono">${OUTPUT_FOLDER}/</span></div>
      <div class="flex gap-2" style="flex-wrap:wrap; align-items:center">
        <select id="artifact-course" class="btn btn-ghost btn-sm" style="min-width:180px"></select>
        <input id="artifact-name" type="text" placeholder="Tên artifact (vd: Slide bài 1)"
               style="background:var(--bg-elevated); border:1px solid var(--border); border-radius:var(--r-sm); padding:6px 10px; color:var(--text); font-family:inherit; font-size:0.85rem">
        <select id="artifact-format" class="btn btn-ghost btn-sm">
          <option value="pptx">.pptx (Slide deck)</option>
          <option value="docx">.docx (Tài liệu)</option>
          <option value="pdf">.pdf</option>
        </select>
        <button class="btn btn-primary btn-sm" id="btn-download-artifact">⬇ Tải về</button>
        <button class="btn btn-ghost btn-sm" id="btn-refresh-artifacts">🔄 Làm mới</button>
      </div>
      <div class="text-muted" style="font-size:0.78rem; margin-top:8px">
        ⛔ NO-LOOP: file trong thư mục kết quả không bị đồng bộ ngược lại NotebookLM.
      </div>
    </div>
    <div id="artifacts-list"></div>`;
  document.getElementById('btn-download-artifact').addEventListener('click', downloadArtifact);
  document.getElementById('btn-refresh-artifacts').addEventListener('click', loadArtifacts);
}

async function loadCourses() {
  const sel = document.getElementById('artifact-course');
  if (!sel || sel.options.length) return;
  try {
    const { courses } = await coursesApi.list();
    sel.innerHTML = (courses && courses.length)
      ? courses.map((c) => `<option value="${c.id}">${esc(c.name || c.subject || c.id)}</option>`).join('')
      : '<option value="">(Chưa có môn học)</option>';
  } catch {
    sel.innerHTML = '<option value="">(Lỗi tải môn học)</option>';
  }
}

async function downloadArtifact() {
  const courseId = document.getElementById('artifact-course')?.value;
  const name = document.getElementById('artifact-name')?.value.trim();
  const format = document.getElementById('artifact-format')?.value || 'pptx';
  if (!courseId) { showToast('Chọn môn học trước', 'error'); return; }
  try {
    const { task_id } = await artifactApi.download({
      course_id: courseId, artifact_name: name || undefined, format,
    });
    showToast(`⬇ Đã xếp hàng tải artifact (task ${task_id}). File sẽ xuất hiện trong ${OUTPUT_FOLDER}/ — bấm 🔄 sau ít phút.`, 'success', 6000);
  } catch (err) { showToast(`Tải artifact thất bại: ${err.message}`, 'error'); }
}

// ---------- List ----------
function renderArtifactCard(file) {
  const ext = getExtension(file.filename);
  const meta = EXT_BADGE[ext] || { icon: '📦', cls: 'badge-processing' };
  return `
    <div class="card">
      <div class="flex items-center gap-2">
        <div class="file-icon">${meta.icon}</div>
        <div style="flex:1">
          <div class="file-name" title="${esc(file.filename)}">${esc(file.filename)}</div>
          <div class="file-meta">${esc(file.subject || '—')} · ${formatBytes(file.size_bytes)}</div>
        </div>
      </div>
      <div class="flex gap-2 mt-4" style="flex-wrap:wrap; align-items:center">
        <span class="badge ${meta.cls}"><span class="badge-dot"></span>${ext || 'file'}</span>
        <span class="badge badge-new">⛔ NO-LOOP</span>
        <span class="text-muted mono" style="font-size:0.72rem">${esc(file.folder_path || OUTPUT_FOLDER)}</span>
      </div>
    </div>`;
}

async function loadArtifacts() {
  const root = document.getElementById('artifacts-list');
  if (!root) return;
  root.innerHTML = '<div class="text-muted">Đang tải danh sách artifacts...</div>';
  try {
    const { artifacts } = await artifactApi.list();
    root.innerHTML = (artifacts && artifacts.length)
      ? `<div class="card-grid">${artifacts.map(renderArtifactCard).join('')}</div>`
      : '<div class="text-muted">Chưa có artifact nào trong 04_Ket_Qua_Xuat_Ban.</div>';
  } catch (err) {
    root.innerHTML = `<div class="text-danger">Lỗi: ${esc(err.message)}</div>`;
  }
}

export function initArtifacts() {
  onTabActivate('artifacts', () => { renderShell(); loadCourses(); loadArtifacts(); });
}
