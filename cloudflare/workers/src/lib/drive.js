// src/lib/drive.js — Google Drive API Client bằng OAuth 2.0 User Refresh Token
// Xác thực thông qua User OAuth 2.0 Refresh Token (full quota Google Drive cá nhân, triệt tiêu 403 quota)

const DRIVE_API = 'https://www.googleapis.com/drive/v3';
const DRIVE_UPLOAD_API = 'https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart';

// Module-level in-memory token cache (sống trong vòng đời Worker instance)
let cachedDriveToken = null;
let driveTokenExpiry = 0;

/**
 * Lấy Access Token Google Drive độc quyền bằng OAuth 2.0 Refresh Token.
 * KHÔNG sử dụng Service Account JWT (giải quyết triệt để 403 storageQuotaExceeded).
 * Cache token 1 tiếng (trừ 60s an toàn).
 */
export async function getDriveAccessToken(env) {
  const now = Date.now();
  if (cachedDriveToken && now < driveTokenExpiry - 60000) {
    return cachedDriveToken;
  }

  const clientId = env.GOOGLE_CLIENT_ID;
  const clientSecret = env.GOOGLE_CLIENT_SECRET;
  const refreshToken = env.GOOGLE_REFRESH_TOKEN;

  if (!clientId || !clientSecret || !refreshToken) {
    throw new Error(
      `Thiếu cấu hình Google OAuth credentials cho Google Drive: ` +
      `GOOGLE_CLIENT_ID=${Boolean(clientId)}, GOOGLE_CLIENT_SECRET=${Boolean(clientSecret)}, GOOGLE_REFRESH_TOKEN=${Boolean(refreshToken)}`
    );
  }

  const resp = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      client_id: clientId,
      client_secret: clientSecret,
      refresh_token: refreshToken,
      grant_type: 'refresh_token',
    }).toString(),
  });

  const data = await resp.json();
  if (!resp.ok || !data.access_token) {
    const errorMsg = data.error_description || data.error || JSON.stringify(data);
    throw new Error(`Google OAuth Refresh Token exchange thất bại (${resp.status}): ${errorMsg}`);
  }

  cachedDriveToken = data.access_token;
  driveTokenExpiry = now + (data.expires_in || 3600) * 1000;
  return cachedDriveToken;
}

/**
 * Reset token cache (phục vụ unit test)
 */
export function _resetDriveTokenCache() {
  cachedDriveToken = null;
  driveTokenExpiry = 0;
}

/**
 * Tìm kiếm thư mục theo tên trên Google Drive (Idempotency - chống tạo trùng lặp)
 */
export async function findDriveFolderByName(env, folderName, parentId = '') {
  if (!folderName) return null;
  try {
    const token = await getDriveAccessToken(env);
    const escapedName = folderName.replace(/'/g, "\\'");
    let query = `mimeType = 'application/vnd.google-apps.folder' and name = '${escapedName}' and trashed = false`;
    if (parentId) {
      query += ` and '${parentId}' in parents`;
    }
    const q = encodeURIComponent(query);
    const resp = await fetch(`${DRIVE_API}/files?q=${q}&fields=files(id,name,createdTime)&pageSize=10`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    if (!resp.ok) {
      const err = await resp.text();
      console.warn(`Tìm thư mục Drive thất bại (${resp.status}): ${err}`);
      return null;
    }

    const data = await resp.json();
    const files = data.files || [];
    return files.length > 0 ? files[0] : null;
  } catch (err) {
    console.warn(`Ngoại lệ khi tìm thư mục Drive: ${err.message}`);
    return null;
  }
}

/**
 * Luồng 1: Tạo thư mục mới trên Google Drive
 */
export async function createDriveFolder(env, folderName, parentId = '') {
  const token = await getDriveAccessToken(env);
  const body = {
    name: folderName,
    mimeType: 'application/vnd.google-apps.folder',
  };
  if (parentId) {
    body.parents = [parentId];
  }

  const resp = await fetch(`${DRIVE_API}/files`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Tạo thư mục Drive thất bại (${resp.status}): ${err}`);
  }

  return await resp.json();
}

/**
 * Luồng 2: Upload file lên Google Drive qua multipart/related
 */
export async function uploadFileToDrive(env, { filename, mimeType, parentId, contentBuffer }) {
  const token = await getDriveAccessToken(env);
  const boundary = '-------314159265358979323846';
  const delimiter = `\r\n--${boundary}\r\n`;
  const closeDelimiter = `\r\n--${boundary}--`;

  const metadata = {
    name: filename,
    mimeType: mimeType || 'application/octet-stream',
  };
  if (parentId) {
    metadata.parents = [parentId];
  }

  const metaPart = `Content-Type: application/json; charset=UTF-8\r\n\r\n${JSON.stringify(metadata)}`;
  const mediaHeader = `Content-Type: ${mimeType || 'application/octet-stream'}\r\n\r\n`;

  // Ghép metadata text + binary buffer
  const encoder = new TextEncoder();
  const metaBytes = encoder.encode(delimiter + metaPart + delimiter + mediaHeader);
  const closeBytes = encoder.encode(closeDelimiter);

  const totalLength = metaBytes.byteLength + contentBuffer.byteLength + closeBytes.byteLength;
  const combined = new Uint8Array(totalLength);
  combined.set(metaBytes, 0);
  combined.set(new Uint8Array(contentBuffer), metaBytes.byteLength);
  combined.set(closeBytes, metaBytes.byteLength + contentBuffer.byteLength);

  const resp = await fetch(DRIVE_UPLOAD_API, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': `multipart/related; boundary=${boundary}`,
    },
    body: combined,
  });

  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Upload file lên Drive thất bại (${resp.status}): ${err}`);
  }

  return await resp.json();
}

/**
 * Cấp quyền Public Reader bằng access token trực tiếp (dùng cho cả test lẫn runtime)
 */
export async function setPublicReaderPermission(accessToken, driveFileId) {
  if (!driveFileId) throw new Error('drive_file_id là bắt buộc');
  if (!accessToken) throw new Error('accessToken là bắt buộc');

  // 1. Gán quyền anyone -> reader
  const permResp = await fetch(`${DRIVE_API}/files/${driveFileId}/permissions`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${accessToken}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ role: 'reader', type: 'anyone' }),
  });

  if (!permResp.ok) {
    const errText = await permResp.text();
    throw new Error(`drive.permissions.create failed (${permResp.status}): ${errText}`);
  }

  // 2. Lấy webViewLink
  const getResp = await fetch(`${DRIVE_API}/files/${driveFileId}?fields=id,webViewLink,webContentLink`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });

  if (!getResp.ok) {
    const errText = await getResp.text();
    throw new Error(`drive.files.get failed (${getResp.status}): ${errText}`);
  }

  const fileData = await getResp.json();
  if (!fileData.webViewLink) {
    throw new Error('Google Drive không trả về webViewLink sau khi cấp quyền');
  }

  return fileData.webViewLink;
}

/**
 * Luồng 2: Cấp quyền Public Reader (anyone, reader) dùng Service Account và trả về webViewLink
 */
export async function setDrivePublicReader(env, driveFileId) {
  const token = await getDriveAccessToken(env);
  return await setPublicReaderPermission(token, driveFileId);
}

/**
 * Luồng 3: Liệt kê các thư mục con trong thư mục cha trên Drive
 */
export async function listDriveSubfolders(env, parentId) {
  const token = await getDriveAccessToken(env);
  const q = encodeURIComponent(`'${parentId}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false`);
  const resp = await fetch(`${DRIVE_API}/files?q=${q}&fields=files(id,name,createdTime)&pageSize=100`, {
    headers: { Authorization: `Bearer ${token}` },
  });

  if (!resp.ok) {
    const err = await resp.text();
    throw new Error(`Liệt kê thư mục Drive thất bại (${resp.status}): ${err}`);
  }

  const data = await resp.json();
  return data.files || [];
}

/**
 * Cấp quyền Chỉnh sửa (writer) cho một email người dùng cụ thể trên file/thư mục Google Drive
 */
export async function setDriveWriterPermission(env, fileId, email) {
  if (!fileId) throw new Error('fileId là bắt buộc');
  if (!email) throw new Error('email là bắt buộc');

  const token = await getDriveAccessToken(env);
  const resp = await fetch(`${DRIVE_API}/files/${fileId}/permissions?sendNotificationEmail=false`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      role: 'writer',
      type: 'user',
      emailAddress: email,
    }),
  });

  if (!resp.ok) {
    const errText = await resp.text();
    throw new Error(`Cấp quyền writer Drive cho ${email} thất bại (${resp.status}): ${errText}`);
  }

  return await resp.json();
}

/**
 * Cấp quyền truy cập bất kỳ ai có link (anyone -> writer/reader) cho file/thư mục Google Drive
 */
export async function setDriveAnyonePermission(env, fileId, role = 'writer') {
  if (!fileId) throw new Error('fileId là bắt buộc');

  const token = await getDriveAccessToken(env);
  const resp = await fetch(`${DRIVE_API}/files/${fileId}/permissions`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({
      role: role,
      type: 'anyone',
    }),
  });

  if (!resp.ok) {
    const errText = await resp.text();
    console.warn(`Cấp quyền anyone (${role}) cho ${fileId} cảnh báo (${resp.status}): ${errText}`);
    return null;
  }

  return await resp.json();
}

