// src/lib/tasks.js — Helper đẩy task vào Firestore queue (§2) (<120 lines)
// Queue: nlm_task_queue (NotebookLM) | drive_task_queue (Drive + local PC)

import { firestoreSet } from './firebase.js';
import { isOutputFolder } from './folders.js';
import { resolveNotebookId } from './notebooks.js';

export const NLM_QUEUE = 'nlm_task_queue';
export const DRIVE_QUEUE = 'drive_task_queue';

export const NLM_ACTIONS = [
  'source_add', 'source_remove', 'chat_query', 'research_start',
  'artifact_download', 'exam_generate',
];
export const DRIVE_ACTIONS = ['move_to_archive', 'soft_delete_local', 'hard_delete'];

/**
 * Báo GitHub Actions chạy ngay workflow "NLM Drain" khi có task NLM mới
 * (repository_dispatch event_type=nlm-drain) → nạp không cần chờ cron 15 phút.
 *
 * - Thiếu Worker secret GITHUB_DISPATCH_TOKEN → bỏ qua im lặng (cron vẫn chạy).
 * - LỖI MẠNG KHÔNG ĐƯỢC làm hỏng request chính: chỉ log warning.
 * - Await (không dùng fire-and-forget) để Worker không cắt promise khi response trả về.
 */
async function dispatchNlmDrain(env, queue, action) {
  const token = env.GITHUB_DISPATCH_TOKEN;
  if (!token || queue !== NLM_QUEUE) return;
  const repo = env.GITHUB_DISPATCH_REPO || 'nngocit/ThsAutoOrganizer';
  try {
    const res = await fetch(`https://api.github.com/repos/${repo}/dispatches`, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${token}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'Content-Type': 'application/json',
        'User-Agent': 'ths-organizer',
      },
      body: JSON.stringify({ event_type: 'nlm-drain', client_payload: { queue, action: action || '' } }),
      signal: typeof AbortSignal !== 'undefined' && AbortSignal.timeout
        ? AbortSignal.timeout(5000)
        : undefined,
    });
    if (res.ok) console.log(`[Dispatch] Đã báo GitHub Actions chạy NLM Drain (${action})`);
    else console.warn(`[Dispatch] GitHub từ chối (${res.status}) cho action=${action}`);
  } catch (err) {
    console.warn(`[Dispatch] Không gửi được (bỏ qua): ${err.message}`);
  }
}

/** Ghi 1 task vào queue; trả về task id (= job_id phía client) */
export async function enqueueTask(env, queue, payload) {
  const taskId = crypto.randomUUID();
  await firestoreSet(env, `${queue}/${taskId}`, {
    id: taskId,
    status: 'pending',
    created_at: new Date().toISOString(),
    ...payload,
  });
  await dispatchNlmDrain(env, queue, payload.action);
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

  let resolvedNbId = notebookId || '';
  if (!resolvedNbId) {
    resolvedNbId = await resolveNotebookId(env, uid, { courseId, subject });
  }

  return enqueueTask(env, NLM_QUEUE, {
    action: 'source_add',
    uid,
    file_id: fileId,
    course_id: courseId || '',
    notebook_id: resolvedNbId || '',
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
