// src/routes/files/retry.js — POST /api/files/:id/retry (<60 lines)
import { Hono } from 'hono';
import { requireAuthOrAgent, resolveTargetUid, getFallbackUid } from '../../lib/auth.js';
import { firestoreGet, firestoreSet, fromFirestoreDoc } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';
import { enqueueTask, NLM_QUEUE } from '../../lib/tasks.js';

const router = new Hono();

router.post('/:id/retry', requireAuthOrAgent(async (c) => {
  const origin = c.req.header('Origin') || '';
  const fileId = c.req.param('id');
  const targetUid = resolveTargetUid(c, null, c.req.query('uid')) || await getFallbackUid(c.env);

  if (!targetUid) {
    return withCors(c.json({ error: 'UID không xác định' }, 400), origin);
  }

  try {
    const fileDoc = await firestoreGet(c.env, `users/${targetUid}/files/${fileId}`);
    if (!fileDoc) {
      return withCors(c.json({ error: 'Không tìm thấy tệp tin' }, 404), origin);
    }

    const file = fromFirestoreDoc(fileDoc);
    const now = new Date().toISOString();

    const courseName = file.course_name || file.subject || '';
    const localFolderName = file.local_folder_name || file.subject || '';
    const driveViewLink = file.drive_view_link || file.webViewLink || (file.drive_file_id ? `https://drive.google.com/file/d/${file.drive_file_id}/view` : '');

    // Re-queue task in nlm_task_queue và tự động dispatch GitHub Actions
    const taskId = await enqueueTask(c.env, NLM_QUEUE, {
      action: 'source_add',
      file_id: fileId,
      filename: file.filename,
      file_url: driveViewLink,
      drive_file_id: file.drive_file_id || '',
      notebooklm_id: file.notebooklm_id || '',
      course_id: file.course_id || '',
      course_name: courseName,
      subject: localFolderName || courseName,
      local_folder_name: localFolderName,
      document_type: file.document_type || 'giao_trinh',
      local_path: file.local_path || (localFolderName ? `${localFolderName}/${file.filename}` : file.filename),
      uid: targetUid,
      owner_email: c.get('user')?.email || '',
    });

    // Update file status
    await firestoreSet(c.env, `users/${targetUid}/files/${fileId}`, {
      notebooklm_sync_status: 'pending',
      local_sync_status: 'downloading',
      updated_at: now,
    });

    return withCors(c.json({
      success: true,
      task_id: taskId,
      message: 'Đã kích hoạt lại tác vụ đồng bộ cho tệp tin',
    }), origin);
  } catch (err) {
    console.error('Retry file error:', err);
    return withCors(c.json({ error: 'Lỗi kích hoạt lại tệp tin', detail: err.message }, 500), origin);
  }
}));

/**
 * PATCH /api/files/:id/local-status
 * Python Local Agent cập nhật trạng thái đã tải về local thành công.
 */
router.patch('/:id/local-status', requireAuthOrAgent(async (c) => {
  const origin = c.req.header('Origin') || '';
  const fileId = c.req.param('id');
  const body = await c.req.json();
  const targetUid = resolveTargetUid(c, body.uid, c.req.query('uid')) || await getFallbackUid(c.env);

  if (!targetUid) {
    return withCors(c.json({ error: 'UID không xác định' }, 400), origin);
  }

  try {
    const { local_sync_status, local_path } = body;
    const patch = { updated_at: new Date().toISOString() };
    if (local_sync_status) patch.local_sync_status = local_sync_status;
    if (local_path) patch.local_path = local_path;

    await firestoreSet(c.env, `users/${targetUid}/files/${fileId}`, patch);
    return withCors(c.json({ success: true, file_id: fileId, local_sync_status }), origin);
  } catch (err) {
    console.error('Update local status error:', err);
    return withCors(c.json({ error: 'Lỗi cập nhật local status', detail: err.message }, 500), origin);
  }
}));

/**
 * POST /api/files/reconcile-local
 * Đẩy tác vụ 'reconcile_local' vào nlm_task_queue để Local Agent quét đĩa và cập nhật trạng thái thực tế.
 */
router.post('/reconcile-local', requireAuthOrAgent(async (c) => {
  const origin = c.req.header('Origin') || '';
  const body = await c.req.json().catch(() => ({}));
  const courseId = c.req.query('course_id') || body.course_id || '';
  const targetUid = resolveTargetUid(c, body.uid, c.req.query('uid')) || await getFallbackUid(c.env);

  if (!targetUid) {
    return withCors(c.json({ error: 'UID không xác định' }, 400), origin);
  }

  try {
    const taskId = crypto.randomUUID();
    const now = new Date().toISOString();

    await firestoreSet(c.env, `nlm_task_queue/${taskId}`, {
      id: taskId,
      action: 'reconcile_local',
      course_id: courseId,
      uid: targetUid,
      owner_email: c.get('user')?.email || '',
      status: 'pending',
      created_at: now,
    });

    return withCors(c.json({
      success: true,
      task_id: taskId,
      message: 'Đã phát lệnh đối soát tệp tin thực tế cho Local Agent',
    }), origin);
  } catch (err) {
    console.error('Reconcile local error:', err);
    return withCors(c.json({ error: 'Lỗi phát lệnh đối soát', detail: err.message }, 500), origin);
  }
}));

export default router;
