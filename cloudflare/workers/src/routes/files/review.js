// src/routes/files/review.js — Hàng đợi duyệt nguồn (§3.4) (<170 lines)
// GET  /api/files/review        → {files, total} (mặc định status=unreviewed)
// POST /api/files/:id/review    → {'approved'|'rejected'} + steps

import { Hono } from 'hono';
import { requireAuth } from '../../lib/auth.js';
import { firestoreGet, firestoreSet, fromFirestoreDoc } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';
import { REVIEW_STATUSES, normalizeFileDoc } from '../../lib/folders.js';
import { listUserFiles, HIDDEN_STATUSES } from '../../lib/file_lookup.js';
import { enqueueSourceAdd, enqueueSourceRemove } from '../../lib/tasks.js';

const router = new Hono();

const DECISIONS = ['approved', 'rejected'];

/** GET /api/files/review?status=unreviewed&course_id=&limit=50 */
router.get('/review', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const status = c.req.query('status') || 'unreviewed';
    const courseId = c.req.query('course_id') || '';
    const limit = Math.min(parseInt(c.req.query('limit') || '50', 10) || 50, 200);

    if (status !== 'all' && !REVIEW_STATUSES.includes(status)) {
      return withCors(c.json({
        error: `status không hợp lệ: ${status}`,
        detail: `Cho phép: ${REVIEW_STATUSES.join(', ')}, all`,
      }, 400), origin);
    }

    const files = (await listUserFiles(c.env, user.uid, 200))
      .filter((f) => !HIDDEN_STATUSES.includes(f.status)) // chỉ file đã upload thật
      .map(normalizeFileDoc)
      .filter((f) => (status === 'all' ? true : f.review_status === status))
      .filter((f) => (courseId ? f.course_id === courseId : true))
      .sort((a, b) => (b.updated_at || b.created_at || '').localeCompare(a.updated_at || a.created_at || ''));

    return withCors(c.json({ files: files.slice(0, limit), total: files.length }), origin);
  } catch (err) {
    console.error('List review queue error:', err);
    return withCors(c.json({ error: 'Không thể lấy hàng đợi duyệt', detail: err.message }, 500), origin);
  }
}));

/**
 * POST /api/files/:fileId/review — Body {review_status, note?}
 * approved → queue source_add nếu chưa sync (NO-LOOP: bỏ qua file output)
 * rejected → queue source_remove nếu có notebooklm_source_id; KHÔNG xoá file Drive
 */
router.post('/:fileId/review', requireAuth(async (c) => {
  const user = c.get('user');
  const fileId = c.req.param('fileId');
  const origin = c.req.header('Origin') || '';

  try {
    const body = await c.req.json();
    const decision = body.review_status;
    const note = body.note || '';

    if (!DECISIONS.includes(decision)) {
      return withCors(c.json({
        error: `review_status không hợp lệ: ${decision}`,
        detail: 'Cho phép: approved, rejected',
      }, 400), origin);
    }

    const fileDoc = await firestoreGet(c.env, `users/${user.uid}/files/${fileId}`);
    if (!fileDoc) {
      return withCors(c.json({ error: 'File không tìm thấy hoặc không thuộc về bạn' }, 404), origin);
    }

    const file = normalizeFileDoc(fromFirestoreDoc(fileDoc));
    const now = new Date().toISOString();
    const steps = {};

    // Ghi kết quả duyệt (synchronous)
    await firestoreSet(c.env, `users/${user.uid}/files/${fileId}`, {
      review_status: decision,
      review_note: note,
      reviewed_at: now,
      updated_at: now,
    });
    steps.step_review_firestore = { success: true, review_status: decision, reviewed_at: now };

    if (decision === 'approved') {
      const synced = file.notebooklm_sync_status === 'synced' && !!file.notebooklm_source_id;
      if (synced) {
        steps.step_nlm_source_add = { success: true, skipped: true, reason: 'already_synced' };
      } else {
        // enqueueSourceAdd tự chặn (Lớp 2 NO-LOOP) khi is_output === true
        const taskId = await enqueueSourceAdd(c.env, {
          uid: user.uid,
          fileId,
          courseId: file.course_id || '',
          notebookId: file.notebook_id || '',
          filename: file.filename || '',
          subject: file.subject || '',
          folderPath: file.folder_path || '',
          isOutput: file.is_output,
          localPath: file.local_path || '',
          driveFileId: file.drive_file_id || '',
        });
        steps.step_nlm_source_add = taskId
          ? { success: true, queued: true, task_id: taskId }
          : { success: true, skipped: true, reason: 'is_output_no_loop' };
      }
    } else {
      // rejected: gỡ source khỏi NotebookLM (nếu có), KHÔNG xoá file Drive
      if (file.notebooklm_source_id) {
        const taskId = await enqueueSourceRemove(c.env, {
          uid: user.uid,
          fileId,
          sourceId: file.notebooklm_source_id,
          notebookId: file.notebook_id || '',
        });
        steps.step_nlm_source_remove = { success: true, queued: true, task_id: taskId };
      } else {
        steps.step_nlm_source_remove = { success: true, skipped: true, reason: 'no_source_id' };
      }
      steps.step_drive_kept = {
        success: true,
        note: 'Giữ nguyên file trên Drive (chỉ gỡ khỏi NotebookLM)',
      };
    }

    return withCors(c.json({
      status: 'updated',
      file_id: fileId,
      review_status: decision,
      steps,
    }), origin);
  } catch (err) {
    console.error('Review file error:', err);
    return withCors(c.json({ error: 'Duyệt nguồn thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
