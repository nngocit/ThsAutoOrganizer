// src/routes/files/upload.js — Luồng 2: Web-to-Cloud-to-Local Flow (<160 lines)
// Nhận file -> Upload Drive (Service Account) -> Cấp Public Reader -> Lưu Firestore -> Đẩy task nlm_task_queue

import { Hono } from 'hono';
import { requireAuthOrAgent, resolveTargetUid, getFallbackUid } from '../../lib/auth.js';
import { firestoreGet, firestoreSet, fromFirestoreDoc } from '../../lib/firebase.js';
import { uploadFileToDrive, setDrivePublicReader } from '../../lib/drive.js';
import { withCors } from '../../lib/cors.js';

const router = new Hono();

/**
 * POST /api/files/upload
 * Luồng 2: Upload tài liệu từ Web
 * Body (multipart/form-data):
 *   - file: Binary File
 *   - course_id: ID môn học (bắt buộc)
 *   - document_type: Loại tài liệu (tùy chọn)
 */
router.post('/', requireAuthOrAgent(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';
  const targetUid = resolveTargetUid(c, user, c.req.query('uid')) || await getFallbackUid(c.env);

  if (!targetUid) {
    return withCors(c.json({ error: 'UID không xác định' }, 400), origin);
  }

  try {
    const formData = await c.req.formData();
    const file = formData.get('file');
    const courseId = formData.get('course_id');
    const documentType = formData.get('document_type') || 'giao_trinh';

    if (!file || !(file instanceof File)) {
      return withCors(c.json({ error: 'file là bắt buộc và phải là tệp tin hợp lệ' }, 400), origin);
    }
    if (!courseId) {
      return withCors(c.json({ error: 'course_id là bắt buộc' }, 400), origin);
    }

    // 1. Đọc thông tin Course từ Firestore
    const courseDoc = await firestoreGet(c.env, `users/${targetUid}/courses/${courseId}`);
    if (!courseDoc) {
      return withCors(c.json({ error: 'Môn học không tồn tại' }, 404), origin);
    }
    const course = fromFirestoreDoc(courseDoc);
    const driveFolderId = course.drive_folder_id;
    const notebooklmId = course.notebooklm_id || course.notebook_id || '';
    const localFolderName = course.local_folder_name || course.subject_key || '';

    if (!driveFolderId) {
      return withCors(c.json({ error: 'Môn học chưa được liên kết thư mục Google Drive (thiếu drive_folder_id)' }, 400), origin);
    }

    // 2. Đọc nội dung file & tính SHA-256 hash
    const arrayBuffer = await file.arrayBuffer();
    const hashBuffer = await crypto.subtle.digest('SHA-256', arrayBuffer);
    const sha256 = Array.from(new Uint8Array(hashBuffer))
      .map((b) => b.toString(16).padStart(2, '0'))
      .join('');

    // 3. Upload file lên Google Drive bằng Service Account
    let driveRes;
    try {
      driveRes = await uploadFileToDrive(c.env, {
        filename: file.name,
        mimeType: file.type || 'application/octet-stream',
        parentId: driveFolderId,
        contentBuffer: arrayBuffer,
      });
    } catch (uploadErr) {
      console.error('Lỗi upload file lên Google Drive:', uploadErr);
      return withCors(c.json({ error: 'Không thể upload file lên Google Drive', detail: uploadErr.message }, 502), origin);
    }

    const driveFileId = driveRes.id;

    // 4. Cấp quyền Public Reader cho file trên Google Drive để NotebookLM có thể truy cập
    let webViewLink = '';
    try {
      webViewLink = await setDrivePublicReader(c.env, driveFileId);
    } catch (permErr) {
      console.warn('Cấp quyền Public Reader Drive cảnh báo:', permErr);
      webViewLink = driveRes.webViewLink || `https://drive.google.com/file/d/${driveFileId}/view`;
    }

    const fileId = crypto.randomUUID();
    const now = new Date().toISOString();

    // 5. Lưu File metadata vào Firestore
    const fileRecord = {
      id: fileId,
      filename: file.name,
      size_bytes: file.size,
      sha256,
      course_id: courseId,
      course_name: course.display_name || course.name || '',
      local_folder_name: localFolderName,
      document_type: documentType,
      drive_file_id: driveFileId,
      drive_view_link: webViewLink,
      webViewLink,
      notebooklm_id: notebooklmId,
      notebooklm_sync_status: notebooklmId ? 'pending' : 'skipped_no_notebook',
      created_at: now,
      updated_at: now,
    };
    await firestoreSet(c.env, `users/${targetUid}/files/${fileId}`, fileRecord);

    // 6. Tạo task trong nlm_task_queue cho Local Agent nạp AI và tải bản sao local
    const taskId = crypto.randomUUID();
    await firestoreSet(c.env, `nlm_task_queue/${taskId}`, {
      id: taskId,
      action: 'source_add',
      file_id: fileId,
      filename: file.name,
      file_url: webViewLink,
      drive_file_id: driveFileId,
      notebooklm_id: notebooklmId,
      course_id: courseId,
      local_folder_name: localFolderName,
      uid: targetUid,
      status: 'pending',
      created_at: now,
    });

    return withCors(c.json({
      file_id: fileId,
      filename: file.name,
      drive_file_id: driveFileId,
      webViewLink,
      task_id: taskId,
      status: 'uploaded',
    }, 201), origin);
  } catch (err) {
    console.error('File upload error:', err);
    return withCors(c.json({ error: 'Xử lý tải lên file thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
