// src/routes/chat/sources.js — GET /api/chat/sources (§3.2 Source Selector) (<80 lines)
// Trả danh sách nguồn có thể chọn cho 1 môn; loại review_status='rejected'
// và mọi doc chưa upload xong (status != 'uploaded').

import { Hono } from 'hono';
import { requireAuth } from '../../lib/auth.js';
import { withCors } from '../../lib/cors.js';
import { normalizeFileDoc } from '../../lib/folders.js';
import { listUserFiles } from '../../lib/file_lookup.js';

const router = new Hono();

router.get('/sources', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const courseId = c.req.query('course_id') || '';
    const limit = Math.min(parseInt(c.req.query('limit') || '200', 10) || 200, 200);

    const files = (await listUserFiles(c.env, user.uid, 200))
      .filter((f) => f.status === 'uploaded')            // bỏ pending_upload/archived
      .map(normalizeFileDoc)
      .filter((f) => f.review_status !== 'rejected')
      .filter((f) => (courseId ? f.course_id === courseId : true))
      .slice(0, limit);

    const sources = files.map((f) => ({
      file_id: f._id || f.id || '',
      filename: f.filename || '',
      subject: f.subject || '',
      document_type: f.document_type,
      source_id: f.notebooklm_source_id || '',
      review_status: f.review_status,
      size_bytes: f.size_bytes || '0',
      updated_at: f.updated_at || '',
    }));

    return withCors(c.json({ sources, total: sources.length }), origin);
  } catch (err) {
    console.error('List chat sources error:', err);
    return withCors(c.json({ error: 'Không thể lấy danh sách nguồn', detail: err.message }, 500), origin);
  }
}));

export default router;
