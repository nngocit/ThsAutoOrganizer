// src/routes/chat/session_detail.js — GET|PATCH|DELETE /api/chat/sessions/:id (§3.2) (<140 lines)

import { Hono } from 'hono';
import { requireAuth } from '../../lib/auth.js';
import { firestoreDelete, firestoreSet, firestoreList } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';
import {
  SESSION_STATUSES, parseArray, normalizeSession, normalizeMessage,
  getOwnedSession, listMessages,
} from '../../lib/chat_sessions.js';

const router = new Hono();

/** GET /api/chat/sessions/:id → {session, messages} (50 message mới nhất) */
router.get('/:id', requireAuth(async (c) => {
  const user = c.get('user');
  const sessionId = c.req.param('id');
  const origin = c.req.header('Origin') || '';

  try {
    const session = await getOwnedSession(c.env, user.uid, sessionId);
    if (!session) {
      return withCors(c.json({ error: 'Phiên chat không tìm thấy' }, 404), origin);
    }

    const messages = await listMessages(c.env, user.uid, sessionId, 50);

    return withCors(c.json({
      session: normalizeSession(session),
      messages: messages.map(normalizeMessage),
    }), origin);
  } catch (err) {
    console.error('Get chat session error:', err);
    return withCors(c.json({ error: 'Không thể lấy phiên chat', detail: err.message }, 500), origin);
  }
}));

/** PATCH /api/chat/sessions/:id — Body {title?, status?, selected_source_ids?[]} */
router.patch('/:id', requireAuth(async (c) => {
  const user = c.get('user');
  const sessionId = c.req.param('id');
  const origin = c.req.header('Origin') || '';

  try {
    const session = await getOwnedSession(c.env, user.uid, sessionId);
    if (!session) {
      return withCors(c.json({ error: 'Phiên chat không tìm thấy' }, 404), origin);
    }

    const body = await c.req.json();
    const now = new Date().toISOString();
    const patch = { updated_at: now };

    if (body.title !== undefined) patch.title = String(body.title);

    if (body.status !== undefined) {
      if (!SESSION_STATUSES.includes(body.status)) {
        return withCors(c.json({
          error: `status không hợp lệ: ${body.status}`,
          detail: `Cho phép: ${SESSION_STATUSES.join(', ')}`,
        }, 400), origin);
      }
      patch.status = body.status;
      patch.archived_at = body.status === 'archived' ? now : '';
    }

    if (body.selected_source_ids !== undefined) {
      patch.selected_source_ids = JSON.stringify(parseArray(body.selected_source_ids));
    }

    await firestoreSet(c.env, `users/${user.uid}/chat_sessions/${sessionId}`, patch);

    return withCors(c.json({
      status: 'updated',
      session: normalizeSession({ ...session, ...patch }),
    }), origin);
  } catch (err) {
    console.error('Patch chat session error:', err);
    return withCors(c.json({ error: 'Cập nhật phiên chat thất bại', detail: err.message }, 500), origin);
  }
}));

/**
 * DELETE /api/chat/sessions/:id
 * Mặc định SOFT: status='archived' + archived_at.
 * ?hard=1 → xoá thật session + toàn bộ messages.
 */
router.delete('/:id', requireAuth(async (c) => {
  const user = c.get('user');
  const sessionId = c.req.param('id');
  const origin = c.req.header('Origin') || '';

  try {
    const session = await getOwnedSession(c.env, user.uid, sessionId);
    if (!session) {
      return withCors(c.json({ error: 'Phiên chat không tìm thấy' }, 404), origin);
    }

    const now = new Date().toISOString();
    const hard = c.req.query('hard') === '1' || c.req.query('hard') === 'true';

    if (!hard) {
      await firestoreSet(c.env, `users/${user.uid}/chat_sessions/${sessionId}`, {
        status: 'archived',
        archived_at: now,
        updated_at: now,
      });
      return withCors(c.json({ status: 'archived', session_id: sessionId, hard: false }), origin);
    }

    // Xoá thật: messages trước, session sau (tránh orphan sub-collection)
    const resp = await firestoreList(
      c.env, `users/${user.uid}/chat_sessions/${sessionId}/messages`, 200
    );
    const msgs = resp.documents || [];
    for (const doc of msgs) {
      const mid = doc.name.split('/').pop();
      if (mid) await firestoreDelete(c.env, `users/${user.uid}/chat_sessions/${sessionId}/messages/${mid}`);
    }
    await firestoreDelete(c.env, `users/${user.uid}/chat_sessions/${sessionId}`);

    return withCors(c.json({
      status: 'deleted',
      session_id: sessionId,
      hard: true,
      messages_deleted: msgs.length,
    }), origin);
  } catch (err) {
    console.error('Delete chat session error:', err);
    return withCors(c.json({ error: 'Xóa phiên chat thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
