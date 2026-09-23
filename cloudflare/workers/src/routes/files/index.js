// src/routes/files/index.js — Mount tất cả file sub-routes (<45 lines)

import { Hono } from 'hono';
import uploadInitRouter from './upload_init.js';
import uploadCompleteRouter from './upload_complete.js';
import registerRouter from './register.js';
import checkHashRouter from './check_hash.js';
import listRouter from './list.js';
import reviewRouter from './review.js';
import deleteRouter from './delete.js';

const router = new Hono();

// Phase 1/3: Khởi tạo upload session → hoàn tất upload (web user)
router.route('/upload', uploadInitRouter);
router.route('/upload', uploadCompleteRouter);

// Phase 2 — Dual Inflow (Python local agent)
router.route('/', registerRouter);   // POST /api/files/register
router.route('/', checkHashRouter);  // POST /api/files/check-hash

// Phase 4 — Hàng đợi duyệt nguồn (đăng ký trước /:fileId để không bị nuốt bởi param)
router.route('/', reviewRouter);     // GET /api/files/review + POST /api/files/:id/review

// GET /api/files — Danh sách files (+ filter review_status / is_output / source_kind)
router.route('/', listRouter);

// DELETE /api/files/:id — Safe Cascade Delete 4 bước
router.route('/', deleteRouter);

export default router;
