// src/lib/firebase.js — Firebase Firestore REST client (<150 lines)
// Dùng Firebase REST API thay vì SDK — tương thích Cloudflare Worker edge runtime

const FIRESTORE_BASE = (projectId) =>
  `https://asia-southeast1-firestore.googleapis.com/v1/projects/${projectId}/databases/(default)/documents`;

/** Base URL của Firestore REST documents (dùng cho runQuery / phân trang) */
export function firestoreRestBaseUrl(env) {
  const sa = JSON.parse(env.FIREBASE_SERVICE_ACCOUNT);
  return FIRESTORE_BASE(sa.project_id);
}

/** Export dùng chung cho các module Firestore khác (ví dụ firestore_query.js) */
export async function getAccessToken(serviceAccount) {
  const now = Math.floor(Date.now() / 1000);
  const payload = {
    iss: serviceAccount.client_email,
    sub: serviceAccount.client_email,
    aud: 'https://oauth2.googleapis.com/token',
    iat: now,
    exp: now + 3600,
    scope: 'https://www.googleapis.com/auth/datastore https://www.googleapis.com/auth/cloud-platform',
  };
  const header = { alg: 'RS256', typ: 'JWT' };
  const enc = (obj) =>
    btoa(JSON.stringify(obj)).replace(/=/g, '').replace(/\+/g, '-').replace(/\//g, '_');
  const signingInput = `${enc(header)}.${enc(payload)}`;

  const keyData = serviceAccount.private_key
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
  if (!data.access_token) throw new Error(`Firebase auth failed: ${JSON.stringify(data)}`);
  return data.access_token;
}

/** Chuyển JS object sang Firestore document format */
function toFirestoreDoc(obj) {
  const fields = {};
  if (!obj || typeof obj !== 'object') return { fields };

  for (const [k, v] of Object.entries(obj)) {
    if (v === undefined) continue; // Bỏ qua các field undefined

    if (typeof v === 'string') fields[k] = { stringValue: v };
    else if (typeof v === 'number' && Number.isInteger(v)) fields[k] = { integerValue: String(v) };
    else if (typeof v === 'number') fields[k] = { doubleValue: v };
    else if (typeof v === 'boolean') fields[k] = { booleanValue: v };
    else if (v === null) fields[k] = { nullValue: null };
    else fields[k] = { stringValue: JSON.stringify(v) };
  }
  return { fields };
}

/** Chuyển Firestore document sang JS object */
export function fromFirestoreDoc(doc) {
  if (!doc || !doc.fields) return {};
  const obj = { _id: doc.name ? doc.name.split('/').pop() : undefined };
  for (const [k, v] of Object.entries(doc.fields)) {
    if (v.stringValue !== undefined) obj[k] = v.stringValue;
    else if (v.integerValue !== undefined) obj[k] = parseInt(v.integerValue);
    else if (v.doubleValue !== undefined) obj[k] = v.doubleValue;
    else if (v.booleanValue !== undefined) obj[k] = v.booleanValue;
    else if (v.nullValue !== undefined) obj[k] = null;
    else obj[k] = v;
  }
  // Doc migrate từ SQLite không có field `id` — alias từ tên doc để client
  // luôn dùng được (sửa: session 404, message dedupe, course/file/insight id).
  if ((obj.id === undefined || obj.id === null || obj.id === '') && obj._id) {
    obj.id = obj._id;
  }
  return obj;
}

/** GET single document */
export async function firestoreGet(env, path) {
  const sa = JSON.parse(env.FIREBASE_SERVICE_ACCOUNT);
  const token = await getAccessToken(sa);
  const resp = await fetch(`${FIRESTORE_BASE(sa.project_id)}/${path}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (resp.status === 404) return null;
  if (!resp.ok) throw new Error(`Firestore GET ${path} failed: ${resp.status}`);
  return resp.json();
}

/** PATCH (upsert) document — merges fields */
export async function firestoreSet(env, path, data) {
  const sa = JSON.parse(env.FIREBASE_SERVICE_ACCOUNT);
  const token = await getAccessToken(sa);
  const body = toFirestoreDoc(data);

  // Tạo updateMask.fieldPaths đúng chuẩn URLSearchParams của Google
  const params = new URLSearchParams();
  Object.keys(data).forEach(key => {
    if (data[key] !== undefined) {
      params.append('updateMask.fieldPaths', key);
    }
  });

  const url = `${FIRESTORE_BASE(sa.project_id)}/${path}?${params.toString()}`;

  const resp = await fetch(url, {
    method: 'PATCH',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    const errText = await resp.text();
    throw new Error(`Firestore SET ${path} failed: ${resp.status} - ${errText}`);
  }
  return resp.json();
}

/** List documents in collection (basic, no server-side filter) */
export async function firestoreList(env, collectionPath, pageSize = 50) {
  const sa = JSON.parse(env.FIREBASE_SERVICE_ACCOUNT);
  const token = await getAccessToken(sa);
  const url = `${FIRESTORE_BASE(sa.project_id)}/${collectionPath}?pageSize=${pageSize}`;
  const resp = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
  if (!resp.ok) throw new Error(`Firestore LIST ${collectionPath} failed: ${resp.status}`);
  return resp.json();
}

/** DELETE document */
export async function firestoreDelete(env, path) {
  const sa = JSON.parse(env.FIREBASE_SERVICE_ACCOUNT);
  const token = await getAccessToken(sa);
  const resp = await fetch(`${FIRESTORE_BASE(sa.project_id)}/${path}`, {
    method: 'DELETE',
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!resp.ok) throw new Error(`Firestore DELETE ${path} failed: ${resp.status}`);
  return true;
}
