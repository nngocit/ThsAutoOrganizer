// src/lib/firestore_query.js — Truy vấn Firestore REST có WHERE (runQuery) (<90 lines)
// MỤC TIÊU (G1): lọc task theo status NGAY TẠI SERVER thay vì lấy N document đầu rồi lọc
// trong Worker (cách cũ làm task "vô hình" khi collection lớn, vì Firestore trả theo ID).
// LƯU Ý: chỉ dùng 1 điều kiện EQUALITY → tận dụng single-field index tự động,
// KHÔNG cần composite index (tránh lỗi "The query requires an index").

import { getAccessToken, firestoreRestBaseUrl, fromFirestoreDoc } from './firebase.js';

/** Chuyển giá trị JS → Firestore Value */
function toFirestoreValue(value) {
  if (typeof value === 'boolean') return { booleanValue: value };
  if (typeof value === 'number') {
    return Number.isInteger(value) ? { integerValue: String(value) } : { doubleValue: value };
  }
  if (value === null || value === undefined) return { nullValue: null };
  return { stringValue: String(value) };
}

/**
 * Chạy structured query 1 điều kiện equality trên 1 collection.
 *
 * @param {Object} env - Worker bindings (cần FIREBASE_SERVICE_ACCOUNT)
 * @param {string} collectionPath - 'nlm_task_queue' hoặc 'users/{uid}/files'
 * @param {{fieldPath: string, value: any, limit?: number}} options
 * @returns {Promise<Array<Object>>} danh sách document (đã map sang object phẳng, có `_id`)
 */
export async function firestoreRunQuery(env, collectionPath, { fieldPath, value, limit = 100 } = {}) {
  if (!collectionPath) throw new Error('collectionPath là bắt buộc');
  if (!fieldPath) throw new Error('fieldPath là bắt buộc');

  const sa = JSON.parse(env.FIREBASE_SERVICE_ACCOUNT);
  const token = await getAccessToken(sa);

  const segments = String(collectionPath).split('/').filter(Boolean);
  const collectionId = segments.pop();
  const parentPath = segments.join('/');
  const base = firestoreRestBaseUrl(env);
  const url = parentPath ? `${base}/${parentPath}:runQuery` : `${base}:runQuery`;

  const structuredQuery = {
    from: [{ collectionId }],
    where: {
      fieldFilter: {
        field: { fieldPath },
        op: 'EQUAL',
        value: toFirestoreValue(value),
      },
    },
    limit: Math.min(Math.max(parseInt(limit, 10) || 100, 1), 300),
  };

  const resp = await fetch(url, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ structuredQuery }),
  });

  if (!resp.ok) {
    const errText = await resp.text();
    throw new Error(`Firestore runQuery ${collectionPath} failed: ${resp.status} - ${errText}`);
  }

  const rows = await resp.json();
  return (Array.isArray(rows) ? rows : [])
    .filter((row) => row && row.document)
    .map((row) => fromFirestoreDoc(row.document));
}
