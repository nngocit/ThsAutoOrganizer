// cloudflare/pages/src/js/components/file_upload.js — Drag & drop + 3-phase upload (<150 lines)
import { filesApi, computeSHA256 } from '../api.js';
import { showToast } from '../app.js';

const SUPPORTED_TYPES = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  'text/plain', 'text/markdown', 'image/jpeg', 'image/png', 'audio/mpeg'];

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
      <div style="font-weight:600; margin-bottom:8px">Kéo thả file vào đây</div>
      <div class="text-muted" style="font-size:0.875rem">PDF, DOCX, PPTX, TXT, MD, JPG, PNG, MP3</div>
      <input type="file" id="file-input" multiple accept=".pdf,.docx,.pptx,.txt,.md,.jpg,.jpeg,.png,.mp3"
             style="display:none">
      <div style="display:flex; gap:12px; justify-content:center; margin-top:16px">
        <button class="btn btn-primary" id="btn-browse-files">📂 Chọn file</button>
        <select class="btn btn-ghost" id="upload-subject-select" style="min-width:140px">
          <option value="Triết học">Triết học</option>
          <option value="Toán KHCL">Toán KHCL</option>
          <option value="Cơ sở dữ liệu">Cơ sở dữ liệu</option>
          <option value="Hệ thống thông tin">Hệ thống thông tin</option>
          <option value="Kinh tế lượng">Kinh tế lượng</option>
        </select>
        <select class="btn btn-ghost" id="upload-type-select" style="min-width:140px">
          <option value="giao_trinh">📚 Giáo trình</option>
          <option value="slide">📊 Slide</option>
          <option value="bai_bao">🔬 Bài báo</option>
          <option value="unverified_web">🌐 Web</option>
          <option value="ket_qua">✅ Kết quả</option>
        </select>
      </div>
    </div>
    <div id="upload-progress-list" style="margin-top:12px; display:flex; flex-direction:column; gap:8px"></div>
  `;

  const dropZone = container.querySelector('#upload-drop-zone');
  const fileInput = container.querySelector('#file-input');
  const browseBtn = container.querySelector('#btn-browse-files');
  const progressList = container.querySelector('#upload-progress-list');

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
    const subject = container.querySelector('#upload-subject-select')?.value || '';
    const docType = container.querySelector('#upload-type-select')?.value || 'giao_trinh';

    for (const file of files) {
      await uploadFile(file, subject, docType);
    }
  }

  async function uploadFile(file, subject, docType) {
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
      // Phase 1: Tính SHA-256 phía client
      updateStatus('Tính SHA-256...');
      const sha256 = await computeSHA256(file);

      // Phase 1: Init upload → lấy Drive URL
      updateStatus('Khởi tạo upload session...');
      const initResp = await filesApi.initUpload({
        filename: file.name, size_bytes: file.size,
        subject, document_type: docType,
        drive_access_token: window._googleAccessToken || null,
      });

      let driveFileId = null;
      if (initResp.upload_url) {
        // Phase 2: Upload trực tiếp lên Drive
        updateStatus('Đang tải file lên Drive...');
        const driveResp = await fetch(initResp.upload_url, {
          method: 'PUT',
          headers: { 'Content-Type': initResp.mime_type || 'application/octet-stream' },
          body: file,
        });
        const driveData = await driveResp.json().catch(() => ({}));
        driveFileId = driveData.id || null;
      }

      // Phase 3: Complete
      updateStatus('Hoàn tất lưu metadata...');
      const completeResp = await filesApi.completeUpload({
        doc_id: initResp.doc_id, sha256, drive_file_id: driveFileId || '',
        drive_access_token: window._googleAccessToken || null,
      });

      if (completeResp.status === 'duplicate') {
        itemEl.innerHTML = `<div class="text-warning">⚠ File "${file.name}" đã tồn tại (SHA-256 trùng)</div>`;
      } else {
        itemEl.innerHTML = `<div class="text-success">✓ Đã upload: ${file.name}</div>`;
        options.onSuccess?.();
      }
      setTimeout(() => itemEl.remove(), 5000);
    } catch (err) {
      itemEl.innerHTML = `<div class="text-danger">✗ Lỗi: ${err.message}</div>`;
      showToast(`Upload thất bại: ${file.name}`, 'error');
    }
  }
}
