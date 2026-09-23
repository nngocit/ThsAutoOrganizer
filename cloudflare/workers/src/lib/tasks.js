// src/lib/tasks.js — Helper đẩy task vào Firestore queue (§2) (<120 lines)
// Queue: nlm_task_queue (NotebookLM) | drive_task_queue (Drive + local PC)

import { firestoreSet } from './firebase.js';
import { isOutputFolder } from './folders.js';

export const NLM_QUEUE = 'nlm_task_queue';
export const DRIVE_QUEUE = 'drive_task_queue';

export const NLM_ACTIONS = [
  'source_add', 'source_remove', 'chat_query', 'research_start',
  'artifact_download', 'exam_generate',
];
export const DRIVE_ACTIONS = ['move_to_archive', 'soft_delete_local', 'hard_delete'];

/** Ghi 1 task vào queue; trả về task id (= job_id phía client) */
export async function enqueueTask(env, queue, payload) {
  const taskId = crypto.randomUUID();
  await firestoreSet(env, `${queue}/${taskId}`, {
    id: taskId,
    status: 'pending',
    created_at: new Date().toISOString(),
    ...payload,
  });
  return taskId;
}

/**
 * Lớp 2 NO-LOOP: TUYỆT ĐỐI không queue source_add cho file trong 04_Ket_Qua_Xuat_Ban.
 * @returns {Promise<string|null>} task_id hoặc null nếu bị chặn/thiếu dữ liệu
 */
export async function enqueueSourceAdd(env, { uid, fileId, courseId, notebookId, filename, subject, folderPath, isOutput, localPath, driveFileId }) {
  if (isOutput === true || isOutputFolder(folderPath)) {
    console.log(`[NoLoop] Bỏ qua source_add cho file output: ${filename || fileId}`);
    return null;
  }
  if (!uid || !fileId) return null;
  return enqueueTask(env, NLM_QUEUE, {
    action: 'source_add',
    uid,
    file_id: fileId,
    course_id: courseId || '',
    notebook_id: notebookId || '',
    filename: filename || '',
    subject: subject || '',
    // Agent cần các field này để resolve file vật lý (local trước, Drive fallback)
    folder_path: folderPath || '',
    local_path: localPath || '',
    drive_file_id: driveFileId || '',
  });
}

/** Queue gỡ source khỏi NotebookLM — bỏ qua nếu chưa từng sync */
export async function enqueueSourceRemove(env, { uid, fileId, sourceId, notebookId }) {
  if (!uid || !sourceId) return null;
  return enqueueTask(env, NLM_QUEUE, {
    action: 'source_remove',
    uid,
    file_id: fileId || '',
    source_id: sourceId,
    notebook_id: notebookId || '',
  });
}

/** Bước 2 cascade: dời file Drive sang _Archive_Trash_90Days */
export async function enqueueDriveArchive(env, { uid, fileId, driveFileId, targetFolder }) {
  if (!uid || !driveFileId) return null;
  return enqueueTask(env, DRIVE_QUEUE, {
    action: 'move_to_archive',
    uid,
    file_id: fileId || '',
    drive_file_id: driveFileId,
    target_folder: targetFolder || '_Archive_Trash_90Days',
  });
}

/** Bước 3 cascade: soft delete file trên PC (Recycle Bin) — cần local_path */
export async function enqueueSoftDeleteLocal(env, { uid, fileId, localPath }) {
  if (!uid || !fileId || !localPath) return null;
  return enqueueTask(env, DRIVE_QUEUE, {
    action: 'soft_delete_local',
    uid,
    file_id: fileId,
    local_path: localPath,
  });
}

/** Bước 4 cascade (cron 90 ngày): xoá vĩnh viễn cả Drive + local PC */
export async function enqueueHardDelete(env, { uid, fileId, driveFileId, filename, localPath }) {
  if (!uid) return null;
  return enqueueTask(env, DRIVE_QUEUE, {
    action: 'hard_delete',
    uid,
    file_id: fileId || '',
    drive_file_id: driveFileId || '',
    filename: filename || '',
    local_path: localPath || '',
  });
}
