// src/routes/chat/sessions.js — GET|POST /api/chat/sessions (§3.2) (<120 lines)

import { Hono } from 'hono';
import { requireAuth } from '../../lib/auth.js';
import { firestoreSet } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';
import { parseArray, normalizeSession, listSessions } from '../../lib/chat_sessions.js';
import { resolveNotebookId } from '../../lib/notebooks.js';

const router = new Hono();

/** GET /api/chat/sessions?course_id=&status=active|archived (mặc định active) */
router.get('/', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const courseId = c.req.query('course_id') || '';
    const status = c.req.query('status') || 'active';

    if (status && !['active', 'archived', 'all'].includes(status)) {
      return withCors(c.json({
        error: `status không hợp lệ: ${status}`,
        detail: 'Cho phép: active, archived, all',
      }, 400), origin);
    }

    const sessions = await listSessions(c.env, user.uid, {
      courseId,
      status: status === 'all' ? '' : status,
    });

    return withCors(c.json({
      sessions: sessions.map(normalizeSession),
      total: sessions.length,
    }), origin);
  } catch (err) {
    console.error('List chat sessions error:', err);
    return withCors(c.json({ error: 'Không thể lấy danh sách phiên chat', detail: err.message }, 500), origin);
  }
}));

/**
 * POST /api/chat/sessions — Body {course_id?, notebook_id?, title?, source_ids?[]}
 * → 201 {id, notebook_id, orphan_warning}
 */
router.post('/', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const body = await c.req.json();
    const courseId = body.course_id || '';
    const sourceIds = parseArray(body.source_ids);
    const notebookId = await resolveNotebookId(c.env, user.uid, {
      notebookId: body.notebook_id || '',
      courseId,
    });

    const id = crypto.randomUUID();
    const now = new Date().toISOString();
    const orphan = !notebookId;

    await firestoreSet(c.env, `users/${user.uid}/chat_sessions/${id}`, {
      id,
      course_id: courseId,
      notebook_id: notebookId,
      title: body.title || 'Cuộc trò chuyện mới',
      selected_source_ids: JSON.stringify(sourceIds), // §2: mảng lưu dạng JSON string
      message_count: 0,
      last_message_at: '',
      status: 'active',
      origin: 'web',
      orphan_warning: orphan,
      orphan_note: orphan ? 'Môn học chưa liên kết NotebookLM (notebooklm_id trống)' : '',
      archived_at: '',
      user_email: user.email || '',
      created_at: now,
      updated_at: now,
    });

    return withCors(c.json({
      id,
      course_id: courseId,
      notebook_id: notebookId,
      title: body.title || 'Cuộc trò chuyện mới',
      selected_source_ids: sourceIds,
      status: 'active',
      orphan_warning: orphan,
    }, 201), origin);
  } catch (err) {
    console.error('Create chat session error:', err);
    return withCors(c.json({ error: 'Tạo phiên chat thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
