// src/routes/insights/remove.js — DELETE /api/ai/insights/:id (<60 lines)

import { Hono } from 'hono';
import { requireAuth } from '../../lib/auth.js';
import { firestoreGet, firestoreDelete } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';

const router = new Hono();

/**
 * DELETE /api/ai/insights/:id
 * Xóa insight của user hiện tại.
 * Kiểm tra ownership trước khi xóa.
 */
router.delete('/:id', requireAuth(async (c) => {
  const user = c.get('user');
  const insightId = c.req.param('id');
  const origin = c.req.header('Origin') || '';

  try {
    // Verify document tồn tại (Firestore path bao gồm uid nên đã implicit auth check)
    const doc = await firestoreGet(c.env, `users/${user.uid}/ai_insights/${insightId}`);
    if (!doc) {
      return withCors(c.json({ error: 'Insight không tìm thấy' }, 404), origin);
    }

    await firestoreDelete(c.env, `users/${user.uid}/ai_insights/${insightId}`);
    return withCors(c.json({ status: 'deleted', id: insightId }), origin);
  } catch (err) {
    console.error('Delete insight error:', err);
    return withCors(c.json({ error: 'Xóa insight thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
