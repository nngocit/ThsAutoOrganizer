// src/routes/ai/artifact.js — Artifacts Downloader (§3.6) (<190 lines)
// POST /api/ai/artifact/download (user, 202 + queue artifact_download)
// POST /api/ai/artifact/complete (agent — tạo file doc ket_qua, KHÔNG queue source_add)
// GET  /api/ai/artifacts (user, ?course_id= — files is_output === true)

import { Hono } from 'hono';
import { requireAuth, requireAuthOrAgent, resolveTargetUid } from '../../lib/auth.js';
import { firestoreSet } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';
import { enqueueTask, NLM_QUEUE } from '../../lib/tasks.js';
import { OUTPUT_FOLDER, normalizeFileDoc } from '../../lib/folders.js';
import { isValidSha256, normalizeSha256, stableFileId } from '../../lib/file_ids.js';
import { listUserFiles, findFileBySha256 } from '../../lib/file_lookup.js';
import { resolveNotebookId } from '../../lib/notebooks.js';

const router = new Hono();
const ARTIFACT_FORMATS = ['pptx', 'docx', 'pdf'];

/**
 * POST /api/ai/artifact/download
 * Body: { course_id, artifact_id?, artifact_name?, format:'pptx'|'docx'|'pdf', notebook_id? }
 * → 202 { task_id } + queue artifact_download (target 04_Ket_Qua_Xuat_Ban)
 */
router.post('/artifact/download', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const body = await c.req.json();
    const { course_id } = body;
    if (!course_id) {
      return withCors(c.json({ error: 'course_id là bắt buộc' }, 400), origin);
    }

    const format = ARTIFACT_FORMATS.includes(body.format) ? body.format : 'pptx';
    const notebookId = await resolveNotebookId(c.env, user.uid, {
      notebookId: body.notebook_id || '',
      courseId: course_id,
    });

    const taskId = await enqueueTask(c.env, NLM_QUEUE, {
      action: 'artifact_download',
      uid: user.uid,
      course_id,
      notebook_id: notebookId,
      artifact_id: body.artifact_id || '',
      artifact_name: body.artifact_name || '',
      format,
      target_folder: OUTPUT_FOLDER,
    });

    return withCors(c.json({ task_id: taskId, status: 'queued' }, 202), origin);
  } catch (err) {
    console.error('Artifact download error:', err);
    return withCors(c.json({ error: 'Tạo artifact_download task thất bại', detail: err.message }, 500), origin);
  }
}));

/**
 * POST /api/ai/artifact/complete (agent)
 * Body: { uid, course_id, filename, local_path, drive_file_id, sha256, size_bytes, artifact_name? }
 * → file doc document_type:'ket_qua', is_output:true, source_kind:'artifact',
 *   review_status:'approved'. NO-LOOP: KHÔNG queue source_add.
 * → { file_id, is_output: true }
 */
router.post('/artifact/complete', requireAuthOrAgent(async (c) => {
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

    const filename = String(body.filename || '').trim();
    if (!filename) {
      return withCors(c.json({ error: 'filename là bắt buộc' }, 400), origin);
    }

    const sha = isValidSha256(normalizeSha256(body.sha256 || ''))
      ? normalizeSha256(body.sha256)
      : '';
    const now = new Date().toISOString();

    // Idempotent: cùng sha256 → merge thông tin, không tạo doc trùng
    const existing = sha ? await findFileBySha256(c.env, uid, sha) : null;
    const fileId = existing?._id || (sha ? stableFileId(sha) : crypto.randomUUID());

    if (existing) {
      await firestoreSet(c.env, `users/${uid}/files/${fileId}`, {
        drive_file_id: body.drive_file_id || existing.drive_file_id || '',
        local_path: body.local_path || existing.local_path || '',
        size_bytes: body.size_bytes ? String(body.size_bytes) : (existing.size_bytes || '0'),
        is_output: true,
        updated_at: now,
      });
    } else {
      await firestoreSet(c.env, `users/${uid}/files/${fileId}`, {
        id: fileId,
        filename,
        subject: body.artifact_name || filename,
        document_type: 'ket_qua',
        folder_path: OUTPUT_FOLDER,
        course_id: body.course_id || '',
        status: 'uploaded',
        is_output: true,
        size_bytes: body.size_bytes ? String(body.size_bytes) : '0',
        sha256: sha,
        drive_file_id: body.drive_file_id || '',
        local_path: body.local_path || '',
        source_kind: 'artifact',
        review_status: 'approved',
        review_note: '',
        reviewed_at: '',
        notebooklm_source_id: '',
        notebooklm_sync_status: 'not_applicable',
        created_at: now,
        updated_at: now,
      });
    }

    // NO-LOOP lớp 2: tuyệt đối không enqueueSourceAdd cho file 04_Ket_Qua_Xuat_Ban
    return withCors(c.json({
      file_id: fileId,
      is_output: true,
      merged: !!existing,
    }, existing ? 200 : 201), origin);
  } catch (err) {
    console.error('Artifact complete error:', err);
    return withCors(c.json({ error: 'Ghi nhận artifact thất bại', detail: err.message }, 500), origin);
  }
}));

/** GET /api/ai/artifacts?course_id= → { artifacts } (files is_output === true) */
router.get('/artifacts', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const courseId = c.req.query('course_id') || '';
    let artifacts = (await listUserFiles(c.env, user.uid))
      .map(normalizeFileDoc)
      .filter((f) => f.is_output === true && f.status !== 'archived');
    if (courseId) artifacts = artifacts.filter((f) => f.course_id === courseId);
    artifacts.sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')));

    return withCors(c.json({ artifacts }), origin);
  } catch (err) {
    console.error('Artifacts list error:', err);
    return withCors(c.json({ error: 'Lấy danh sách artifacts thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;

