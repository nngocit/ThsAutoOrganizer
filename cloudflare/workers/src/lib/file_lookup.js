// src/lib/file_lookup.js — Truy vấn collection users/{uid}/files (<80 lines)
// Firestore REST không hỗ trợ WHERE tốt trên edge → lấy trang rồi lọc phía Worker.

import { firestoreList, fromFirestoreDoc } from './firebase.js';

/** Doc coi như "không tồn tại" khi đang upload dở hoặc đã archive */
export const HIDDEN_STATUSES = ['pending_upload', 'archived'];

/** Danh sách file của user (đã bỏ field rác _id trùng) */
export async function listUserFiles(env, uid, pageSize = 200) {
  const resp = await firestoreList(env, `users/${uid}/files`, pageSize);
  return (resp.documents || []).map(fromFirestoreDoc);
}

/** Tìm file theo sha256 (bỏ qua pending_upload/archived) → doc hoặc null */
export async function findFileBySha256(env, uid, sha256) {
  if (!sha256) return null;
  const files = await listUserFiles(env, uid);
  return files.find(
    (f) => f.sha256 === sha256 && !HIDDEN_STATUSES.includes(f.status)
  ) || null;
}

/** Tìm file theo id doc (bỏ qua pending_upload/archived) → doc hoặc null */
export async function findFileByDocId(env, uid, docId) {
  const files = await listUserFiles(env, uid);
  return files.find((f) => f._id === docId && !HIDDEN_STATUSES.includes(f.status)) || null;
}
