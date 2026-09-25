// src/routes/files/list.js — GET /api/files (<100 lines)
// List files của user; filter: subject, status, document_type, course_id,
// review_status, is_output, source_kind (§3.1)

import { Hono } from 'hono';
import { requireAuthOrAgent, resolveTargetUid, getFallbackUid } from '../../lib/auth.js';
import { withCors } from '../../lib/cors.js';
import { normalizeFileDoc } from '../../lib/folders.js';
import { listUserFiles, HIDDEN_STATUSES } from '../../lib/file_lookup.js';

const router = new Hono();

/** Query ?is_output=true|false → true | false | null (null = không lọc) */
function parseBool(value) {
  if (value === 'true' || value === '1') return true;
  if (value === 'false' || value === '0') return false;
  return null;
}

/**
 * GET /api/files
 * Query: subject, status, document_type, course_id, review_status, is_output,
 *        source_kind, limit (default 50, max 200)
 * Trả về: { files: [...], total: N, all_count: M }
 *
 * NOTE: Firestore REST không hỗ trợ compound WHERE tốt trên edge runtime.
 * Chiến lược: Lấy toàn bộ (pageSize=200), lọc phía Worker.
 */
router.get('/', requireAuthOrAgent(async (c) => {
  const origin = c.req.header('Origin') || '';
  const targetUid = resolveTargetUid(c, null, c.req.query('uid')) || await getFallbackUid(c.env);

  if (!targetUid) {
    return withCors(c.json({ error: 'UID không xác định' }, 400), origin);
  }

  try {
    const subject = c.req.query('subject') || '';
    const status = c.req.query('status') || '';
    const docType = c.req.query('document_type') || '';
    const courseId = c.req.query('course_id') || '';
    const reviewStatus = c.req.query('review_status') || '';
    const sourceKind = c.req.query('source_kind') || '';
    const isOutput = parseBool(c.req.query('is_output'));
    const limit = Math.min(parseInt(c.req.query('limit') || '50', 10) || 50, 200);

    // Chuẩn hoá: luôn có review_status / is_output / source_kind cho UI
    const files = (await listUserFiles(c.env, targetUid, 200)).map(normalizeFileDoc);

    const filtered = files.filter((f) => {
      if (HIDDEN_STATUSES.includes(f.status)) return false; // Ẩn archived + pending_upload
      if (courseId) {
        const matchesCourseId = (f.course_id === courseId);
        const matchesCourseSubject = subject && (f.subject === subject || f.local_folder_name === subject);
        if (!matchesCourseId && !matchesCourseSubject) return false;
      } else if (subject && f.subject !== subject && f.local_folder_name !== subject) {
        return false;
      }
      if (status && f.status !== status) return false;
      if (docType && f.document_type !== docType) return false;
      if (reviewStatus && f.review_status !== reviewStatus) return false;
      if (sourceKind && f.source_kind !== sourceKind) return false;
      if (isOutput !== null && f.is_output !== isOutput) return false;
      return true;
    });

    // Sắp xếp: mới nhất trước
    filtered.sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''));
    const paginated = filtered.slice(0, limit);

    // Thêm flag is_new (<24h) cho UI
    const now = Date.now();
    const result = paginated.map((f) => ({
      ...f,
      is_new: f.created_at
        ? now - new Date(f.created_at).getTime() < 24 * 60 * 60 * 1000
        : false,
    }));

    return withCors(
      c.json({ files: result, total: result.length, all_count: filtered.length }),
      origin
    );
  } catch (err) {
    console.error('List files error:', err);
    return withCors(c.json({ error: 'Không thể lấy danh sách files', detail: err.message }, 500), origin);
  }
}));

export default router;
