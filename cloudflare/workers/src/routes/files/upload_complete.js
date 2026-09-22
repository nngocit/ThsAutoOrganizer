// src/routes/files/upload_complete.js — Phase 3: Hoàn tất upload, lưu metadata (<150 lines)
// Client đã upload file trực tiếp vào Drive, gửi sha256 + drive_file_id để Worker lưu Firestore

import { Hono } from 'hono';
import { requireAuth } from '../../lib/auth.js';
import { firestoreGet, firestoreSet, firestoreList, fromFirestoreDoc } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';

const router = new Hono();

/**
 * Kiểm tra SHA-256 đã tồn tại trong Firestore của user chưa.
 * Lấy toàn bộ files collection và lọc phía Worker (Firestore REST không hỗ trợ WHERE tốt).
 */
async function checkDuplicateSHA256(env, uid, sha256) {
  const resp = await firestoreList(env, `users/${uid}/files`, 200);
  const docs = resp.documents || [];
  return docs.some((doc) => {
    const obj = fromFirestoreDoc(doc);
    return obj.sha256 === sha256 && obj.status !== 'pending_upload' && obj.status !== 'archived';
  });
}

/**
 * Xóa file trên Google Drive (dùng khi phát hiện duplicate sau khi đã upload).
 */
async function deleteDriveFile(accessToken, driveFileId) {
  if (!driveFileId || !accessToken) return;
  try {
    await fetch(`https://www.googleapis.com/drive/v3/files/${driveFileId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${accessToken}` },
    });
  } catch (err) {
    console.warn('Drive cleanup failed:', err.message);
  }
}

// POST /api/files/upload/complete
router.post('/complete', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const body = await c.req.json();
    const { doc_id, sha256, drive_file_id, drive_access_token } = body;

    if (!doc_id || !sha256) {
      return withCors(c.json({ error: 'doc_id và sha256 là bắt buộc' }, 400), origin);
    }
    if (!/^[a-f0-9]{64}$/.test(sha256)) {
      return withCors(c.json({ error: 'sha256 không hợp lệ — phải là hex 64 ký tự' }, 400), origin);
    }

    // Kiểm tra doc tồn tại và thuộc về user này
    const existingDoc = await firestoreGet(c.env, `users/${user.uid}/files/${doc_id}`);
    if (!existingDoc) {
      return withCors(c.json({ error: 'Document không tồn tại hoặc không thuộc về bạn' }, 404), origin);
    }

    // Kiểm tra SHA-256 duplicate
    const isDuplicate = await checkDuplicateSHA256(c.env, user.uid, sha256);
    if (isDuplicate) {
      // Dọn sạch Drive file vừa upload (nếu có)
      await deleteDriveFile(drive_access_token, drive_file_id);
      // Soft delete placeholder document
      await firestoreSet(c.env, `users/${user.uid}/files/${doc_id}`, {
        status: 'archived',
        updated_at: new Date().toISOString(),
      });
      return withCors(c.json({ status: 'duplicate', sha256 }, 409), origin);
    }

    const now = new Date().toISOString();

    // Cập nhật Firestore document với metadata đầy đủ
    await firestoreSet(c.env, `users/${user.uid}/files/${doc_id}`, {
      sha256,
      drive_file_id: drive_file_id || '',
      status: 'uploaded',
      updated_at: now,
    });

    // Queue NotebookLM sync task (auto-ingestion pipeline)
    const existingFields = fromFirestoreDoc(existingDoc);
    if (existingFields.course_id) {
      const taskId = crypto.randomUUID();
      await firestoreSet(c.env, `nlm_task_queue/${taskId}`, {
        id: taskId,
        action: 'source_add',
        uid: user.uid,
        file_id: doc_id,
        course_id: existingFields.course_id,
        filename: existingFields.filename || '',
        status: 'pending',
        created_at: now,
      });
    }

    return withCors(c.json({
      status: 'uploaded',
      doc_id,
      sha256,
      drive_file_id: drive_file_id || '',
    }), origin);
  } catch (err) {
    console.error('Upload complete error:', err);
    return withCors(c.json({ error: 'Upload complete thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
