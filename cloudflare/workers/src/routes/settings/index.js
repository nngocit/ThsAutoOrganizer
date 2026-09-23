// src/routes/settings/index.js — Global & Per-User Settings API (<150 lines)
// Quản lý cấu hình tập trung (system_config) trên Firestore

import { Hono } from 'hono';
import { requireAuth, requireAuthOrAgent, resolveTargetUid, getFallbackUid } from '../../lib/auth.js';
import { firestoreGet, firestoreSet, fromFirestoreDoc } from '../../lib/firebase.js';
import { createDriveFolder, setDriveWriterPermission } from '../../lib/drive.js';
import { withCors } from '../../lib/cors.js';

const router = new Hono();

const DEFAULT_DRIVE_ROOT = '1xAZK2zEeqgm2zN5_37ZafJPqYFhtuXtg'; // ThacSi_HTTT master root folder

const DEFAULT_CONFIG = {
  local_base_path: 'H:\\2026\\Thac Sy\\Mon_Hoc',
  google_drive_root_folder_id: DEFAULT_DRIVE_ROOT,
  google_drive_root_name: 'ThacSi_HTTT',
  file_watcher_enabled: true,
  auto_sync_nlm: true,
  poll_interval_seconds: 10,
  supported_extensions: ['.pdf', '.docx', '.pptx', '.txt', '.md', '.mp3'],
};

/**
 * GET /api/settings/config
 * Lấy cấu hình hệ thống / người dùng.
 * Hỗ trợ cả User Bearer token lẫn Agent X-Agent-Secret.
 */
router.get('/config', requireAuthOrAgent(async (c) => {
  const origin = c.req.header('Origin') || '';
  const targetUid = resolveTargetUid(c, null, c.req.query('uid')) || await getFallbackUid(c.env);

  if (!targetUid) {
    return withCors(c.json({ error: 'UID không xác định' }, 400), origin);
  }

  try {
    let doc = await firestoreGet(c.env, `users/${targetUid}/settings/config`);
    if (!doc) {
      doc = await firestoreGet(c.env, `users/${targetUid}/system_config/current`);
    }
    if (!doc) {
      doc = await firestoreGet(c.env, 'system_config/default');
    }

    if (!doc) {
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
    // Graceful fallback to default config
    return withCors(c.json({
      config: { ...DEFAULT_CONFIG, initialized: false, error: err.message },
      uid: targetUid,
    }), origin);
  }
}));

/**
 * PUT /api/settings/config
 * Cập nhật cấu hình hệ thống / người dùng.
 */
router.put('/config', requireAuthOrAgent(async (c) => {
  const origin = c.req.header('Origin') || '';
  const targetUid = resolveTargetUid(c, null, c.req.query('uid')) || await getFallbackUid(c.env);

  if (!targetUid) {
    return withCors(c.json({ error: 'UID không xác định' }, 400), origin);
  }

  try {
    const body = await c.req.json();
    let existingDoc = await firestoreGet(c.env, `users/${targetUid}/settings/config`);
    if (!existingDoc) {
      existingDoc = await firestoreGet(c.env, `users/${targetUid}/system_config/current`);
    }
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

    await firestoreSet(c.env, `users/${targetUid}/settings/config`, updatedData);

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

/**
 * POST /api/settings/provision-drive
 * Tự động tạo thư mục Drive riêng cho user và chia sẻ quyền writer cho email user.
 */
router.post('/provision-drive', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const userEmail = user.email || '';
    const emailPrefix = userEmail ? userEmail.split('@')[0] : (user.name || user.uid.slice(0, 8));
    const folderName = `ThacSi_HTTT - ${user.name || emailPrefix}`;

    // 1. Tạo thư mục Drive riêng bên trong Master Root
    const folderRes = await createDriveFolder(c.env, folderName, DEFAULT_DRIVE_ROOT);
    const folderId = folderRes.id;

    // 2. Chia sẻ quyền writer (Editor) cho user.email
    if (userEmail) {
      try {
        await setDriveWriterPermission(c.env, folderId, userEmail);
      } catch (shareErr) {
        console.warn(`Lỗi phân quyền Drive cho ${userEmail}:`, shareErr.message);
      }
    }

    // 3. Lưu cấu hình vào Firestore users/${user.uid}/settings/config
    const now = new Date().toISOString();
    const newConfig = {
      google_drive_root_folder_id: folderId,
      google_drive_root_name: folderName,
      user_email: userEmail,
      updated_at: now,
      updated_by: userEmail,
    };

    await firestoreSet(c.env, `users/${user.uid}/settings/config`, newConfig);

    return withCors(c.json({
      status: 'provisioned',
      folder_id: folderId,
      folder_name: folderName,
      user_email: userEmail,
      config: newConfig,
    }), origin);
  } catch (err) {
    console.error('Provision drive error:', err);
    return withCors(c.json({ error: 'Cấp phát thư mục Google Drive thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
