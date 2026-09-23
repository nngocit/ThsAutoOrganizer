// src/routes/sync/index.js — Task queue API cho Python local agent (<150 lines)
// Python agent poll queue này để lấy tasks và báo cáo kết quả

import { Hono } from 'hono';
import { requireAgentAuth } from '../../lib/auth.js';
import { firestoreList, firestoreGet, firestoreSet, fromFirestoreDoc } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';

const router = new Hono();

const VALID_QUEUES = new Set(['nlm_task_queue', 'drive_task_queue']);

/**
 * GET /api/tasks/:queue
 * Python local agent gọi endpoint này để lấy các task pending.
 * Auth: X-Agent-Secret header.
 * Returns: { tasks: [...] }
 */
router.get('/:queue', requireAgentAuth(async (c) => {
  const queueName = c.req.param('queue');
  const origin = c.req.header('Origin') || '';

  if (!VALID_QUEUES.has(queueName)) {
    return withCors(c.json({ error: `Queue không hợp lệ: ${queueName}` }, 400), origin);
  }

  try {
    const limit = parseInt(c.req.query('limit') || '10', 10);
    const resp = await firestoreList(c.env, queueName, Math.min(limit, 50));
    const allDocs = (resp.documents || []).map(fromFirestoreDoc);

    // Chỉ trả về tasks pending
    const pendingTasks = allDocs
      .filter((t) => t.status === 'pending')
      .slice(0, limit);

    return withCors(c.json({ tasks: pendingTasks, queue: queueName }), origin);
  } catch (err) {
    console.error(`Get tasks ${queueName} error:`, err);
    return withCors(c.json({ error: 'Không thể lấy tasks', detail: err.message }, 500), origin);
  }
}));

/**
 * PATCH /api/tasks/:queue/:taskId
 * Python agent báo cáo kết quả xử lý task.
 * Body: { status: "done" | "failed", error?: string }
 */
router.patch('/:queue/:taskId', requireAgentAuth(async (c) => {
  const queueName = c.req.param('queue');
  const taskId = c.req.param('taskId');
  const origin = c.req.header('Origin') || '';

  if (!VALID_QUEUES.has(queueName)) {
    return withCors(c.json({ error: `Queue không hợp lệ: ${queueName}` }, 400), origin);
  }

  try {
    const body = await c.req.json();
    const { status, error: errorMsg, result } = body;

    const validStatuses = new Set(['done', 'failed', 'processing', 'skipped_ext']);
    if (!validStatuses.has(status)) {
      return withCors(c.json({ error: `status không hợp lệ: ${status}` }, 400), origin);
    }

    const existingDoc = await firestoreGet(c.env, `${queueName}/${taskId}`);
    if (!existingDoc) {
      return withCors(c.json({ error: 'Task không tìm thấy' }, 404), origin);
    }

    const now = new Date().toISOString();
    const updateData = { status, processed_at: now };
    if (errorMsg) updateData.error = errorMsg;
    if (result) updateData.result = typeof result === 'string' ? result : JSON.stringify(result);

    await firestoreSet(c.env, `${queueName}/${taskId}`, updateData);

    // Nếu là NLM source_add done hoặc skipped_ext: cập nhật notebooklm_sync_status trên file
    const taskData = fromFirestoreDoc(existingDoc);
    if (queueName === 'nlm_task_queue' && taskData.action === 'source_add' && (status === 'done' || status === 'skipped_ext')) {
      if (taskData.uid && taskData.file_id) {
        const resultStr = typeof result === 'string' ? result : (result ? JSON.stringify(result) : '');
        const skipped = status === 'skipped_ext' || resultStr.startsWith('skipped');
        await firestoreSet(c.env, `users/${taskData.uid}/files/${taskData.file_id}`, {
          notebooklm_sync_status: status === 'skipped_ext' ? 'skipped_ext' : (skipped ? 'skipped' : 'synced'),
          notebooklm_source_id: skipped ? '' : resultStr,
          updated_at: now,
        });
      }
    }

    return withCors(c.json({ status: 'updated', task_id: taskId }), origin);
  } catch (err) {
    console.error(`Update task ${taskId} error:`, err);
    return withCors(c.json({ error: 'Cập nhật task thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
