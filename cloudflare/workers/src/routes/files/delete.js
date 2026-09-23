// src/routes/files/delete.js — DELETE /api/files/:id — Safe Cascade Delete 4 bước (§3.8) (<170 lines)
// Thứ tự: (1) gỡ NotebookLM → (2) Drive archive → (3) Firestore + soft delete local PC
//         → (4) hẹn hard delete sau 90 ngày (cron). Mọi bước đều ghi vào `steps` để audit.

import { Hono } from 'hono';
import { requireAuth } from '../../lib/auth.js';
import { firestoreGet, firestoreSet, fromFirestoreDoc } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';
import { ARCHIVE_FOLDER, HARD_DELETE_DAYS } from '../../lib/folders.js';
import {
  enqueueSourceRemove, enqueueDriveArchive, enqueueSoftDeleteLocal,
} from '../../lib/tasks.js';

const router = new Hono();

/** Bọc 1 bước cascade — không bao giờ throw để các bước sau vẫn chạy */
async function safeStep(name, fn) {
  try {
    return await fn();
  } catch (err) {
    console.warn(`[Cascade] ${name} lỗi:`, err.message);
    return { success: false, error: err.message };
  }
}

// DELETE /api/files/:fileId
router.delete('/:fileId', requireAuth(async (c) => {
  const user = c.get('user');
  const fileId = c.req.param('fileId');
  const origin = c.req.header('Origin') || '';

  try {
    // Lấy thông tin file từ Firestore (đồng thời kiểm tra ownership theo uid)
    const fileDoc = await firestoreGet(c.env, `users/${user.uid}/files/${fileId}`);
    if (!fileDoc) {
      return withCors(c.json({ error: 'File không tìm thấy hoặc bạn không có quyền truy cập' }, 404), origin);
    }

    const fileData = fromFirestoreDoc(fileDoc);
    if (fileData.status === 'archived') {
      return withCors(c.json({ error: 'File đã được xóa trước đó', status: 'already_archived' }, 409), origin);
    }

    const steps = {};

    // ── Bước 1: Gỡ source khỏi NotebookLM (queue, non-blocking) ──
    steps.step1_nlm_remove = await safeStep('step1_nlm_remove', async () => {
      if (!fileData.notebooklm_source_id) {
        return { success: true, skipped: true, reason: 'no_source_id' };
      }
      const taskId = await enqueueSourceRemove(c.env, {
        uid: user.uid,
        fileId,
        sourceId: fileData.notebooklm_source_id,
        notebookId: fileData.notebook_id || '',
      });
      return { success: true, queued: true, task_id: taskId };
    });

    // ── Bước 2: Dời file Drive sang _Archive_Trash_90Days (queue, non-blocking) ──
    steps.step2_drive_archive = await safeStep('step2_drive_archive', async () => {
      if (!fileData.drive_file_id) {
        return { success: true, skipped: true, reason: 'no_drive_file_id' };
      }
      const taskId = await enqueueDriveArchive(c.env, {
        uid: user.uid,
        fileId,
        driveFileId: fileData.drive_file_id,
        targetFolder: ARCHIVE_FOLDER,
      });
      return { success: true, queued: true, task_id: taskId };
    });

    // ── Bước 3: Soft delete Firestore (synchronous, bắt buộc) ──
    const now = new Date().toISOString();
    steps.step3_firestore = await softDeleteFirestore(c.env, user.uid, fileId, now);

    // ── Bước 3b: Soft delete file trên PC (Recycle Bin) — cần local_path ──
    steps.step3_local_softdelete = await safeStep('step3_local_softdelete', async () => {
      if (!fileData.local_path) {
        return { success: true, skipped: true, reason: 'no_local_path' };
      }
      const taskId = await enqueueSoftDeleteLocal(c.env, {
        uid: user.uid,
        fileId,
        localPath: fileData.local_path,
      });
      return { success: true, queued: true, task_id: taskId };
    });

    // ── Bước 4: Hẹn hard delete sau 90 ngày (cron hard_delete.js xử lý) ──
    steps.step4_scheduled_hard_delete = await safeStep('step4_scheduled_hard_delete', async () => {
      await firestoreSet(c.env, `archived_files/${fileId}`, {
        id: fileId,
        uid: user.uid,
        filename: fileData.filename || '',
        sha256: fileData.sha256 || '',
        drive_file_id: fileData.drive_file_id || '',
        local_path: fileData.local_path || '',
        user_email: fileData.user_email || '',
        status: 'archived',
        archived_at: now,
        hard_delete_at: steps.step3_firestore.hard_delete_at,
      });
      return {
        success: true,
        hard_delete_at: steps.step3_firestore.hard_delete_at,
        retention_days: HARD_DELETE_DAYS,
      };
    });

    return withCors(c.json({
      status: 'archived',
      file_id: fileId,
      hard_delete_at: steps.step3_firestore.hard_delete_at,
      message: `File sẽ bị xóa hoàn toàn sau ${HARD_DELETE_DAYS} ngày`,
      steps,
    }), origin);
  } catch (err) {
    console.error('Delete error:', err);
    return withCors(c.json({ error: 'Xóa file thất bại', detail: err.message }, 500), origin);
  }
}));

/**
 * Bước 3: Soft delete trong Firestore (synchronous).
 * Ghi status='archived' + hard_delete_at = now + 90 ngày vào doc file.
 */
async function softDeleteFirestore(env, uid, fileId, now) {
  const hardDeleteAt = new Date(
    Date.now() + HARD_DELETE_DAYS * 24 * 60 * 60 * 1000
  ).toISOString();

  await firestoreSet(env, `users/${uid}/files/${fileId}`, {
    status: 'archived',
    archived_at: now,
    hard_delete_at: hardDeleteAt,
    updated_at: now,
  });

  return { success: true, hard_delete_at: hardDeleteAt, retention_days: HARD_DELETE_DAYS };
}

export default router;
