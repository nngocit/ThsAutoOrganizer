// cloudflare/pages/src/js/components/file_upload.js — Upload trực tiếp lên Worker -> Drive (<120 dòng)
import { filesApi, coursesApi } from '../api.js';
import { showToast } from '../app.js';

/**
 * Render và khởi động upload component trong container.
 * 
 * @param {HTMLElement} container
 * @param {Object} options
 * @param {Function} options.onSuccess - callback sau khi upload thành công
 */
export function renderFileUpload(container, options = {}) {
  container.innerHTML = `
    <div class="upload-zone" id="upload-drop-zone">
      <div class="upload-zone-icon">☁️</div>
      <div style="font-weight:600; margin-bottom:8px">Kéo thả file vào đây hoặc bấm Chọn file</div>
      <div class="text-muted" style="font-size:0.875rem">Hỗ trợ PDF, DOCX, PPTX, TXT, MD, MP3 (Tự động stream lên Google Drive 24/7 & NotebookLM)</div>
      <input type="file" id="file-input" multiple accept=".pdf,.docx,.pptx,.txt,.md,.jpg,.jpeg,.png,.mp3"
             style="display:none">
      <div style="display:flex; gap:12px; justify-content:center; margin-top:16px; flex-wrap:wrap">
        <button class="btn btn-primary" id="btn-browse-files" type="button">📂 Chọn file</button>
        <select class="btn btn-ghost" id="upload-subject-select" style="min-width:180px">
          <option value="">Đang tải môn học...</option>
        </select>
        <select class="btn btn-ghost" id="upload-type-select" style="min-width:140px">
          <option value="giao_trinh">📚 Giáo trình</option>
          <option value="slide">📊 Slide bài giảng</option>
          <option value="bai_bao">🔬 Bài báo nghiên cứu</option>
          <option value="ket_qua">✅ Ấn phẩm / Kết quả</option>
        </select>
      </div>
    </div>
    <div id="upload-progress-list" style="margin-top:12px; display:flex; flex-direction:column; gap:8px"></div>
  `;

  const dropZone = container.querySelector('#upload-drop-zone');
  const fileInput = container.querySelector('#file-input');
  const browseBtn = container.querySelector('#btn-browse-files');
  const progressList = container.querySelector('#upload-progress-list');
  const subjectSelect = container.querySelector('#upload-subject-select');

  // Nạp danh sách môn học động từ backend
  coursesApi.list().then((data) => {
    const courses = (data.courses || []).filter((c) => c.kind === 'subject');
    if (courses.length && subjectSelect) {
      subjectSelect.innerHTML = courses.map((c) => {
        const id = c.id || c._id;
        const name = c.name || c.folder_name || c.local_folder_name || id;
        return `<option value="${id}">${name}</option>`;
      }).join('');
      if (window._activeCourseId && courses.some((c) => (c.id || c._id) === window._activeCourseId)) {
        subjectSelect.value = window._activeCourseId;
      }
    } else if (subjectSelect) {
      subjectSelect.innerHTML = '<option value="">(Chưa có môn học - hãy tạo môn)</option>';
    }
  }).catch(() => {
    if (subjectSelect) subjectSelect.innerHTML = '<option value="">(Lỗi tải môn học)</option>';
  });

  browseBtn.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => handleFiles([...fileInput.files]));

  dropZone.addEventListener('dragover', (e) => { e.preventDefault(); dropZone.classList.add('dragover'); });
  dropZone.addEventListener('dragleave', () => dropZone.classList.remove('dragover'));
  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    handleFiles([...e.dataTransfer.files]);
  });

  async function handleFiles(files) {
    const courseId = container.querySelector('#upload-subject-select')?.value || '';
    const docType = container.querySelector('#upload-type-select')?.value || 'giao_trinh';

    if (!courseId) {
      showToast('Vui lòng chọn môn học trước khi tải lên', 'error');
      return;
    }

    for (const file of files) {
      await uploadFile(file, courseId, docType);
    }
  }

  async function uploadFile(file, courseId, docType) {
    const itemId = `upload-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    const itemEl = document.createElement('div');
    itemEl.id = itemId;
    itemEl.className = 'card';
    itemEl.innerHTML = `
      <div class="flex items-center gap-2">
        <div class="loading-spinner"></div>
        <div style="flex:1">
          <div style="font-weight:500; font-size:0.875rem">${file.name}</div>
          <div class="text-muted" style="font-size:0.78rem" id="${itemId}-status">Đang chuẩn bị...</div>
        </div>
      </div>
    `;
    progressList.prepend(itemEl);

    const updateStatus = (msg) => {
      const el = document.getElementById(`${itemId}-status`);
      if (el) el.textContent = msg;
    };

    try {
      updateStatus('Đang stream file lên Worker & Google Drive (24/7)...');
      const formData = new FormData();
      formData.append('file', file);
      formData.append('course_id', courseId);
      formData.append('document_type', docType);

      const resp = await filesApi.upload(formData);
      updateStatus('Đồng bộ hoàn tất!');
      itemEl.innerHTML = `
        <div class="text-success" style="font-size:0.85rem">
          ✓ Đã tải lên thành công: <strong>${file.name}</strong> 
          <span class="text-muted" style="font-size:0.75rem">(Đã đưa vào hàng đợi NotebookLM)</span>
        </div>`;
      showToast(`✓ Đã upload: ${file.name}`, 'success');
      options.onSuccess?.();
      setTimeout(() => itemEl.remove(), 4000);
    } catch (err) {
      itemEl.innerHTML = `<div class="text-danger" style="font-size:0.85rem">✗ Lỗi upload: ${err.message}</div>`;
      showToast(`Upload thất bại: ${file.name}`, 'error');
    }
  }
}
