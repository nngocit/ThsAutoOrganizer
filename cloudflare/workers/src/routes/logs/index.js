// src/routes/logs/index.js — System Logs API (<130 lines)
// Quản lý và thu thập logs lỗi toàn hệ thống trên Firestore (users/{uid}/system_logs)

import { Hono } from 'hono';
import { requireAuthOrAgent, resolveTargetUid, getFallbackUid } from '../../lib/auth.js';
import { firestoreGet, firestoreSet, firestoreList, fromFirestoreDoc } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';

const router = new Hono();

/**
 * POST /api/logs
 * Ghi nhận log sự cố từ Local Agent hoặc Web UI.
 */
router.post('/', requireAuthOrAgent(async (c) => {
  const origin = c.req.header('Origin') || '';
  const body = await c.req.json();
  const targetUid = resolveTargetUid(c, body.uid, c.req.query('uid')) || await getFallbackUid(c.env);

  if (!targetUid) {
    return withCors(c.json({ error: 'UID không xác định' }, 400), origin);
  }

  try {
    const logId = `log_${crypto.randomUUID()}`;
    const now = new Date().toISOString();

    const logEntry = {
      id: logId,
      timestamp: now,
      level: body.level || 'ERROR',
      source: body.source || 'local_agent',
      module: body.module || '',
      action: body.action || '',
      subject: body.subject || '',
      file_name: body.file_name || body.filename || '',
      message: body.message || 'Lỗi không xác định',
      error_detail: typeof body.error_detail === 'object' ? JSON.stringify(body.error_detail) : String(body.error_detail || ''),
      context: typeof body.context === 'object' ? body.context : {},
      resolved: false,
      created_at: now,
    };

    await firestoreSet(c.env, `users/${targetUid}/system_logs/${logId}`, logEntry);

    return withCors(c.json({
      status: 'created',
      log_id: logId,
      entry: logEntry,
    }, 201), origin);
  } catch (err) {
    console.error('Create log error:', err);
    return withCors(c.json({ error: 'Ghi log thất bại', detail: err.message }, 500), origin);
  }
}));

/**
 * GET /api/logs
 * Truy vấn danh sách logs theo bộ lọc.
 */
router.get('/', requireAuthOrAgent(async (c) => {
  const origin = c.req.header('Origin') || '';
  const targetUid = resolveTargetUid(c, null, c.req.query('uid')) || await getFallbackUid(c.env);

  if (!targetUid) {
    return withCors(c.json({ error: 'UID không xác định' }, 400), origin);
  }

  try {
    const limit = Math.min(parseInt(c.req.query('limit') || '50', 10), 100);
    const filterLevel = c.req.query('level');
    const filterResolved = c.req.query('resolved');

    const resp = await firestoreList(c.env, `users/${targetUid}/system_logs`, limit);
    let logs = (resp.documents || []).map(fromFirestoreDoc);

    if (filterLevel) {
      logs = logs.filter((l) => l.level === filterLevel);
    }
    if (filterResolved !== undefined) {
      const isResolved = filterResolved === 'true';
      logs = logs.filter((l) => Boolean(l.resolved) === isResolved);
    }

    // Sắp xếp giảm dần theo thời gian
    logs.sort((a, b) => (b.timestamp || '').localeCompare(a.timestamp || ''));

    return withCors(c.json({ logs, count: logs.length }), origin);
  } catch (err) {
    console.error('List logs error:', err);
    return withCors(c.json({ error: 'Lỗi truy vấn logs', detail: err.message }, 500), origin);
  }
}));

/**
 * PATCH /api/logs/:logId/resolve
 * Đánh dấu log lỗi đã được giải quyết.
 */
router.patch('/:logId/resolve', requireAuthOrAgent(async (c) => {
  const origin = c.req.header('Origin') || '';
  const logId = c.req.param('logId');
  const targetUid = resolveTargetUid(c, null, c.req.query('uid')) || await getFallbackUid(c.env);

  if (!targetUid) {
    return withCors(c.json({ error: 'UID không xác định' }, 400), origin);
  }

  try {
    const doc = await firestoreGet(c.env, `users/${targetUid}/system_logs/${logId}`);
    if (!doc) {
      return withCors(c.json({ error: 'Log không tìm thấy' }, 404), origin);
    }

    const now = new Date().toISOString();
    await firestoreSet(c.env, `users/${targetUid}/system_logs/${logId}`, {
      resolved: true,
      resolved_at: now,
      resolved_by: c.get('user')?.email || 'user',
    });

    return withCors(c.json({ status: 'resolved', log_id: logId }), origin);
  } catch (err) {
    console.error('Resolve log error:', err);
    return withCors(c.json({ error: 'Cập nhật trạng thái log thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
