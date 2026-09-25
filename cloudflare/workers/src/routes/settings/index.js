// src/routes/settings/index.js — Global & Per-User Settings API (<150 lines)
// Quản lý cấu hình tập trung (system_config) trên Firestore

import { Hono } from 'hono';
import { requireAuth, requireAuthOrAgent, resolveTargetUid, getFallbackUid } from '../../lib/auth.js';
import { firestoreGet, firestoreSet, fromFirestoreDoc } from '../../lib/firebase.js';
import { createDriveFolder, setDriveWriterPermission, setDriveAnyonePermission, findDriveFolderByName } from '../../lib/drive.js';
import { withCors } from '../../lib/cors.js';
import taskFlagsRouter from './task_flags.js';

const router = new Hono();

// Công tắc tính năng hàng đợi (G1: truy vấn pending phía server, G2: hồi phục task kẹt)
router.route('/task-flags', taskFlagsRouter);

export const DEFAULT_DRIVE_ROOT = '1xAZK2zEeqgm2zN5_37ZafJPqYFhtuXtg'; // ThacSi_HTTT master root folder fallback
export const DEFAULT_LOCAL_PATH = 'D:\\ThacSi_HTTT\\Mon_Hoc';

export const getDefaultDriveRoot = (env) => env?.DEFAULT_DRIVE_ROOT || DEFAULT_DRIVE_ROOT;
export const getDefaultLocalPath = (env) => env?.DEFAULT_LOCAL_PATH || DEFAULT_LOCAL_PATH;

/**
 * Trích xuất ID thư mục Drive từ URL hoặc ID thô
 */
export function extractDriveFolderId(input) {
  if (!input) return '';
  let str = String(input).trim();
  str = str.replace(/[:?\/]+$/, '');
  const match = str.match(/\/folders\/([a-zA-Z0-9_-]+)/);
  if (match) return match[1];
  const matchD = str.match(/\/d\/([a-zA-Z0-9_-]+)/);
  if (matchD) return matchD[1];
  const matchQuery = str.match(/[?&]id=([a-zA-Z0-9_-]+)/);
  if (matchQuery) return matchQuery[1];
  return str;
}

export const getBaseDefaultConfig = (env) => {
  const driveRoot = getDefaultDriveRoot(env);
  const localPath = getDefaultLocalPath(env);
  return {
    local_base_path: localPath,
    root_folder: localPath,
    google_drive_root_folder_id: driveRoot,
    drive_root_folder: driveRoot,
    google_drive_root_name: 'ThacSi_HTTT',
    file_watcher_enabled: true,
    auto_sync_nlm: true,
    poll_interval_seconds: 10,
    supported_extensions: ['.pdf', '.docx', '.pptx', '.txt', '.md', '.mp3'],
  };
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

  const baseDefault = getBaseDefaultConfig(c.env);

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
        config: { ...baseDefault, initialized: false },
        uid: targetUid,
      }), origin);
    }

    const data = fromFirestoreDoc(doc);
    const resolvedLocal = data.local_base_path || data.root_folder || baseDefault.local_base_path;
    const resolvedDrive = extractDriveFolderId(data.google_drive_root_folder_id || data.drive_root_folder || baseDefault.google_drive_root_folder_id);

    return withCors(c.json({
      config: {
        ...baseDefault,
        ...data,
        local_base_path: resolvedLocal,
        root_folder: resolvedLocal,
        google_drive_root_folder_id: resolvedDrive,
        drive_root_folder: resolvedDrive,
        initialized: true,
      },
      uid: targetUid,
    }), origin);
  } catch (err) {
    console.error('Get system_config error:', err);
    // Graceful fallback to default config
    return withCors(c.json({
      config: { ...baseDefault, initialized: false, error: err.message },
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

  const baseDefault = getBaseDefaultConfig(c.env);

  try {
    const body = await c.req.json();
    let existingDoc = await firestoreGet(c.env, `users/${targetUid}/settings/config`);
    if (!existingDoc) {
      existingDoc = await firestoreGet(c.env, `users/${targetUid}/system_config/current`);
    }
    const currentData = existingDoc ? fromFirestoreDoc(existingDoc) : baseDefault;

    const targetLocal = body.local_base_path !== undefined ? String(body.local_base_path).trim()
      : (body.root_folder !== undefined ? String(body.root_folder).trim() : undefined);

    let targetDrive = body.google_drive_root_folder_id !== undefined ? String(body.google_drive_root_folder_id).trim()
      : (body.drive_root_folder !== undefined ? String(body.drive_root_folder).trim() : undefined);

    if (targetDrive !== undefined) {
      targetDrive = extractDriveFolderId(targetDrive);
      // Khi user lưu folder ID tùy chỉnh, tự động cấp quyền cho userEmail và anyone để link không bao giờ bị 'Từ chối truy cập'
      if (targetDrive) {
        const userEmail = c.get('user')?.email;
        if (userEmail) {
          await setDriveWriterPermission(c.env, targetDrive, userEmail).catch((e) => console.warn('Lỗi cấp quyền user:', e.message));
        }
        await setDriveAnyonePermission(c.env, targetDrive, 'writer').catch((e) => console.warn('Lỗi cấp quyền anyone:', e.message));
      }
    }

    const updatedData = {
      ...currentData,
      ...(targetLocal !== undefined && { local_base_path: targetLocal, root_folder: targetLocal }),
      ...(targetDrive !== undefined && { google_drive_root_folder_id: targetDrive, drive_root_folder: targetDrive }),
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
 * Xử lý cấp phát thư mục Drive riêng (Idempotency - tính lũy đẳng tuyệt đối)
 * Quy tắc: 1 email thì 1 thư mục ThacSi_HTTT duy nhất, tự động phân quyền user & anyone
 */
async function handleProvisionDrive(c) {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const userEmail = user.email || '';
    const folderName = 'ThacSi_HTTT';
    const masterRoot = getDefaultDriveRoot(c.env);
    const defaultLocal = getDefaultLocalPath(c.env);

    let targetFolderName = folderName;

    // 1. KIỂM TRA TÍNH LŨY ĐẲNG TRONG DATABASE CỦA USER TRƯỚC
    let existingDoc = await firestoreGet(c.env, `users/${user.uid}/settings/config`);
    if (!existingDoc) {
      existingDoc = await firestoreGet(c.env, `users/${user.uid}/system_config/current`);
    }
    const currentConfig = existingDoc ? fromFirestoreDoc(existingDoc) : null;
    let targetFolderId = extractDriveFolderId(currentConfig?.google_drive_root_folder_id || currentConfig?.drive_root_folder || '');
    if (currentConfig?.google_drive_root_name) {
      targetFolderName = currentConfig.google_drive_root_name;
    }

    // 2. NẾU DATABASE CHƯA CÓ HOẶC CẦN TÌM: TÌM THƯ MỤC TRÊN GOOGLE DRIVE
    if (!targetFolderId) {
      let existingFolder = null;
      try {
        existingFolder = await findDriveFolderByName(c.env, folderName, masterRoot);
        if (!existingFolder) {
          existingFolder = await findDriveFolderByName(c.env, folderName);
        }
        if (!existingFolder && user.name) {
          existingFolder = await findDriveFolderByName(c.env, `ThacSi_HTTT - ${user.name}`, masterRoot)
            || await findDriveFolderByName(c.env, `ThacSi_HTTT - ${user.name}`);
        }
      } catch (checkErr) {
        console.warn('Lỗi khi kiểm tra thư mục Drive:', checkErr.message);
      }

      if (existingFolder && existingFolder.id) {
        targetFolderId = existingFolder.id;
        targetFolderName = existingFolder.name || folderName;
        console.log(`[Drive Idempotency] Tìm thấy thư mục '${targetFolderName}' -> Tái sử dụng ID: ${targetFolderId}`);
      }
    }

    // 3. NẾU CHƯA TỒN TẠI CẢ TRÊN DRIVE: TẠO MỚI THƯ MỤC 'ThacSi_HTTT'
    let isNew = false;
    if (!targetFolderId) {
      const folderRes = await createDriveFolder(c.env, folderName, masterRoot);
      targetFolderId = folderRes.id;
      targetFolderName = folderName;
      isNew = true;
      console.log(`[Drive Provision] Đã tạo mới thư mục '${folderName}' -> ID: ${targetFolderId}`);
    }

    // 4. PHÂN QUYỀN TOÀN DIỆN CHO EMAIL ĐANG ĐĂNG NHẬP (DYNAMIC 100%)
    // 4.1 Cấp quyền writer cho email đang đăng nhập
    if (userEmail) {
      try {
        await setDriveWriterPermission(c.env, targetFolderId, userEmail);
      } catch (shareErr) {
        console.warn(`Lỗi phân quyền Drive cho ${userEmail}:`, shareErr.message);
      }
    }
    // 4.2 Cấp quyền writer cho tài khoản Root Admin nếu cấu hình trong env
    const adminEmail = c.env?.ROOT_ADMIN_EMAIL;
    if (adminEmail && userEmail !== adminEmail) {
      try {
        await setDriveWriterPermission(c.env, targetFolderId, adminEmail);
      } catch (adminPermErr) {
        console.warn(`Lỗi phân quyền admin ${adminEmail}:`, adminPermErr.message);
      }
    }
    // 4.3 Cấp quyền writer cho 'anyone' có liên kết (đảm bảo mở ở bất kỳ profile Chrome nào cũng truy cập được)
    try {
      await setDriveAnyonePermission(c.env, targetFolderId, 'writer');
    } catch (anyoneErr) {
      console.warn('Lỗi phân quyền anyone with link:', anyoneErr.message);
    }

    // 5. LƯU CẤU HÌNH VÀO FIRESTORE users/${user.uid}/settings/config
    const now = new Date().toISOString();
    const updatedConfig = {
      ...currentConfig,
      google_drive_root_folder_id: targetFolderId,
      drive_root_folder: targetFolderId,
      google_drive_root_name: targetFolderName,
      local_base_path: currentConfig?.local_base_path || defaultLocal,
      root_folder: currentConfig?.root_folder || defaultLocal,
      user_email: userEmail,
      updated_at: now,
      updated_by: userEmail || 'user',
    };

    await firestoreSet(c.env, `users/${user.uid}/settings/config`, updatedConfig);

    return withCors(c.json({
      status: isNew ? 'provisioned' : 'reused',
      folder_id: targetFolderId,
      folder_name: targetFolderName,
      user_email: userEmail,
      config: updatedConfig,
    }), origin);
  } catch (err) {
    console.error('Provision drive error:', err);
    return withCors(c.json({ error: 'Cấp phát thư mục Google Drive thất bại', detail: err.message }, 500), origin);
  }
}

/**
 * POST /api/settings/provision-drive & POST /api/settings/init-root
 */
router.post('/provision-drive', requireAuth(handleProvisionDrive));
router.post('/init-root', requireAuth(handleProvisionDrive));

export default router;
