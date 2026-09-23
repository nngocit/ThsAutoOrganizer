// src/routes/ai/insights.js — Quản lý AI Insights cho tài liệu (<100 lines)

import { Hono } from 'hono';
import { requireAuth, requireAuthOrAgent, resolveTargetUid, getFallbackUid } from '../../lib/auth.js';
import { firestoreSet, firestoreList, firestoreDelete, fromFirestoreDoc } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';

const router = new Hono();

/**
 * GET /api/ai/insights
 * Lấy danh sách AI insights của user (hoặc theo course_id / file_id).
 */
router.get('/', requireAuthOrAgent(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';
  const targetUid = resolveTargetUid(c, user, c.req.query('uid')) || await getFallbackUid(c.env);

  if (!targetUid) {
    return withCors(c.json({ error: 'UID không xác định' }, 400), origin);
  }

  try {
    const courseId = c.req.query('course_id');
    const fileId = c.req.query('file_id');
    const limit = parseInt(c.req.query('limit') || '50', 10);

    const resp = await firestoreList(c.env, `users/${targetUid}/ai_insights`, limit);
    let items = (resp.documents || []).map(fromFirestoreDoc);

    if (courseId) items = items.filter((i) => i.course_id === courseId);
    if (fileId) items = items.filter((i) => i.file_id === fileId);

    items.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
    return withCors(c.json({ insights: items }), origin);
  } catch (err) {
    console.error('List insights error:', err);
    return withCors(c.json({ error: 'Không thể lấy insights', detail: err.message }, 500), origin);
  }
}));

/**
 * POST /api/ai/insights
 * Tạo mới insight cho tài liệu.
 */
router.post('/', requireAuthOrAgent(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';
  const targetUid = resolveTargetUid(c, user, c.req.query('uid')) || await getFallbackUid(c.env);

  try {
    const body = await c.req.json();
    const { title, content, type = 'summary', course_id = '', file_id = '' } = body;

    if (!title || !content) {
      return withCors(c.json({ error: 'title và content là bắt buộc' }, 400), origin);
    }

    const docId = crypto.randomUUID();
    const now = new Date().toISOString();

    await firestoreSet(c.env, `users/${targetUid}/ai_insights/${docId}`, {
      id: docId,
      title,
      content,
      type,
      course_id,
      file_id,
      created_at: now,
      updated_at: now,
    });

    return withCors(c.json({ id: docId, status: 'created' }, 201), origin);
  } catch (err) {
    console.error('Create insight error:', err);
    return withCors(c.json({ error: 'Tạo insight thất bại', detail: err.message }, 500), origin);
  }
}));

/**
 * DELETE /api/ai/insights/:id
 * Xóa một insight.
 */
router.delete('/:id', requireAuthOrAgent(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';
  const targetUid = resolveTargetUid(c, user, c.req.query('uid')) || await getFallbackUid(c.env);
  const insightId = c.req.param('id');

  try {
    await firestoreDelete(c.env, `users/${targetUid}/ai_insights/${insightId}`);
    return withCors(c.json({ status: 'deleted', id: insightId }), origin);
  } catch (err) {
    console.error('Delete insight error:', err);
    return withCors(c.json({ error: 'Xóa insight thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
