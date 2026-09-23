// src/routes/chat/messages.js — GET|POST /api/chat/sessions/:id/messages (§3.2) (<140 lines)
// POST trả 202 kèm job_id = id task trong nlm_task_queue (action 'chat_query').

import { Hono } from 'hono';
import { requireAuth } from '../../lib/auth.js';
import { firestoreSet } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';
import { NLM_QUEUE, enqueueTask } from '../../lib/tasks.js';
import { resolveNotebookId } from '../../lib/notebooks.js';
import {
  parseArray, normalizeMessage, getOwnedSession, listMessages, touchSession,
} from '../../lib/chat_sessions.js';

const router = new Hono();

/** GET /api/chat/sessions/:id/messages?since=<ISO>&limit=100 (polling realtime) */
router.get('/:id/messages', requireAuth(async (c) => {
  const user = c.get('user');
  const sessionId = c.req.param('id');
  const origin = c.req.header('Origin') || '';

  try {
    const session = await getOwnedSession(c.env, user.uid, sessionId);
    if (!session) {
      return withCors(c.json({ error: 'Phiên chat không tìm thấy' }, 404), origin);
    }

    const since = c.req.query('since') || '';
    const limit = Math.min(parseInt(c.req.query('limit') || '100', 10) || 100, 200);

    const all = await listMessages(c.env, user.uid, sessionId, 200);
    const filtered = since ? all.filter((m) => (m.created_at || '') > since) : all;

    return withCors(c.json({
      messages: filtered.slice(-limit).map(normalizeMessage),
      server_time: new Date().toISOString(),
    }), origin);
  } catch (err) {
    console.error('List chat messages error:', err);
    return withCors(c.json({ error: 'Không thể lấy tin nhắn', detail: err.message }, 500), origin);
  }
}));

/**
 * POST /api/chat/sessions/:id/messages — Body {content, source_ids?[], citation_style?}
 * → 202 {message_id, job_id, status:'queued'} + queue nlm_task_queue action 'chat_query'
 */
router.post('/:id/messages', requireAuth(async (c) => {
  const user = c.get('user');
  const sessionId = c.req.param('id');
  const origin = c.req.header('Origin') || '';

  try {
    const session = await getOwnedSession(c.env, user.uid, sessionId);
    if (!session) {
      return withCors(c.json({ error: 'Phiên chat không tìm thấy' }, 404), origin);
    }
    if (session.status === 'archived') {
      return withCors(c.json({ error: 'Phiên chat đã được lưu trữ — không thể gửi thêm' }, 409), origin);
    }

    const body = await c.req.json();
    const content = String(body.content || '').trim();
    if (!content) {
      return withCors(c.json({ error: 'content là bắt buộc' }, 400), origin);
    }

    // Nguồn chọn: ưu tiên body, fallback danh sách đã lưu trong session (Source Selector)
    const sourceIds = body.source_ids !== undefined
      ? parseArray(body.source_ids)
      : parseArray(session.selected_source_ids);
    const citationStyle = body.citation_style || 'auto';

    const notebookId = await resolveNotebookId(c.env, user.uid, {
      notebookId: session.notebook_id || '',
      courseId: session.course_id || '',
    });

    const messageId = crypto.randomUUID();
    const now = new Date().toISOString();

    await firestoreSet(c.env, `users/${user.uid}/chat_sessions/${sessionId}/messages/${messageId}`, {
      id: messageId,
      session_id: sessionId,
      role: 'user',
      content,
      citations: '[]',
      citation_style: citationStyle,
      reference_block: '',
      model: '',
      nlm_job_id: '',
      status: 'pending',
      error: '',
      created_at: now,
    });

    // Queue chat_query → Python agent xử lý qua NotebookLM CLI
    const jobId = await enqueueTask(c.env, NLM_QUEUE, {
      action: 'chat_query',
      uid: user.uid,
      session_id: sessionId,
      message_id: messageId,
      notebook_id: notebookId,
      prompt: content,
      source_ids: JSON.stringify(sourceIds),
      citation_style: citationStyle,
    });

    await firestoreSet(c.env, `users/${user.uid}/chat_sessions/${sessionId}/messages/${messageId}`, {
      nlm_job_id: jobId,
    });

    await touchSession(c.env, user.uid, sessionId, {
      message_count: (parseInt(session.message_count || 0, 10) || 0) + 1,
      orphan_warning: !notebookId,
      orphan_note: notebookId ? '' : 'Môn học chưa liên kết NotebookLM (notebooklm_id trống)',
    });

    return withCors(c.json({
      message_id: messageId,
      job_id: jobId,
      status: 'queued',
      notebook_id: notebookId,
    }, 202), origin);
  } catch (err) {
    console.error('Send chat message error:', err);
    return withCors(c.json({ error: 'Gửi tin nhắn thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
