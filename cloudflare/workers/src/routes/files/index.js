// src/routes/files/index.js — Mount tất cả file sub-routes (<40 lines)

import { Hono } from 'hono';
import uploadInitRouter from './upload_init.js';
import uploadCompleteRouter from './upload_complete.js';
import listRouter from './list.js';
import deleteRouter from './delete.js';

const router = new Hono();

// Phase 1: Khởi tạo upload session → trả về Drive URL
router.route('/upload', uploadInitRouter);

// Phase 3: Hoàn tất upload, lưu metadata Firestore
router.route('/upload', uploadCompleteRouter);

// GET /api/files — Danh sách files
router.route('/', listRouter);

// DELETE /api/files/:id — Safe Cascade Delete 4 bước
router.route('/', deleteRouter);

export default router;
