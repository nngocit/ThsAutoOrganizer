// src/routes/insights/list.js — GET /api/ai/insights (<100 lines)

import { Hono } from 'hono';
import { requireAuth } from '../../lib/auth.js';
import { firestoreList, fromFirestoreDoc } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';

const router = new Hono();

/**
 * GET /api/ai/insights
 * Query params: course_id, type (insight_type), limit (default 50)
 * Returns: { insights: [...], total: N }
 */
router.get('/', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const courseId = c.req.query('course_id') || '';
    const insightType = c.req.query('type') || '';
    const limit = Math.min(parseInt(c.req.query('limit') || '50', 10), 200);

    // Lấy toàn bộ insights của user (lọc phía Worker)
    const resp = await firestoreList(c.env, `users/${user.uid}/ai_insights`, 200);
    let insights = (resp.documents || []).map(fromFirestoreDoc);

    // Lọc theo course_id và insight_type
    insights = insights.filter((ins) => {
      if (courseId && ins.course_id !== courseId) return false;
      if (insightType && ins.insight_type !== insightType) return false;
      return true;
    });

    // Sắp xếp: mới nhất trước
    insights.sort((a, b) => {
      const ta = a.created_at || '';
      const tb = b.created_at || '';
      return tb.localeCompare(ta);
    });

    // Parse citations JSON nếu là string
    const result = insights.slice(0, limit).map((ins) => ({
      ...ins,
      citations: (() => {
        try {
          return typeof ins.citations === 'string' ? JSON.parse(ins.citations) : (ins.citations || []);
        } catch {
          return [];
        }
      })(),
    }));

    return withCors(c.json({ insights: result, total: result.length }), origin);
  } catch (err) {
    console.error('List insights error:', err);
    return withCors(c.json({ error: 'Không thể lấy danh sách insights', detail: err.message }, 500), origin);
  }
}));

export default router;
