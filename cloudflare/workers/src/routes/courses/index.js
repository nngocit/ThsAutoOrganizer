// src/routes/courses/index.js — CRUD courses (<150 lines)

import { Hono } from 'hono';
import { requireAuth } from '../../lib/auth.js';
import { firestoreSet, firestoreList, firestoreGet, fromFirestoreDoc } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';

const router = new Hono();

/**
 * GET /api/courses
 * Trả về danh sách courses của user.
 */
router.get('/', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';
  try {
    const resp = await firestoreList(c.env, `users/${user.uid}/courses`, 100);
    const courses = (resp.documents || []).map(fromFirestoreDoc);
    courses.sort((a, b) => (a.name || '').localeCompare(b.name || '', 'vi'));
    return withCors(c.json({ courses }), origin);
  } catch (err) {
    console.error('List courses error:', err);
    return withCors(c.json({ error: 'Không thể lấy danh sách môn học', detail: err.message }, 500), origin);
  }
}));

/**
 * POST /api/courses
 * Body: { name, code?, subject_key, major?, notebooklm_id? }
 * Tạo môn học mới.
 */
router.post('/', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';
  try {
    const body = await c.req.json();
    const { name, code, subject_key, major, notebooklm_id } = body;

    if (!name || !subject_key) {
      return withCors(c.json({ error: 'name và subject_key là bắt buộc' }, 400), origin);
    }

    const docId = crypto.randomUUID();
    const now = new Date().toISOString();

    await firestoreSet(c.env, `users/${user.uid}/courses/${docId}`, {
      id: docId,
      name,
      code: code || '',
      subject_key,
      major: major || '',
      notebooklm_id: notebooklm_id || '',
      created_at: now,
      updated_at: now,
    });

    return withCors(c.json({ id: docId, status: 'created' }, 201), origin);
  } catch (err) {
    console.error('Create course error:', err);
    return withCors(c.json({ error: 'Tạo môn học thất bại', detail: err.message }, 500), origin);
  }
}));

/**
 * PUT /api/courses/:courseId/notebooklm
 * Body: { notebooklm_id }
 * Liên kết môn học với NotebookLM notebook ID.
 */
router.put('/:courseId/notebooklm', requireAuth(async (c) => {
  const user = c.get('user');
  const courseId = c.req.param('courseId');
  const origin = c.req.header('Origin') || '';
  try {
    const { notebooklm_id } = await c.req.json();
    if (!notebooklm_id) {
      return withCors(c.json({ error: 'notebooklm_id là bắt buộc' }, 400), origin);
    }

    const doc = await firestoreGet(c.env, `users/${user.uid}/courses/${courseId}`);
    if (!doc) {
      return withCors(c.json({ error: 'Môn học không tìm thấy' }, 404), origin);
    }

    await firestoreSet(c.env, `users/${user.uid}/courses/${courseId}`, {
      notebooklm_id,
      updated_at: new Date().toISOString(),
    });

    return withCors(c.json({ status: 'updated', course_id: courseId, notebooklm_id }), origin);
  } catch (err) {
    console.error('Update notebooklm error:', err);
    return withCors(c.json({ error: 'Cập nhật thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
