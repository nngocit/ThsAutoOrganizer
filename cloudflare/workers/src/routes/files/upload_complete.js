// src/routes/files/upload_complete.js — Phase 3: Hoàn tất upload, lưu metadata (<150 lines)
// Client đã upload file trực tiếp vào Drive, gửi sha256 + drive_file_id để Worker lưu Firestore

import { Hono } from 'hono';
import { requireAuth } from '../../lib/auth.js';
import { firestoreGet, firestoreSet, fromFirestoreDoc } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';
import { isOutputFolder } from '../../lib/folders.js';
import { isValidSha256, normalizeSha256 } from '../../lib/file_ids.js';
import { findFileBySha256 } from '../../lib/file_lookup.js';
import { enqueueSourceAdd } from '../../lib/tasks.js';

const router = new Hono();

/**
 * Xóa file trên Google Drive (dùng khi phát hiện duplicate sau khi đã upload).
 */
async function deleteDriveFile(accessToken, driveFileId) {
  if (!driveFileId || !accessToken) return;
  try {
    await fetch(`https://www.googleapis.com/drive/v3/files/${driveFileId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${accessToken}` },
    });
  } catch (err) {
    console.warn('Drive cleanup failed:', err.message);
  }
}

/**
 * Gán quyền public reader (type: 'anyone', role: 'reader') cho Google Drive file và lấy webViewLink.
 * BẮT BUỘC gọi API drive.permissions.create và chỉ trả về link webViewLink khi đã cấp quyền thành công.
 *
 * @param {string} accessToken - Google Drive OAuth access token
 * @param {string} driveFileId - File ID trên Google Drive
 * @returns {Promise<string>} webViewLink của file
 * @throws {Error} nếu không cấp được quyền hoặc không lấy được webViewLink
 */
export async function setPublicReaderPermission(accessToken, driveFileId) {
  if (!driveFileId) throw new Error('drive_file_id là bắt buộc');
  if (!accessToken) throw new Error('drive_access_token là bắt buộc để cấp quyền Google Drive');

  // 1. Gọi drive.permissions.create: type: 'anyone', role: 'reader'
  const permResp = await fetch(`https://www.googleapis.com/drive/v3/files/${driveFileId}/permissions`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      type: 'anyone',
      role: 'reader',
    }),
  });

  if (!permResp.ok) {
    const errText = await permResp.text();
    throw new Error(`drive.permissions.create failed (${permResp.status}): ${errText}`);
  }

  // 2. Lấy webViewLink khi đã cấp quyền thành công
  const getResp = await fetch(`https://www.googleapis.com/drive/v3/files/${driveFileId}?fields=id,webViewLink,webContentLink`, {
    headers: {
      Authorization: `Bearer ${accessToken}`,
    },
  });

  if (!getResp.ok) {
    const errText = await getResp.text();
    throw new Error(`drive.files.get failed (${getResp.status}): ${errText}`);
  }

  const fileData = await getResp.json();
  const webViewLink = fileData.webViewLink || '';
  if (!webViewLink) {
    throw new Error('Google Drive không trả về webViewLink sau khi cấp quyền');
  }

  return webViewLink;
}

// POST /api/files/upload/complete
router.post('/complete', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const body = await c.req.json();
    const { doc_id, sha256, drive_file_id, drive_access_token } = body;

    if (!doc_id || !sha256) {
      return withCors(c.json({ error: 'doc_id và sha256 là bắt buộc' }, 400), origin);
    }
    const sha = normalizeSha256(sha256);
    if (!isValidSha256(sha)) {
      return withCors(c.json({ error: 'sha256 không hợp lệ — phải là hex 64 ký tự' }, 400), origin);
    }

    // Kiểm tra doc tồn tại và thuộc về user này
    const existingDoc = await firestoreGet(c.env, `users/${user.uid}/files/${doc_id}`);
    if (!existingDoc) {
      return withCors(c.json({ error: 'Document không tồn tại hoặc không thuộc về bạn' }, 404), origin);
    }

    // Kiểm tra SHA-256 duplicate (bỏ qua pending_upload/archived)
    const duplicate = await findFileBySha256(c.env, user.uid, sha);
    if (duplicate) {
      // Dọn sạch Drive file vừa upload (nếu có)
      await deleteDriveFile(drive_access_token, drive_file_id);
      // Soft delete placeholder document
      await firestoreSet(c.env, `users/${user.uid}/files/${doc_id}`, {
        status: 'archived',
        updated_at: new Date().toISOString(),
      });
      return withCors(c.json({
        status: 'duplicate',
        sha256: sha,
        file_id: duplicate._id || duplicate.id || '',
      }, 409), origin);
    }

    // Cấp quyền public reader (type: anyone, role: reader) và lấy webViewLink
    let webViewLink = '';
    if (drive_file_id) {
      if (!drive_access_token) {
        return withCors(c.json({
          error: 'drive_access_token là bắt buộc để cấp quyền truy cập Drive',
        }, 400), origin);
      }
      try {
        webViewLink = await setPublicReaderPermission(drive_access_token, drive_file_id);
      } catch (permErr) {
        console.error('Lỗi drive.permissions.create:', permErr);
        return withCors(c.json({
          error: 'Không thể cấp quyền public reader cho file trên Google Drive',
          detail: permErr.message,
        }, 502), origin);
      }
    }

    const now = new Date().toISOString();
    const meta = fromFirestoreDoc(existingDoc);
    const isOutput = meta.is_output === true || isOutputFolder(meta.folder_path);

    // Cập nhật Firestore document với metadata đầy đủ kèm link xem file Drive
    await firestoreSet(c.env, `users/${user.uid}/files/${doc_id}`, {
      sha256: sha,
      drive_file_id: drive_file_id || '',
      drive_view_link: webViewLink || '',
      web_view_link: webViewLink || '',
      status: 'uploaded',
      is_output: isOutput,
      updated_at: now,
    });

    // Lớp 2 NO-LOOP: chỉ queue source_add khi file KHÔNG nằm trong 04_Ket_Qua_Xuat_Ban
    const taskId = await enqueueSourceAdd(c.env, {
      uid: user.uid,
      fileId: doc_id,
      courseId: meta.course_id || '',
      filename: meta.filename || '',
      subject: meta.subject || '',
      folderPath: meta.folder_path || '',
      isOutput,
      localPath: meta.local_path || '',
      driveFileId: drive_file_id || meta.drive_file_id || '',
    });

    return withCors(c.json({
      status: 'uploaded',
      doc_id,
      sha256: sha,
      drive_file_id: drive_file_id || '',
      webViewLink: webViewLink || '',
      drive_view_link: webViewLink || '',
      is_output: isOutput,
      queued_source_add: !!taskId,
    }), origin);
  } catch (err) {
    console.error('Upload complete error:', err);
    return withCors(c.json({ error: 'Upload complete thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
