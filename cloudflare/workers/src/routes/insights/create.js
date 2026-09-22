// src/routes/insights/create.js — POST /api/ai/insights (<120 lines)

import { Hono } from 'hono';
import { requireAuth } from '../../lib/auth.js';
import { firestoreSet } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';

const router = new Hono();
const VALID_TYPES = new Set(['quiz', 'summary', 'outline', 'qa']);

/**
 * POST /api/ai/insights
 * Body: { course_id, insight_type, title, content, citations?, created_by? }
 * Returns: { id, status: "created" }
 */
router.post('/', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const body = await c.req.json();
    const {
      course_id,
      insight_type,
      title,
      content,
      citations = '[]',
      created_by = 'agent',
    } = body;

    // Validate required fields
    if (!course_id || !insight_type || !title || !content) {
      return withCors(c.json({
        error: 'Thiếu trường bắt buộc: course_id, insight_type, title, content',
      }, 400), origin);
    }

    if (!VALID_TYPES.has(insight_type)) {
      return withCors(c.json({
        error: `insight_type không hợp lệ. Các giá trị cho phép: ${[...VALID_TYPES].join(', ')}`,
      }, 400), origin);
    }

    // Validate created_by
    const validCreatedBy = new Set(['agent', 'web_user']);
    const safeCreatedBy = validCreatedBy.has(created_by) ? created_by : 'agent';

    const docId = crypto.randomUUID();
    const now = new Date().toISOString();

    // Chuẩn hóa citations về string JSON
    const citationsStr = typeof citations === 'string'
      ? citations
      : JSON.stringify(citations);

    await firestoreSet(c.env, `users/${user.uid}/ai_insights/${docId}`, {
      id: docId,
      course_id,
      insight_type,
      title,
      content,
      citations: citationsStr,
      created_by: safeCreatedBy,
      created_at: now,
      updated_at: now,
    });

    return withCors(c.json({ id: docId, status: 'created' }, 201), origin);
  } catch (err) {
    console.error('Create insight error:', err);
    return withCors(c.json({ error: 'Tạo insight thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
