// src/routes/files/index.js — Mount tất cả file sub-routes (<35 lines)

import { Hono } from 'hono';
import uploadRouter from './upload.js';
import registerRouter from './register.js';
import checkHashRouter from './check_hash.js';
import listRouter from './list.js';
import reviewRouter from './review.js';
import deleteRouter from './delete.js';
import retryRouter from './retry.js';

const router = new Hono();

// Luồng 2: Web-to-Cloud-to-Local Upload
router.route('/upload', uploadRouter);

// Local Agent Direct Inflow (file đã có sẵn hoặc tải cục bộ)
router.route('/register', registerRouter);      // POST /api/files/register
router.route('/check-hash', checkHashRouter);   // POST /api/files/check-hash

// Thử lại tác vụ đồng bộ cho file
router.route('/', retryRouter);                 // POST /api/files/:id/retry

// Hàng đợi duyệt nguồn (Review Queue)
router.route('/', reviewRouter);                // GET /api/files/review + POST /api/files/:id/review

// Danh sách files
router.route('/', listRouter);                  // GET /api/files

// Xóa files
router.route('/', deleteRouter);                // DELETE /api/files/:id

export default router;
