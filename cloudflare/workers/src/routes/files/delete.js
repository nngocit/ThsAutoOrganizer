// src/routes/files/delete.js — DELETE /api/files/:id — Safe Cascade Delete 4 bước (<200 lines)

import { Hono } from 'hono';
import { requireAuth } from '../../lib/auth.js';
import { firestoreGet, firestoreSet, fromFirestoreDoc } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';

const router = new Hono();

/** Bước 1: Queue task gỡ source NotebookLM (non-blocking) */
async function queueNLMRemove(env, uid, fileId, sourceId) {
  if (!sourceId) return { success: true, skipped: true, reason: 'no_source_id' };
  try {
    const taskId = crypto.randomUUID();
    await firestoreSet(env, `nlm_task_queue/${taskId}`, {
      id: taskId,
      action: 'source_remove',
      uid,
      file_id: fileId,
      source_id: sourceId,
      status: 'pending',
      created_at: new Date().toISOString(),
    });
    return { success: true, queued: true, task_id: taskId };
  } catch (err) {
    // Không block quy trình xóa nếu queue thất bại
    console.warn('NLM remove queue failed:', err.message);
    return { success: false, error: err.message };
  }
}

/** Bước 2: Queue task dời file Drive sang _Archive_Trash_90Days/ (non-blocking) */
async function queueDriveArchive(env, uid, fileId, driveFileId) {
  if (!driveFileId) return { success: true, skipped: true, reason: 'no_drive_file_id' };
  try {
    const taskId = crypto.randomUUID();
    await firestoreSet(env, `drive_task_queue/${taskId}`, {
      id: taskId,
      action: 'move_to_archive',
      uid,
      file_id: fileId,
      drive_file_id: driveFileId,
      target_folder: '_Archive_Trash_90Days',
      status: 'pending',
      created_at: new Date().toISOString(),
    });
    return { success: true, queued: true, task_id: taskId };
  } catch (err) {
    console.warn('Drive archive queue failed:', err.message);
    return { success: false, error: err.message };
  }
}

/** Bước 3: Soft delete trong Firestore (synchronous) */
async function softDeleteFirestore(env, uid, fileId, fileData) {
  const now = new Date().toISOString();
  const hardDeleteAt = new Date(Date.now() + 90 * 24 * 60 * 60 * 1000).toISOString();

  // Cập nhật users/{uid}/files/{id}
  await firestoreSet(env, `users/${uid}/files/${fileId}`, {
    status: 'archived',
    archived_at: now,
    hard_delete_at: hardDeleteAt,
    updated_at: now,
  });

  // Ghi thêm vào archived_files flat collection (để cron dễ query)
  await firestoreSet(env, `archived_files/${fileId}`, {
    id: fileId,
    uid,
    filename: fileData.filename || '',
    sha256: fileData.sha256 || '',
    drive_file_id: fileData.drive_file_id || '',
    user_email: fileData.user_email || '',
    status: 'archived',
    archived_at: now,
    hard_delete_at: hardDeleteAt,
  });

  return { success: true, hard_delete_at: hardDeleteAt };
}

// DELETE /api/files/:fileId
router.delete('/:fileId', requireAuth(async (c) => {
  const user = c.get('user');
  const fileId = c.req.param('fileId');
  const origin = c.req.header('Origin') || '';

  try {
    // Lấy thông tin file từ Firestore
    const fileDoc = await firestoreGet(c.env, `users/${user.uid}/files/${fileId}`);
    if (!fileDoc) {
      return withCors(c.json({ error: 'File không tìm thấy hoặc bạn không có quyền truy cập' }, 404), origin);
    }

    const fileData = fromFirestoreDoc(fileDoc);

    // Kiểm tra file đã bị archive rồi
    if (fileData.status === 'archived') {
      return withCors(c.json({ error: 'File đã được xóa trước đó', status: 'already_archived' }, 409), origin);
    }

    const steps = {};

    // Bước 1: Gỡ source NotebookLM (queue, non-blocking)
    steps.step1_nlm_remove = await queueNLMRemove(
      c.env, user.uid, fileId, fileData.notebooklm_source_id || ''
    );

    // Bước 2: Soft delete Drive (queue, non-blocking)
    steps.step2_drive_archive = await queueDriveArchive(
      c.env, user.uid, fileId, fileData.drive_file_id || ''
    );

    // Bước 3: Soft delete Firestore (synchronous — bắt buộc thành công)
    steps.step3_firestore = await softDeleteFirestore(c.env, user.uid, fileId, fileData);

    // Bước 4: Hard delete sau 90 ngày → Cron Worker tự động (không cần action ở đây)

    return withCors(c.json({
      status: 'archived',
      file_id: fileId,
      hard_delete_at: steps.step3_firestore.hard_delete_at,
      message: 'File sẽ bị xóa hoàn toàn sau 90 ngày',
      steps,
    }), origin);
  } catch (err) {
    console.error('Delete error:', err);
    return withCors(c.json({ error: 'Xóa file thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
