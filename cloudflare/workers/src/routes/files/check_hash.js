// src/routes/files/check_hash.js — POST /api/files/check-hash (auth-or-agent) (<80 lines)
// Kiểm tra sha256 đã tồn tại chưa (bỏ qua doc pending_upload / archived).

import { Hono } from 'hono';
import { requireAuthOrAgent, resolveTargetUid } from '../../lib/auth.js';
import { withCors } from '../../lib/cors.js';
import { isValidSha256, normalizeSha256 } from '../../lib/file_ids.js';
import { findFileBySha256 } from '../../lib/file_lookup.js';

const router = new Hono();

// POST /api/files/check-hash — Body {sha256, uid?}
router.post('/', requireAuthOrAgent(async (c) => {
  const origin = c.req.header('Origin') || '';

  try {
    const body = await c.req.json();
    const sha = normalizeSha256(body.sha256);

    if (!isValidSha256(sha)) {
      return withCors(c.json({ error: 'sha256 không hợp lệ — phải là hex 64 ký tự' }, 400), origin);
    }

    const uid = resolveTargetUid(c, body.uid, c.req.query('uid'));
    if (!uid) {
      return withCors(c.json({
        error: 'Thiếu uid',
        detail: 'Agent gọi bằng X-Agent-Secret phải gửi uid (body.uid hoặc ?uid=)',
      }, 400), origin);
    }

    const file = await findFileBySha256(c.env, uid, sha);
    if (!file) {
      return withCors(c.json({ duplicate: false, sha256: sha }), origin);
    }

    return withCors(c.json({
      duplicate: true,
      file_id: file._id || file.id || '',
      drive_file_id: file.drive_file_id || '',
      filename: file.filename || '',
      sha256: sha,
    }), origin);
  } catch (err) {
    console.error('Check hash error:', err);
    return withCors(c.json({ error: 'Kiểm tra sha256 thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
