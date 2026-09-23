// src/routes/exam/sets.js — CRUD bộ đề ôn thi (§3.7) (<200 lines)
// POST /api/exam/sets (agent, 201, cap 100 flashcard / 20 essay)
// GET  /api/exam/sets (user — KHÔNG trả flashcards/essays, chỉ counts)
// GET  /api/exam/sets/:id (user — đầy đủ, đã JSON.parse)
// DELETE /api/exam/sets/:id (user)

import { Hono } from 'hono';
import { requireAuth, requireAuthOrAgent, resolveTargetUid } from '../../lib/auth.js';
import {
  firestoreGet, firestoreSet, firestoreList, firestoreDelete, fromFirestoreDoc,
} from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';
import { notebookForCourse } from '../../lib/notebooks.js';

const router = new Hono();
const MAX_FLASHCARDS = 100;
const MAX_ESSAYS = 20;

/** Parse JSON string an toàn → mảng (quy ước §2: mảng/object lưu dạng JSON string) */
export function parseJsonArray(val) {
  if (Array.isArray(val)) return val;
  try {
    const parsed = JSON.parse(val || '[]');
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

async function listExamSets(env, uid, pageSize = 100) {
  const resp = await firestoreList(env, `users/${uid}/exam_sets`, pageSize);
  return (resp.documents || []).map(fromFirestoreDoc);
}

async function getExamSet(env, uid, setId) {
  const doc = await firestoreGet(env, `users/${uid}/exam_sets/${setId}`);
  return doc ? fromFirestoreDoc(doc) : null;
}

/**
 * POST /api/exam/sets (agent)
 * Body: { uid, course_id, title, flashcards[], essays[], source_job_id? }
 * → 201 { set_id, flashcard_count, essay_count }
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

    const { course_id } = body;
    const title = String(body.title || '').trim();
    if (!course_id || !title) {
      return withCors(c.json({ error: 'course_id và title là bắt buộc' }, 400), origin);
    }

    const flashcards = (Array.isArray(body.flashcards) ? body.flashcards : [])
      .slice(0, MAX_FLASHCARDS);
    const essays = (Array.isArray(body.essays) ? body.essays : [])
      .slice(0, MAX_ESSAYS);
    if (flashcards.length === 0 && essays.length === 0) {
      return withCors(c.json({ error: 'Cần ít nhất 1 flashcard hoặc essay' }, 400), origin);
    }

    const notebookId = body.notebook_id
      || await notebookForCourse(c.env, uid, course_id);
    const setId = crypto.randomUUID();
    const now = new Date().toISOString();

    // Quy ước §2: mảng lưu dạng JSON string
    await firestoreSet(c.env, `users/${uid}/exam_sets/${setId}`, {
      id: setId,
      course_id,
      notebook_id: notebookId,
      title,
      flashcards: JSON.stringify(flashcards),
      essays: JSON.stringify(essays),
      attempts: '[]',
      source_job_id: body.source_job_id || '',
      created_at: now,
      updated_at: now,
    });

    return withCors(c.json({
      set_id: setId,
      flashcard_count: flashcards.length,
      essay_count: essays.length,
    }, 201), origin);
  } catch (err) {
    console.error('Exam set create error:', err);
    return withCors(c.json({ error: 'Tạo bộ đề thất bại', detail: err.message }, 500), origin);
  }
}));

/** GET /api/exam/sets?course_id= → { sets } (KHÔNG trả flashcards/essays) */
router.get('/', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const courseId = c.req.query('course_id') || '';
    let sets = await listExamSets(c.env, user.uid);
    if (courseId) sets = sets.filter((s) => s.course_id === courseId);
    sets.sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')));

    const summary = sets.map((s) => {
      const { flashcards, essays, ...rest } = s;
      return {
        ...rest,
        flashcard_count: parseJsonArray(flashcards).length,
        essay_count: parseJsonArray(essays).length,
        attempts_count: parseJsonArray(s.attempts).length,
      };
    });

    return withCors(c.json({ sets: summary }), origin);
  } catch (err) {
    console.error('Exam sets list error:', err);
    return withCors(c.json({ error: 'Lấy danh sách bộ đề thất bại', detail: err.message }, 500), origin);
  }
}));

/** GET /api/exam/sets/:id → { set } đầy đủ (flashcards/essays/attempts đã JSON.parse) */
router.get('/:id', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const set = await getExamSet(c.env, user.uid, c.req.param('id'));
    if (!set) {
      return withCors(c.json({ error: 'Bộ đề không tìm thấy' }, 404), origin);
    }

    return withCors(c.json({
      set: {
        ...set,
        flashcards: parseJsonArray(set.flashcards),
        essays: parseJsonArray(set.essays),
        attempts: parseJsonArray(set.attempts),
      },
    }), origin);
  } catch (err) {
    console.error('Exam set detail error:', err);
    return withCors(c.json({ error: 'Lấy bộ đề thất bại', detail: err.message }, 500), origin);
  }
}));

/** DELETE /api/exam/sets/:id → { status:'deleted' } */
router.delete('/:id', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const setId = c.req.param('id');
    const set = await getExamSet(c.env, user.uid, setId);
    if (!set) {
      return withCors(c.json({ error: 'Bộ đề không tìm thấy' }, 404), origin);
    }

    await firestoreDelete(c.env, `users/${user.uid}/exam_sets/${setId}`);
    return withCors(c.json({ status: 'deleted', set_id: setId }), origin);
  } catch (err) {
    console.error('Exam set delete error:', err);
    return withCors(c.json({ error: 'Xoá bộ đề thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
