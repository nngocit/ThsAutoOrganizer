// src/routes/exam/generate.js — POST /api/exam/sets/generate (user) (§3.7) (<90 lines)
// 202 { job_id, task_id } + queue exam_generate (agent poll → tạo đề → POST /api/exam/sets)

import { Hono } from 'hono';
import { requireAuth } from '../../lib/auth.js';
import { withCors } from '../../lib/cors.js';
import { enqueueTask, NLM_QUEUE } from '../../lib/tasks.js';
import { resolveNotebookId } from '../../lib/notebooks.js';

const router = new Hono();

// Khớp cap phía agent-create (§3.7): 100 flashcard / 20 essay
const MAX_FLASHCARDS = 100;
const MAX_ESSAYS = 20;

const clamp = (val, fallback, max) => {
  const n = parseInt(val, 10);
  if (!Number.isFinite(n) || n < 1) return fallback;
  return Math.min(n, max);
};

/**
 * POST /api/exam/sets/generate
 * Body: { course_id, notebook_id?, flashcard_count=50, essay_count=5, title? }
 * → 202 { job_id, task_id, status:'queued' }
 */
router.post('/generate', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const body = await c.req.json();
    const { course_id } = body;
    if (!course_id) {
      return withCors(c.json({ error: 'course_id là bắt buộc' }, 400), origin);
    }

    const notebookId = await resolveNotebookId(c.env, user.uid, {
      notebookId: body.notebook_id || '',
      courseId: course_id,
    });

    if (!notebookId) {
      return withCors(c.json({
        error: 'Môn học chưa liên kết NotebookLM (notebooklm_id trống)',
      }, 400), origin);
    }

    const jobId = crypto.randomUUID();
    const flashcardCount = clamp(body.flashcard_count, 50, MAX_FLASHCARDS);
    const essayCount = clamp(body.essay_count, 5, MAX_ESSAYS);

    const taskId = await enqueueTask(c.env, NLM_QUEUE, {
      action: 'exam_generate',
      uid: user.uid,
      job_id: jobId, // agent dùng làm source_job_id khi POST /api/exam/sets
      course_id,
      notebook_id: notebookId,
      flashcard_count: flashcardCount,
      essay_count: essayCount,
      title: String(body.title || '').trim(),
    });

    return withCors(c.json({ job_id: jobId, task_id: taskId, status: 'queued' }, 202), origin);
  } catch (err) {
    console.error('Exam generate error:', err);
    return withCors(c.json({ error: 'Tạo exam_generate task thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
