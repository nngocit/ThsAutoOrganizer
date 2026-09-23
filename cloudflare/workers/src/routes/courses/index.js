// src/routes/courses/index.js — Luồng 1: Master Creation Flow & CRUD courses (<180 lines)

import { Hono } from 'hono';
import { requireAuth, requireAuthOrAgent, resolveTargetUid, getFallbackUid } from '../../lib/auth.js';
import { firestoreSet, firestoreList, firestoreGet, fromFirestoreDoc } from '../../lib/firebase.js';
import { createDriveFolder } from '../../lib/drive.js';
import { withCors } from '../../lib/cors.js';

const router = new Hono();
const DEFAULT_DRIVE_ROOT = '1xAZK2zEeqgm2zN5_37ZafJPqYFhtuXtg'; // ThacSi_HTTT root folder

/**
 * GET /api/courses
 * Trả về danh sách courses của user.
 */
router.get('/', requireAuthOrAgent(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';
  const targetUid = resolveTargetUid(c, user, c.req.query('uid')) || await getFallbackUid(c.env);

  if (!targetUid) {
    return withCors(c.json({ error: 'UID không xác định' }, 400), origin);
  }

  try {
    const resp = await firestoreList(c.env, `users/${targetUid}/courses`, 100);
    const courses = (resp.documents || []).map(fromFirestoreDoc);
    courses.sort((a, b) => (a.display_name || a.name || '').localeCompare(b.display_name || b.name || '', 'vi'));
    return withCors(c.json({ courses }), origin);
  } catch (err) {
    console.error('List courses error:', err);
    return withCors(c.json({ error: 'Không thể lấy danh sách môn học', detail: err.message }, 500), origin);
  }
}));

/**
 * GET /api/courses/:courseId
 * Tra cứu 1 course theo ID.
 */
router.get('/:courseId', requireAuthOrAgent(async (c) => {
  const courseId = c.req.param('courseId');
  const origin = c.req.header('Origin') || '';
  const targetUid = resolveTargetUid(c, null, c.req.query('uid')) || await getFallbackUid(c.env);

  if (!targetUid) {
    return withCors(c.json({ error: 'UID không xác định' }, 400), origin);
  }

  try {
    const doc = await firestoreGet(c.env, `users/${targetUid}/courses/${courseId}`);
    if (!doc) {
      return withCors(c.json({ error: 'Môn học không tìm thấy' }, 404), origin);
    }
    const data = fromFirestoreDoc(doc);
    return withCors(c.json({
      id: courseId,
      notebooklm_id: data.notebooklm_id || data.notebook_id || '',
      ...data,
    }), origin);
  } catch (err) {
    console.error(`Get course ${courseId} error:`, err);
    return withCors(c.json({ error: 'Lỗi tra cứu môn học', detail: err.message }, 500), origin);
  }
}));

/**
 * POST /api/courses
 * Luồng 1: Master Creation Flow
 * Body: { display_name, local_folder_name }
 * 1. Gọi Google Drive API tạo thư mục mới bên trong ThacSi_HTTT -> drive_folder_id
 * 2. Lưu vào Firestore với status='pending'
 * 3. Tạo task trong nlm_task_queue cho Local Agent tạo Notebook và thư mục Local
 */
router.post('/', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';
  try {
    const body = await c.req.json();
    const displayName = (body.display_name || body.name || '').trim();
    let localFolderName = (body.local_folder_name || '').trim();

    if (!displayName) {
      return withCors(c.json({ error: 'display_name là bắt buộc' }, 400), origin);
    }
    if (!localFolderName) {
      // Tự sinh local_folder_name nếu không truyền
      localFolderName = displayName
        .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
        .replace(/[^a-zA-Z0-9_-]/g, '_')
        .replace(/_+/g, '_');
    }

    // 1. Xác định Root Folder ID trên Google Drive
    let rootFolderId = DEFAULT_DRIVE_ROOT;
    try {
      let configDoc = await firestoreGet(c.env, `users/${user.uid}/settings/config`);
      if (!configDoc) {
        configDoc = await firestoreGet(c.env, 'system_config/default');
      }
      if (configDoc) {
        const cfg = fromFirestoreDoc(configDoc);
        if (cfg.google_drive_root_folder_id) rootFolderId = cfg.google_drive_root_folder_id;
      }
    } catch (e) {
      console.warn('Không thể đọc settings config, dùng root fallback:', e);
    }

    // 2. Tạo thư mục Drive bằng Service Account
    let driveFolderId = '';
    try {
      const folderRes = await createDriveFolder(c.env, displayName, rootFolderId);
      driveFolderId = folderRes.id;
    } catch (driveErr) {
      console.error('Lỗi tạo thư mục Google Drive:', driveErr);
      let detailMsg = driveErr.message;
      if (driveErr.message.includes('has not been used in project') || driveErr.message.includes('disabled')) {
        detailMsg = 'Google Drive API chưa được BẬT trên Google Cloud Console (Project 437903639644). Vui lòng nhấn nút BẬT (Enable) tại https://console.developers.google.com/apis/api/drive.googleapis.com/overview?project=437903639644 rồi thử lại.';
      } else if (driveErr.message.includes('File not found') || driveErr.message.includes('404')) {
        detailMsg = `Thư mục cha trên Google Drive (${rootFolderId}) không tìm thấy hoặc chưa chia sẻ quyền 'Người chỉnh sửa (Editor)' cho Service Account: firebase-adminsdk-fbsvc@thsautoorganizer.iam.gserviceaccount.com`;
      }
      return withCors(c.json({ 
        error: 'Không thể tạo thư mục môn học trên Google Drive', 
        detail: detailMsg,
        raw_error: driveErr.message 
      }, 502), origin);
    }

    const docId = crypto.randomUUID();
    const now = new Date().toISOString();

    // 3. Ghi Firestore với status 'pending'
    const courseData = {
      id: docId,
      display_name: displayName,
      name: displayName,
      local_folder_name: localFolderName,
      drive_folder_id: driveFolderId,
      notebooklm_id: body.notebooklm_id || '',
      status: 'pending',
      created_at: now,
      updated_at: now,
    };
    await firestoreSet(c.env, `users/${user.uid}/courses/${docId}`, courseData);

    // 4. Tạo task trong nlm_task_queue cho Local Agent
    const taskId = crypto.randomUUID();
    await firestoreSet(c.env, `nlm_task_queue/${taskId}`, {
      id: taskId,
      action: 'course_create',
      course_id: docId,
      display_name: displayName,
      local_folder_name: localFolderName,
      drive_folder_id: driveFolderId,
      uid: user.uid,
      status: 'pending',
      created_at: now,
    });

    return withCors(c.json({
      id: docId,
      display_name: displayName,
      local_folder_name: localFolderName,
      drive_folder_id: driveFolderId,
      status: 'pending',
      task_id: taskId,
    }, 201), origin);
  } catch (err) {
    console.error('Create course error:', err);
    return withCors(c.json({ error: 'Tạo môn học thất bại', detail: err.message }, 500), origin);
  }
}));

/**
 * PUT /api/courses/:courseId/notebooklm
 * Cập nhật notebooklm_id cho course (Local agent gọi hoặc admin liên kết thủ công)
 */
router.put('/:courseId/notebooklm', requireAuthOrAgent(async (c) => {
  const user = c.get('user');
  const courseId = c.req.param('courseId');
  const origin = c.req.header('Origin') || '';
  const targetUid = resolveTargetUid(c, user, c.req.query('uid')) || await getFallbackUid(c.env);

  try {
    const { notebooklm_id, status } = await c.req.json();
    if (!notebooklm_id) {
      return withCors(c.json({ error: 'notebooklm_id là bắt buộc' }, 400), origin);
    }

    const doc = await firestoreGet(c.env, `users/${targetUid}/courses/${courseId}`);
    if (!doc) {
      return withCors(c.json({ error: 'Môn học không tìm thấy' }, 404), origin);
    }

    const now = new Date().toISOString();
    const updateData = {
      notebooklm_id,
      updated_at: now,
    };
    if (status) updateData.status = status;

    await firestoreSet(c.env, `users/${targetUid}/courses/${courseId}`, updateData);

    return withCors(c.json({ status: 'updated', course_id: courseId, notebooklm_id }), origin);
  } catch (err) {
    console.error('Update notebooklm error:', err);
    return withCors(c.json({ error: 'Cập nhật thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
