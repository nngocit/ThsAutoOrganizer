// src/routes/settings/index.js — Global Settings API (<120 lines)
// Quản lý cấu hình tập trung (system_config) trên Firestore

import { Hono } from 'hono';
import { requireAuthOrAgent, resolveTargetUid, getFallbackUid } from '../../lib/auth.js';
import { firestoreGet, firestoreSet, fromFirestoreDoc } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';

const router = new Hono();

const DEFAULT_CONFIG = {
  local_base_path: 'H:\\2026\\Thac Sy\\Mon_Hoc',
  google_drive_root_folder_id: '12YHJZzM04Uq0rSKcg-pQGwdFMqKrXE3X',
  google_drive_root_name: 'ThacSi_HTTT',
  file_watcher_enabled: true,
  auto_sync_nlm: true,
  poll_interval_seconds: 10,
  supported_extensions: ['.pdf', '.docx', '.pptx', '.txt', '.md', '.mp3'],
};

/**
 * GET /api/settings/config
 * Lấy cấu hình hệ thống toàn cục.
 * Hỗ trợ cả User Bearer token lẫn Agent X-Agent-Secret.
 */
router.get('/config', requireAuthOrAgent(async (c) => {
  const origin = c.req.header('Origin') || '';
  const targetUid = resolveTargetUid(c, null, c.req.query('uid')) || await getFallbackUid(c.env);

  if (!targetUid) {
    return withCors(c.json({ error: 'UID không xác định' }, 400), origin);
  }

  try {
    const doc = await firestoreGet(c.env, `users/${targetUid}/system_config/current`);
    if (!doc) {
      // Trả default config nếu chưa khởi tạo
      return withCors(c.json({
        config: { ...DEFAULT_CONFIG, initialized: false },
        uid: targetUid,
      }), origin);
    }

    const data = fromFirestoreDoc(doc);
    return withCors(c.json({
      config: { ...DEFAULT_CONFIG, ...data, initialized: true },
      uid: targetUid,
    }), origin);
  } catch (err) {
    console.error('Get system_config error:', err);
    return withCors(c.json({ error: 'Lỗi nạp cấu hình hệ thống', detail: err.message }, 500), origin);
  }
}));

/**
 * PUT /api/settings/config
 * Cập nhật cấu hình hệ thống toàn cục.
 */
router.put('/config', requireAuthOrAgent(async (c) => {
  const origin = c.req.header('Origin') || '';
  const targetUid = resolveTargetUid(c, null, c.req.query('uid')) || await getFallbackUid(c.env);

  if (!targetUid) {
    return withCors(c.json({ error: 'UID không xác định' }, 400), origin);
  }

  try {
    const body = await c.req.json();
    const existingDoc = await firestoreGet(c.env, `users/${targetUid}/system_config/current`);
    const currentData = existingDoc ? fromFirestoreDoc(existingDoc) : DEFAULT_CONFIG;

    const updatedData = {
      ...currentData,
      ...(body.local_base_path !== undefined && { local_base_path: String(body.local_base_path).trim() }),
      ...(body.google_drive_root_folder_id !== undefined && { google_drive_root_folder_id: String(body.google_drive_root_folder_id).trim() }),
      ...(body.google_drive_root_name !== undefined && { google_drive_root_name: String(body.google_drive_root_name).trim() }),
      ...(body.file_watcher_enabled !== undefined && { file_watcher_enabled: Boolean(body.file_watcher_enabled) }),
      ...(body.auto_sync_nlm !== undefined && { auto_sync_nlm: Boolean(body.auto_sync_nlm) }),
      ...(body.poll_interval_seconds !== undefined && { poll_interval_seconds: Number(body.poll_interval_seconds) }),
      updated_at: new Date().toISOString(),
      updated_by: c.get('user')?.email || 'agent',
    };

    await firestoreSet(c.env, `users/${targetUid}/system_config/current`, updatedData);

    return withCors(c.json({
      status: 'updated',
      config: updatedData,
      uid: targetUid,
    }), origin);
  } catch (err) {
    console.error('Update system_config error:', err);
    return withCors(c.json({ error: 'Cập nhật cấu hình thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
