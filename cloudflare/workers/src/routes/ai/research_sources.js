// src/routes/ai/research_sources.js — POST /api/ai/research/:jobId/sources (agent) (§3.5) (<160 lines)
// Agent import nguồn deep research → file doc document_type:'unverified_web',
// review_status:'unreviewed', source_kind:'deep_research', is_output:false.
// NO-LOOP: TUYỆT ĐỐI KHÔNG queue source_add — nguồn web chờ người dùng duyệt (§3.4).

import { Hono } from 'hono';
import { requireAuthOrAgent, resolveTargetUid } from '../../lib/auth.js';
import { firestoreSet, fromFirestoreDoc } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';
import { FOLDER_MAP } from '../../lib/folders.js';
import { isValidSha256, normalizeSha256, stableFileId } from '../../lib/file_ids.js';
import { findFileBySha256 } from '../../lib/file_lookup.js';
import { getResearchJob } from './research.js';

const router = new Hono();
const MAX_SOURCES_PER_CALL = 50;

/**
 * POST /api/ai/research/:jobId/sources
 * Body: { uid?, sources: [{ filename, drive_file_id, sha256, url, title,
 *                           authors, year, publisher, doi, local_path, size_bytes }] }
 * → 201 { imported: [{ file_id, filename }], job }
 */
router.post('/:jobId/sources', requireAuthOrAgent(async (c) => {
  const jobId = c.req.param('jobId');
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

    const sources = Array.isArray(body.sources) ? body.sources : [];
    if (sources.length === 0) {
      return withCors(c.json({ error: 'sources phải là mảng không rỗng' }, 400), origin);
    }

    const job = await getResearchJob(c.env, uid, jobId);
    if (!job) {
      return withCors(c.json({ error: 'Research job không tìm thấy' }, 404), origin);
    }

    const now = new Date().toISOString();
    const imported = [];

    for (const s of sources.slice(0, MAX_SOURCES_PER_CALL)) {
      const filename = String(s.filename || s.title || '').trim();
      if (!filename) continue;

      const sha = isValidSha256(normalizeSha256(s.sha256 || ''))
        ? normalizeSha256(s.sha256)
        : '';

      // Chống trùng theo sha256 (bỏ qua pending_upload/archived)
      if (sha) {
        const dup = await findFileBySha256(c.env, uid, sha);
        if (dup) continue;
      }

      const fileId = sha ? stableFileId(sha) : crypto.randomUUID();

      await firestoreSet(c.env, `users/${uid}/files/${fileId}`, {
        id: fileId,
        filename,
        subject: s.subject || '',
        document_type: 'unverified_web',
        folder_path: FOLDER_MAP.unverified_web,
        course_id: job.course_id || '',
        status: 'uploaded',
        is_output: false,
        size_bytes: s.size_bytes ? String(s.size_bytes) : '0',
        sha256: sha,
        drive_file_id: s.drive_file_id || '',
        local_path: s.local_path || '',
        url: s.url || '',
        title: s.title || filename,
        authors: s.authors || '',
        year: s.year ? String(s.year) : '',
        publisher: s.publisher || '',
        doi: s.doi || '',
        source_kind: 'deep_research',
        review_status: 'unreviewed',
        review_note: '',
        reviewed_at: '',
        notebooklm_source_id: '',
        notebooklm_sync_status: 'pending',
        research_job_id: jobId,
        created_at: now,
        updated_at: now,
      });

      imported.push({ file_id: fileId, filename });
    }

    const sourcesImported = (parseInt(job.sources_imported || 0, 10) || 0) + imported.length;
    await firestoreSet(c.env, `users/${uid}/research_jobs/${jobId}`, {
      sources_imported: sourcesImported,
      updated_at: now,
    });

    const updated = await getResearchJob(c.env, uid, jobId);

    return withCors(c.json({ imported, job: updated }, 201), origin);
  } catch (err) {
    console.error('Research sources import error:', err);
    return withCors(c.json({ error: 'Import nguồn research thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
