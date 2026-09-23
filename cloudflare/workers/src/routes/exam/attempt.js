// src/routes/exam/attempt.js — POST /api/exam/sets/:id/attempt (user) (§3.7) (<90 lines)
// Ghi nhận 1 lần làm bài; chỉ giữ 50 attempts gần nhất (FIFO cắt đầu).

import { Hono } from 'hono';
import { requireAuth } from '../../lib/auth.js';
import { firestoreGet, firestoreSet, fromFirestoreDoc } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';
import { parseJsonArray } from './sets.js';

const router = new Hono();
const MAX_ATTEMPTS = 50;

/**
 * POST /api/exam/sets/:id/attempt
 * Body: { score, total, answers? }
 * → { status:'recorded', attempts_count }
 */
router.post('/:id/attempt', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const setId = c.req.param('id');
    const body = await c.req.json();

    const score = Number(body.score);
    const total = Number(body.total);
    if (!Number.isFinite(score) || !Number.isFinite(total) || total <= 0) {
      return withCors(c.json({ error: 'score và total là bắt buộc (total > 0)' }, 400), origin);
    }

    const doc = await firestoreGet(c.env, `users/${user.uid}/exam_sets/${setId}`);
    if (!doc) {
      return withCors(c.json({ error: 'Bộ đề không tìm thấy' }, 404), origin);
    }
    const set = fromFirestoreDoc(doc);

    const now = new Date().toISOString();
    const attempts = parseJsonArray(set.attempts);
    attempts.push({
      id: crypto.randomUUID(),
      score,
      total,
      answers: body.answers !== undefined ? body.answers : null,
      at: now,
    });

    // Giữ 50 lần gần nhất
    const kept = attempts.slice(-MAX_ATTEMPTS);

    await firestoreSet(c.env, `users/${user.uid}/exam_sets/${setId}`, {
      attempts: JSON.stringify(kept),
      updated_at: now,
    });

    return withCors(c.json({ status: 'recorded', attempts_count: kept.length }), origin);
  } catch (err) {
    console.error('Exam attempt error:', err);
    return withCors(c.json({ error: 'Ghi nhận kết quả làm bài thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
