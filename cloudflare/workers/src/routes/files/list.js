// src/routes/files/list.js — GET /api/files (<120 lines)
// List files của user hiện tại, hỗ trợ filter subject và status

import { Hono } from 'hono';
import { requireAuth } from '../../lib/auth.js';
import { firestoreList, fromFirestoreDoc } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';

const router = new Hono();

/**
 * GET /api/files
 * Query params: subject, status, limit (default 50)
 * Trả về: { files: [...], total: N }
 *
 * NOTE: Firestore REST không hỗ trợ compound WHERE tốt trên edge runtime.
 * Chiến lược: Lấy toàn bộ (max pageSize=200), lọc phía Worker.
 * Với dữ liệu ~1 user/1 môn học vài trăm file là ổn.
 * Nếu cần scale: dùng Firestore structured query API (runQuery endpoint).
 */
router.get('/', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const subject = c.req.query('subject') || '';
    const status = c.req.query('status') || '';
    const docType = c.req.query('document_type') || '';
    const courseId = c.req.query('course_id') || '';
    const limit = Math.min(parseInt(c.req.query('limit') || '50', 10), 200);

    // Lấy toàn bộ files của user
    const resp = await firestoreList(c.env, `users/${user.uid}/files`, 200);
    let files = (resp.documents || []).map(fromFirestoreDoc);

    // Lọc phía Worker
    files = files.filter((f) => {
      if (f.status === 'archived') return false;              // Ẩn soft-deleted
      if (f.status === 'pending_upload') return false;        // Ẩn incomplete uploads
      if (subject && f.subject !== subject) return false;
      if (status && f.status !== status) return false;
      if (docType && f.document_type !== docType) return false;
      if (courseId && f.course_id !== courseId) return false;
      return true;
    });

    // Sắp xếp: mới nhất trước
    files.sort((a, b) => {
      const ta = a.created_at || '';
      const tb = b.created_at || '';
      return tb.localeCompare(ta);
    });

    // Giới hạn kết quả
    const paginated = files.slice(0, limit);

    // Thêm flag isNew (<24h) cho UI
    const now = Date.now();
    const result = paginated.map((f) => ({
      ...f,
      is_new: f.created_at
        ? now - new Date(f.created_at).getTime() < 24 * 60 * 60 * 1000
        : false,
    }));

    return withCors(c.json({ files: result, total: result.length, all_count: files.length }), origin);
  } catch (err) {
    console.error('List files error:', err);
    return withCors(c.json({ error: 'Không thể lấy danh sách files', detail: err.message }, 500), origin);
  }
}));

export default router;
