// src/routes/ai/research.js — Deep Research bất đồng bộ (§3.5) (<200 lines)
// POST /api/ai/research (user, 202 + queue research_start)
// GET  /api/ai/research (?course_id=&status=) | GET /api/ai/research/:jobId
// PATCH /api/ai/research/:jobId (agent — cập nhật status/progress/error)

import { Hono } from 'hono';
import { requireAuth, requireAuthOrAgent, resolveTargetUid } from '../../lib/auth.js';
import {
  firestoreGet, firestoreSet, firestoreList, fromFirestoreDoc,
} from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';
import { enqueueTask, NLM_QUEUE } from '../../lib/tasks.js';
import { resolveNotebookId } from '../../lib/notebooks.js';

const router = new Hono();
const JOB_STATUSES = ['queued', 'running', 'done', 'failed'];

/** Danh sách research_jobs của user (lọc phía Worker — Firestore REST không WHERE tốt) */
export async function listResearchJobs(env, uid, pageSize = 100) {
  const resp = await firestoreList(env, `users/${uid}/research_jobs`, pageSize);
  return (resp.documents || []).map(fromFirestoreDoc);
}

/** Lấy 1 job theo id (null nếu không tồn tại) */
export async function getResearchJob(env, uid, jobId) {
  const doc = await firestoreGet(env, `users/${uid}/research_jobs/${jobId}`);
  return doc ? fromFirestoreDoc(doc) : null;
}

function missingUid(c, origin) {
  return withCors(c.json({
    error: 'Thiếu uid',
    detail: 'Agent gọi bằng X-Agent-Secret phải gửi uid (body.uid hoặc ?uid=)',
  }, 400), origin);
}

/**
 * POST /api/ai/research
 * Body: { course_id, notebook_id?, query, mode:'deep'|'fast' }
 * → 202 { job_id, task_id, status:'queued' } + queue research_start
 */
router.post('/', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const body = await c.req.json();
    const { course_id } = body;
    const query = String(body.query || '').trim();
    const mode = body.mode === 'fast' ? 'fast' : 'deep';

    if (!course_id || !query) {
      return withCors(c.json({ error: 'course_id và query là bắt buộc' }, 400), origin);
    }

    const notebookId = await resolveNotebookId(c.env, user.uid, {
      notebookId: body.notebook_id || '',
      courseId: course_id,
    });

    const jobId = crypto.randomUUID();
    const now = new Date().toISOString();

    const taskId = await enqueueTask(c.env, NLM_QUEUE, {
      action: 'research_start',
      uid: user.uid,
      job_id: jobId,
      notebook_id: notebookId,
      query,
      mode,
    });

    await firestoreSet(c.env, `users/${user.uid}/research_jobs/${jobId}`, {
      id: jobId,
      course_id,
      notebook_id: notebookId,
      query,
      mode,
      status: 'queued',
      progress: '',
      sources_found: 0,
      sources_imported: 0,
      task_id: taskId,
      error: '',
      created_at: now,
      updated_at: now,
    });

    return withCors(c.json({ job_id: jobId, task_id: taskId, status: 'queued' }, 202), origin);
  } catch (err) {
    console.error('Research start error:', err);
    return withCors(c.json({ error: 'Tạo research job thất bại', detail: err.message }, 500), origin);
  }
}));

/** GET /api/ai/research?course_id=&status= → { jobs } */
router.get('/', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const courseId = c.req.query('course_id') || '';
    const status = c.req.query('status') || '';

    let jobs = await listResearchJobs(c.env, user.uid);
    if (courseId) jobs = jobs.filter((j) => j.course_id === courseId);
    if (status) jobs = jobs.filter((j) => j.status === status);
    jobs.sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')));

    return withCors(c.json({ jobs }), origin);
  } catch (err) {
    console.error('Research list error:', err);
    return withCors(c.json({ error: 'Lấy danh sách research job thất bại', detail: err.message }, 500), origin);
  }
}));

/** GET /api/ai/research/:jobId → { job } */
router.get('/:jobId', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const job = await getResearchJob(c.env, user.uid, c.req.param('jobId'));
    if (!job) {
      return withCors(c.json({ error: 'Research job không tìm thấy' }, 404), origin);
    }
    return withCors(c.json({ job }), origin);
  } catch (err) {
    console.error('Research detail error:', err);
    return withCors(c.json({ error: 'Lấy research job thất bại', detail: err.message }, 500), origin);
  }
}));

/**
 * PATCH /api/ai/research/:jobId (agent)
 * Body: { uid?, status?, progress?, error?, sources_found?, sources_imported? }
 */
router.patch('/:jobId', requireAuthOrAgent(async (c) => {
  const jobId = c.req.param('jobId');
  const origin = c.req.header('Origin') || '';

  try {
    const body = await c.req.json();
    const uid = resolveTargetUid(c, body.uid, c.req.query('uid'));
    if (!uid) return missingUid(c, origin);

    const job = await getResearchJob(c.env, uid, jobId);
    if (!job) {
      return withCors(c.json({ error: 'Research job không tìm thấy' }, 404), origin);
    }

    const patch = { updated_at: new Date().toISOString() };
    if (body.status !== undefined) {
      if (!JOB_STATUSES.includes(body.status)) {
        return withCors(c.json({
          error: `status không hợp lệ. Cho phép: ${JOB_STATUSES.join(', ')}`,
        }, 400), origin);
      }
      patch.status = body.status;
    }
    if (body.progress !== undefined) patch.progress = String(body.progress);
    if (body.error !== undefined) patch.error = String(body.error);
    if (body.sources_found !== undefined) {
      patch.sources_found = parseInt(body.sources_found, 10) || 0;
    }
    if (body.sources_imported !== undefined) {
      patch.sources_imported = parseInt(body.sources_imported, 10) || 0;
    }

    if (Object.keys(patch).length === 1) {
      return withCors(c.json({ error: 'Không có trường nào để cập nhật' }, 400), origin);
    }

    await firestoreSet(c.env, `users/${uid}/research_jobs/${jobId}`, patch);
    const updated = await getResearchJob(c.env, uid, jobId);

    return withCors(c.json({ job: updated }), origin);
  } catch (err) {
    console.error('Research patch error:', err);
    return withCors(c.json({ error: 'Cập nhật research job thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;

