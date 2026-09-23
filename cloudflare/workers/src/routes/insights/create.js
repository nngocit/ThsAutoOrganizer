// src/routes/insights/create.js — POST /api/ai/insights (<120 lines)

import { Hono } from 'hono';
import { requireAuthOrAgent, resolveTargetUid } from '../../lib/auth.js';
import { firestoreSet } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';

const router = new Hono();
const VALID_TYPES = new Set(['quiz', 'summary', 'outline', 'qa', 'deep_research']);

/**
 * POST /api/ai/insights
 * Body: { id?, course_id?, insight_type, title, content, citations?, created_by?, created_at?, uid? }
 * course_id rỗng → 'all' (câu hỏi Quick Research phạm vi "Tất cả môn học")
 * Returns: { id, status: "created" }
 */
router.post('/', requireAuthOrAgent(async (c) => {
  const origin = c.req.header('Origin') || '';

  try {
    const body = await c.req.json();
    const uid = resolveTargetUid(c, body.uid, c.req.query('uid'));
    if (!uid) {
      return withCors(c.json({
        error: 'Thiếu uid',
        detail: 'Agent gọi bằng X-Agent-Secret phải gửi uid (body.uid hoặc ?uid=)',
      }, 400), origin);
    }
    const {
      insight_type,
      title,
      content,
      citations = '[]',
      created_by = 'agent',
    } = body;
    const course_id = String(body.course_id || '').trim() || 'all';

    // Validate required fields
    if (!insight_type || !title || !content) {
      return withCors(c.json({
        error: 'Thiếu trường bắt buộc: insight_type, title, content',
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

    const docId = String(body.id || '').trim() || crypto.randomUUID();
    const now = new Date().toISOString();

    // Chuẩn hóa citations về string JSON
    const citationsStr = typeof citations === 'string'
      ? citations
      : JSON.stringify(citations);

    await firestoreSet(c.env, `users/${uid}/ai_insights/${docId}`, {
      id: docId,
      course_id,
      insight_type,
      title,
      content,
      citations: citationsStr,
      created_by: safeCreatedBy,
      created_at: body.created_at || now,
      updated_at: now,
    });

    return withCors(c.json({ id: docId, status: 'created' }, 201), origin);
  } catch (err) {
    console.error('Create insight error:', err);
    return withCors(c.json({ error: 'Tạo insight thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
