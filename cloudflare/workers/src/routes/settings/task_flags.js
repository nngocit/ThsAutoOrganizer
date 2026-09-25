// src/routes/settings/task_flags.js — Công tắc bật/tắt G1+G2 (<70 lines)
// GET  /api/settings/task-flags → đọc cờ hiện hành
// PUT  /api/settings/task-flags → { queryMode?: 'query'|'legacy', recoveryEnabled?: bool, staleMinutes?: number }
// Cho phép cả user (Bearer) lẫn agent (X-Agent-Secret).

import { Hono } from 'hono';
import { requireAuthOrAgent } from '../../lib/auth.js';
import { withCors } from '../../lib/cors.js';
import { getTaskFlags, setTaskFlags } from '../../lib/feature_flags.js';

const router = new Hono();

router.get('/', requireAuthOrAgent(async (c) => {
  const origin = c.req.header('Origin') || '';
  try {
    const flags = await getTaskFlags(c.env, { forceRefresh: true });
    return withCors(c.json({ flags }), origin);
  } catch (err) {
    console.error('Get task flags error:', err);
    return withCors(c.json({ error: 'Không đọc được công tắc', detail: err.message }, 500), origin);
  }
}));

router.put('/', requireAuthOrAgent(async (c) => {
  const origin = c.req.header('Origin') || '';
  try {
    const body = await c.req.json().catch(() => ({}));
    const flags = await setTaskFlags(c.env, body || {});
    return withCors(c.json({ status: 'updated', flags }), origin);
  } catch (err) {
    console.error('Update task flags error:', err);
    return withCors(c.json({ error: 'Cập nhật công tắc thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
