// src/routes/files/register.js — POST /api/files/register (Local watcher đăng ký) (<180 lines)
// Auth: X-Agent-Secret. NO-LOOP: TUYỆT ĐỐI không queue source_add cho file trong 04_Ket_Qua_Xuat_Ban.

import { Hono } from 'hono';
import { requireAgentAuth } from '../../lib/auth.js';
import { firestoreSet } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';
import {
  ARCHIVE_FOLDER, DEFAULT_FOLDER, SOURCE_KINDS,
  folderForDocType, docTypeFromFolder, defaultReviewStatus,
  isOutputFolder, isNoLoopFolder, isSupportedFile, extensionOf,
} from '../../lib/folders.js';
import { isValidSha256, normalizeSha256, stableFileId } from '../../lib/file_ids.js';
import { findFileBySha256 } from '../../lib/file_lookup.js';
import { enqueueSourceAdd } from '../../lib/tasks.js';

const router = new Hono();

// POST /api/files/register
router.post('/', requireAgentAuth(async (c) => {
  const origin = c.req.header('Origin') || '';

  try {
    const body = await c.req.json();
    const {
      uid, filename, subject, document_type, folder_path,
      sha256, drive_file_id, size_bytes, local_path, course_id,
    } = body;

    if (!uid) {
      return withCors(c.json({ error: 'uid là bắt buộc' }, 400), origin);
    }
    if (!filename || !sha256) {
      return withCors(c.json({ error: 'filename và sha256 là bắt buộc' }, 400), origin);
    }

    const sha = normalizeSha256(sha256);
    if (!isValidSha256(sha)) {
      return withCors(c.json({ error: 'sha256 không hợp lệ — phải là hex 64 ký tự' }, 400), origin);
    }
    if (!isSupportedFile(filename)) {
      return withCors(
        c.json({ error: `Định dạng ${extensionOf(filename) || '(không rõ)'} không được hỗ trợ` }, 415),
        origin
      );
    }

    const folderPath = folder_path
      ? String(folder_path).trim()
      : folderForDocType(document_type || '');
    const docType = document_type || docTypeFromFolder(folderPath);

    // Lớp 1 NO-LOOP
    const isOutput = isOutputFolder(folderPath) || docType === 'ket_qua';

    // Vùng cấm inflow (Archive) → không đăng ký, không queue
    if (isNoLoopFolder(folderPath) && !isOutput) {
      return withCors(c.json({
        file_id: null,
        is_output: false,
        queued_source_add: false,
        skipped: true,
        reason: `folder_path thuộc vùng cấm inflow (${ARCHIVE_FOLDER})`,
      }, 200), origin);
    }

    const now = new Date().toISOString();
    const existing = await findFileBySha256(c.env, uid, sha);
    const fileId = existing?._id || stableFileId(sha);

    if (existing) {
      // Merge: chỉ bổ sung dữ liệu local, giữ nguyên nguồn gốc ban đầu
      const patch = {
        filename: existing.filename || filename,
        drive_file_id: drive_file_id || existing.drive_file_id || '',
        local_path: local_path || existing.local_path || '',
        size_bytes: size_bytes ? String(size_bytes) : (existing.size_bytes || '0'),
        is_output: isOutput || existing.is_output === true,
        updated_at: now,
      };
      if (!SOURCE_KINDS.includes(existing.source_kind)) patch.source_kind = 'local_scan';
      await firestoreSet(c.env, `users/${uid}/files/${fileId}`, patch);
    } else {
      await firestoreSet(c.env, `users/${uid}/files/${fileId}`, {
        id: fileId,
        filename,
        subject: subject || '',
        document_type: docType,
        folder_path: folderPath || DEFAULT_FOLDER,
        course_id: course_id || '',
        status: 'uploaded',
        is_output: isOutput,
        size_bytes: size_bytes ? String(size_bytes) : '0',
        sha256: sha,
        drive_file_id: drive_file_id || '',
        local_path: local_path || '',
        source_kind: 'local_scan',
        review_status: defaultReviewStatus(docType),
        review_note: '',
        reviewed_at: '',
        notebooklm_source_id: '',
        notebooklm_sync_status: 'pending',
        created_at: now,
        updated_at: now,
      });
    }

    // Lớp 2 NO-LOOP + tránh queue trùng khi đã sync
    const alreadySynced = existing?.notebooklm_sync_status === 'synced'
      && !!existing?.notebooklm_source_id;
    const taskId = (isOutput || alreadySynced)
      ? null
      : await enqueueSourceAdd(c.env, {
        uid,
        fileId,
        courseId: course_id || existing?.course_id || '',
        filename,
        subject: subject || existing?.subject || '',
        folderPath,
        isOutput,
        localPath: local_path || existing?.local_path || '',
        driveFileId: drive_file_id || existing?.drive_file_id || '',
      });

    return withCors(c.json({
      file_id: fileId,
      is_output: isOutput,
      queued_source_add: !!taskId,
      task_id: taskId || '',
      merged: !!existing,
      review_status: existing?.review_status || defaultReviewStatus(docType),
    }, existing ? 200 : 201), origin);
  } catch (err) {
    console.error('Register file error:', err);
    return withCors(c.json({ error: 'Đăng ký file thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
