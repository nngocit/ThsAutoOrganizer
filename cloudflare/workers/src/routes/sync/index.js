// src/routes/sync/index.js — Luồng 3: Discovery/Reconciliation & Task Queue API (<180 lines)

import { Hono } from 'hono';
import { requireAgentAuth, requireAuthOrAgent, resolveTargetUid, getFallbackUid } from '../../lib/auth.js';
import { firestoreList, firestoreGet, firestoreSet, fromFirestoreDoc } from '../../lib/firebase.js';
import { listDriveSubfolders } from '../../lib/drive.js';
import { withCors } from '../../lib/cors.js';

const router = new Hono();
const VALID_QUEUES = new Set(['nlm_task_queue', 'drive_task_queue']);
const DEFAULT_DRIVE_ROOT = '12YHJZzM04Uq0rSKcg-pQGwdFMqKrXE3X'; // ThacSi_HTTT root folder

/**
 * GET /api/sync/reconcile
 * Luồng 3: Quét đồng bộ thông minh
 * So sánh thực tế trên Google Drive với danh sách môn học trên Firestore
 */
router.get('/reconcile', requireAuthOrAgent(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';
  const targetUid = resolveTargetUid(c, user, c.req.query('uid')) || await getFallbackUid(c.env);

  if (!targetUid) {
    return withCors(c.json({ error: 'UID không xác định' }, 400), origin);
  }

  try {
    // 1. Xác định Root Folder ID trên Drive
    let rootFolderId = DEFAULT_DRIVE_ROOT;
    try {
      const configDoc = await firestoreGet(c.env, `users/${targetUid}/settings/config`);
      if (configDoc) {
        const cfg = fromFirestoreDoc(configDoc);
        if (cfg.google_drive_root_folder_id) rootFolderId = cfg.google_drive_root_folder_id;
      }
    } catch (e) {
      console.warn('Lỗi đọc settings config, dùng root fallback:', e);
    }

    // 2. Lấy danh sách thư mục con thực tế trên Google Drive
    let driveFolders = [];
    try {
      driveFolders = await listDriveSubfolders(c.env, rootFolderId);
    } catch (driveErr) {
      console.warn('Không thể liệt kê Google Drive (Service Account):', driveErr.message);
    }

    // 3. Lấy danh sách Môn học trên Firestore
    const coursesResp = await firestoreList(c.env, `users/${targetUid}/courses`, 100);
    const courses = (coursesResp.documents || []).map(fromFirestoreDoc);

    // 4. So khớp dữ liệu
    const linkedDriveFolderIds = new Set(courses.map((c) => c.drive_folder_id).filter(Boolean));
    const linkedDriveFolderNames = new Set(courses.map((c) => (c.display_name || c.name || '').toLowerCase().trim()));

    // Thư mục trên Drive chưa được ghi nhận trên Web/Firestore -> Gợi ý Import
    const unimportedFolders = driveFolders.filter((df) => {
      const nameMatch = linkedDriveFolderNames.has((df.name || '').toLowerCase().trim());
      const idMatch = linkedDriveFolderIds.has(df.id);
      return !nameMatch && !idMatch;
    });

    // Môn học trên Firestore chưa có sổ NotebookLM -> Gợi ý liên kết
    const unlinkedCourses = courses.filter((c) => !c.notebooklm_id && !c.notebook_id);

    return withCors(c.json({
      reconcile: {
        drive_root_folder_id: rootFolderId,
        drive_total_folders: driveFolders.length,
        courses_total: courses.length,
        unimported_drive_folders: unimportedFolders,
        unlinked_courses: unlinkedCourses,
        status: (unimportedFolders.length === 0 && unlinkedCourses.length === 0) ? 'healthy' : 'needs_sync',
      },
    }), origin);
  } catch (err) {
    console.error('Reconcile error:', err);
    return withCors(c.json({ error: 'Quét đồng bộ thất bại', detail: err.message }, 500), origin);
  }
}));

/**
 * POST /api/sync/import-drive-folder
 * Import một thư mục phát hiện trên Drive thành Môn học chính thức
 */
router.post('/import-drive-folder', requireAuthOrAgent(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';
  const targetUid = resolveTargetUid(c, user, c.req.query('uid')) || await getFallbackUid(c.env);

  try {
    const { folder_id, folder_name, local_folder_name } = await c.req.json();
    if (!folder_id || !folder_name) {
      return withCors(c.json({ error: 'folder_id và folder_name là bắt buộc' }, 400), origin);
    }

    const docId = crypto.randomUUID();
    const now = new Date().toISOString();
    const localFolder = local_folder_name || folder_name
      .normalize('NFD').replace(/[\u0300-\u036f]/g, '')
      .replace(/[^a-zA-Z0-9_-]/g, '_')
      .replace(/_+/g, '_');

    // 1. Tạo Course record trên Firestore
    await firestoreSet(c.env, `users/${targetUid}/courses/${docId}`, {
      id: docId,
      display_name: folder_name,
      name: folder_name,
      local_folder_name: localFolder,
      drive_folder_id: folder_id,
      notebooklm_id: '',
      status: 'pending',
      created_at: now,
      updated_at: now,
    });

    // 2. Tạo task cho Local Agent tạo Notebook và thư mục Local
    const taskId = crypto.randomUUID();
    await firestoreSet(c.env, `nlm_task_queue/${taskId}`, {
      id: taskId,
      action: 'course_create',
      course_id: docId,
      display_name: folder_name,
      local_folder_name: localFolder,
      drive_folder_id: folder_id,
      uid: targetUid,
      status: 'pending',
      created_at: now,
    });

    return withCors(c.json({
      status: 'imported',
      course_id: docId,
      task_id: taskId,
    }, 201), origin);
  } catch (err) {
    console.error('Import drive folder error:', err);
    return withCors(c.json({ error: 'Import thư mục Drive thất bại', detail: err.message }, 500), origin);
  }
}));

/**
 * GET /api/tasks/:queue
 * Python local agent gọi endpoint này để lấy các task pending.
 */
router.get('/:queue', requireAgentAuth(async (c) => {
  const queueName = c.req.param('queue');
  const origin = c.req.header('Origin') || '';

  if (!VALID_QUEUES.has(queueName)) {
    return withCors(c.json({ error: `Queue không hợp lệ: ${queueName}` }, 400), origin);
  }

  try {
    const limit = parseInt(c.req.query('limit') || '10', 10);
    const resp = await firestoreList(c.env, queueName, Math.min(limit, 50));
    const allDocs = (resp.documents || []).map(fromFirestoreDoc);

    const pendingTasks = allDocs
      .filter((t) => t.status === 'pending')
      .slice(0, limit);

    return withCors(c.json({ tasks: pendingTasks, queue: queueName }), origin);
  } catch (err) {
    console.error(`Get tasks ${queueName} error:`, err);
    return withCors(c.json({ error: 'Không thể lấy tasks', detail: err.message }, 500), origin);
  }
}));

/**
 * PATCH /api/tasks/:queue/:taskId
 * Python agent báo cáo kết quả xử lý task.
 */
router.patch('/:queue/:taskId', requireAgentAuth(async (c) => {
  const queueName = c.req.param('queue');
  const taskId = c.req.param('taskId');
  const origin = c.req.header('Origin') || '';

  if (!VALID_QUEUES.has(queueName)) {
    return withCors(c.json({ error: `Queue không hợp lệ: ${queueName}` }, 400), origin);
  }

  try {
    const body = await c.req.json();
    const { status, error: errorMsg, result } = body;

    const validStatuses = new Set(['done', 'failed', 'processing', 'skipped_ext', 'skipped_no_course']);
    if (!validStatuses.has(status)) {
      return withCors(c.json({ error: `status không hợp lệ: ${status}` }, 400), origin);
    }

    const existingDoc = await firestoreGet(c.env, `${queueName}/${taskId}`);
    if (!existingDoc) {
      return withCors(c.json({ error: 'Task không tìm thấy' }, 404), origin);
    }

    const now = new Date().toISOString();
    const updateData = { status, processed_at: now };
    if (errorMsg) updateData.error = errorMsg;
    if (result) updateData.result = typeof result === 'string' ? result : JSON.stringify(result);

    await firestoreSet(c.env, `${queueName}/${taskId}`, updateData);

    const taskData = fromFirestoreDoc(existingDoc);

    // Cập nhật trạng thái file nếu là source_add
    if (queueName === 'nlm_task_queue' && taskData.action === 'source_add' && (status === 'done' || status === 'skipped_ext' || status === 'skipped_no_course')) {
      if (taskData.uid && taskData.file_id) {
        const resultStr = typeof result === 'string' ? result : (result ? JSON.stringify(result) : '');
        const skipped = status === 'skipped_ext' || status === 'skipped_no_course' || resultStr.startsWith('skipped');
        const finalStatus = (status === 'skipped_ext' || status === 'skipped_no_course') ? status : (skipped ? 'skipped' : 'synced');
        await firestoreSet(c.env, `users/${taskData.uid}/files/${taskData.file_id}`, {
          notebooklm_sync_status: finalStatus,
          notebooklm_source_id: skipped ? '' : resultStr,
          updated_at: now,
        });
      }
    }

    // Cập nhật trạng thái course nếu là course_create
    if (queueName === 'nlm_task_queue' && taskData.action === 'course_create' && status === 'done') {
      if (taskData.uid && taskData.course_id && result) {
        await firestoreSet(c.env, `users/${taskData.uid}/courses/${taskData.course_id}`, {
          notebooklm_id: result,
          status: 'active',
          updated_at: now,
        });
      }
    }

    return withCors(c.json({ status: 'updated', task_id: taskId }), origin);
  } catch (err) {
    console.error(`Update task ${taskId} error:`, err);
    return withCors(c.json({ error: 'Cập nhật task thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
