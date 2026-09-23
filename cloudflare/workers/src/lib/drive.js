// src/lib/drive.js — Google Drive API Client bằng Service Account (<180 lines)
// Sử dụng JWT Bearer để xác thực trực tiếp 24/7 với Google Drive REST API v3

const DRIVE_API = 'https://www.googleapis.com/drive/v3';
const DRIVE_UPLOAD_API = 'https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart';

/**
 * Lấy Access Token Google Drive từ Service Account JSON (env.FIREBASE_SERVICE_ACCOUNT)
 */
export async function getDriveAccessToken(env) {
  let sa = env.FIREBASE_SERVICE_ACCOUNT;
  if (!sa) throw new Error('Biến môi trường FIREBASE_SERVICE_ACCOUNT chưa được cấu hình');
  if (typeof sa === 'string') {
    try { sa = JSON.parse(sa); } catch (e) { throw new Error('FIREBASE_SERVICE_ACCOUNT không đúng định dạng JSON: ' + e.message); }
  }

  const now = Math.floor(Date.now() / 1000);
  const payload = {
    iss: sa.client_email,
    sub: sa.client_email,
    aud: 'https://oauth2.googleapis.com/token',
    iat: now,
    exp: now + 3600,
    scope: 'https://www.googleapis.com/auth/drive https://www.googleapis.com/auth/drive.file',
  };

  const header = { alg: 'RS256', typ: 'JWT' };
  const enc = (obj) =>
    btoa(JSON.stringify(obj)).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
  const signingInput = `${enc(header)}.${enc(payload)}`;

  const keyData = sa.private_key
    .replace('-----BEGIN PRIVATE KEY-----', '')
    .replace('-----END PRIVATE KEY-----', '')
    .replace(/\s/g, '');
  const binaryKey = Uint8Array.from(atob(keyData), (c) => c.charCodeAt(0));
  const cryptoKey = await crypto.subtle.importKey(
    'pkcs8', binaryKey,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false, ['sign']
  );
  const sig = await crypto.subtle.sign(
    'RSASSA-PKCS1-v1_5', cryptoKey, new TextEncoder().encode(signingInput)
  );
  const encodedSig = btoa(String.fromCharCode(...new Uint8Array(sig)))
    .replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
  const jwt = `${signingInput}.${encodedSig}`;

  const resp = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: `grant_type=urn%3Aietf%3Aparams%3Aoauth%3Agrant-type%3Ajwt-bearer&assertion=${jwt}`,
  });
  const data = await resp.json();
  if (!data.access_token) {
    throw new Error(`Google Drive Service Account auth thất bại: ${JSON.stringify(data)}`);
  }
  return data.access_token;
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
      'Content-Length': String(totalLength),
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

