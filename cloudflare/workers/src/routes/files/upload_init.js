// src/routes/files/upload_init.js — Phase 1: Tạo Google Drive upload session (<150 lines)
// Client gửi metadata → Worker tạo Drive resumable URL → Client upload trực tiếp vào Drive
// NO-LOOP lớp 1: is_output = folder_path nằm trong 04_Ket_Qua_Xuat_Ban

import { Hono } from 'hono';
import { requireAuth } from '../../lib/auth.js';
import { firestoreSet } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';
import {
  folderForDocType, defaultReviewStatus, isSupportedFile, extensionOf, isOutputFolder,
} from '../../lib/folders.js';

const router = new Hono();

/**
 * Tạo Google Drive resumable upload session.
 * Dùng user's OAuth access token (lấy từ Google Sign-In trên frontend).
 */
async function createDriveUploadSession(accessToken, filename, mimeType, folderId) {
  const metadata = {
    name: filename,
    parents: folderId ? [folderId] : [],
  };
  const resp = await fetch(
    'https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable',
    {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
        'X-Upload-Content-Type': mimeType,
      },
      body: JSON.stringify(metadata),
    }
  );
  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Drive session creation failed: ${resp.status} — ${err}`);
  }
  // Location header chứa resumable upload URL
  const uploadUrl = resp.headers.get('Location');
  if (!uploadUrl) throw new Error('Drive did not return upload URL');
  return uploadUrl;
}

/** Detect MIME type từ file extension */
function getMimeType(filename) {
  const ext = '.' + filename.split('.').pop().toLowerCase();
  const mimeMap = {
    '.pdf': 'application/pdf',
    '.docx': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    '.pptx': 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
    '.txt': 'text/plain',
    '.md': 'text/markdown',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.mp3': 'audio/mpeg',
  };
  return mimeMap[ext] || 'application/octet-stream';
}

// POST /api/files/upload/init
router.post('/init', requireAuth(async (c) => {
  const user = c.get('user');
  const origin = c.req.header('Origin') || '';

  try {
    const body = await c.req.json();
    const { filename, size_bytes, subject, document_type, course_id, drive_access_token } = body;

    if (!filename || !subject) {
      return withCors(c.json({ error: 'filename và subject là bắt buộc' }, 400), origin);
    }

    // Validate extension — dùng bảng hỗ trợ chung (§1)
    if (!isSupportedFile(filename)) {
      const ext = extensionOf(filename) || '(không rõ)';
      return withCors(c.json({ error: `Định dạng ${ext} không được hỗ trợ` }, 415), origin);
    }

    const docType = document_type || 'giao_trinh';
    const folderPath = folderForDocType(docType);
    const isOutput = isOutputFolder(folderPath); // Lớp 1 NO-LOOP
    const mimeType = getMimeType(filename);

    // Tạo Drive resumable upload session (dùng user's access token)
    let uploadUrl = null;
    if (drive_access_token) {
      uploadUrl = await createDriveUploadSession(drive_access_token, filename, mimeType, null);
    }

    // Tạo Firestore document placeholder với status pending_upload
    const docId = crypto.randomUUID();
    const now = new Date().toISOString();
    const expiresAt = new Date(Date.now() + 30 * 60 * 1000).toISOString(); // 30 phút

    await firestoreSet(c.env, `users/${user.uid}/files/${docId}`, {
      id: docId,
      filename,
      subject,
      document_type: docType,
      folder_path: folderPath,
      course_id: course_id || '',
      status: 'pending_upload',
      is_output: isOutput,
      size_bytes: size_bytes ? String(size_bytes) : '0',
      sha256: '',
      drive_file_id: '',
      local_path: '',
      source_kind: 'web_upload',
      review_status: defaultReviewStatus(docType),
      review_note: '',
      reviewed_at: '',
      notebooklm_source_id: '',
      notebooklm_sync_status: 'pending',
      user_email: user.email,
      created_at: now,
      updated_at: now,
    });

    return withCors(c.json({
      doc_id: docId,
      upload_url: uploadUrl,
      expires_at: expiresAt,
      folder_path: folderPath,
      is_output: isOutput,
      mime_type: mimeType,
    }, 201), origin);
  } catch (err) {
    console.error('Upload init error:', err);
    return withCors(c.json({ error: 'Upload init thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
