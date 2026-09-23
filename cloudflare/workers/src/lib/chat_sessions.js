// src/lib/chat_sessions.js — Helper đọc/ghi chat session (<90 lines)
// §2: mảng/object lưu dạng JSON string (selected_source_ids)

import { firestoreList, firestoreGet, firestoreSet, fromFirestoreDoc } from './firebase.js';

export const SESSION_STATUSES = ['active', 'archived'];

/** Parse an toàn về mảng */
export function parseArray(value) {
  if (Array.isArray(value)) return value;
  if (typeof value === 'string' && value.trim()) {
    try {
      const arr = JSON.parse(value);
      return Array.isArray(arr) ? arr : [];
    } catch (err) {
      return [];
    }
  }
  return [];
}

/** Chuẩn hoá session gửi về client (đã parse selected_source_ids) */
export function normalizeSession(doc) {
  return {
    ...doc,
    selected_source_ids: parseArray(doc.selected_source_ids),
    status: SESSION_STATUSES.includes(doc.status) ? doc.status : 'active',
    message_count: parseInt(doc.message_count || 0, 10) || 0,
    orphan_warning: doc.orphan_warning === true,
  };
}

/** Chuẩn hoá message gửi về client (đã parse citations, có trường mặc định) */
export function normalizeMessage(doc) {
  return {
    ...doc,
    citations: parseArray(doc.citations),
    citation_style: doc.citation_style || 'none',
    status: doc.status || 'done',
    error: doc.error || '',
    reference_block: doc.reference_block || '',
  };
}

/** Đọc session + kiểm tra ownership (session nằm trong users/{uid}) */
export async function getOwnedSession(env, uid, sessionId) {
  if (!sessionId) return null;
  const doc = await firestoreGet(env, `users/${uid}/chat_sessions/${sessionId}`);
  return doc ? { ...fromFirestoreDoc(doc), _raw: doc } : null;
}

/** Danh sách session của user, mới nhất trước */
export async function listSessions(env, uid, { courseId = '', status = '' } = {}) {
  const resp = await firestoreList(env, `users/${uid}/chat_sessions`, 100);
  let sessions = (resp.documents || []).map(fromFirestoreDoc);
  if (courseId) sessions = sessions.filter((s) => s.course_id === courseId);
  if (status) sessions = sessions.filter((s) => (s.status || 'active') === status);
  sessions.sort((a, b) => (b.last_message_at || b.updated_at || b.created_at || '')
    .localeCompare(a.last_message_at || a.updated_at || a.created_at || ''));
  return sessions;
}

/** Danh sách message của 1 session (mới nhất trước theo created_at) */
export async function listMessages(env, uid, sessionId, limit = 100) {
  const resp = await firestoreList(env, `users/${uid}/chat_sessions/${sessionId}/messages`, 200);
  const messages = (resp.documents || []).map(fromFirestoreDoc);
  messages.sort((a, b) => (a.created_at || '').localeCompare(b.created_at || ''));
  return messages.slice(-limit);
}

/** Tìm message theo id trong session */
export async function getMessage(env, uid, sessionId, messageId) {
  if (!messageId) return null;
  const doc = await firestoreGet(env, `users/${uid}/chat_sessions/${sessionId}/messages/${messageId}`);
  return doc ? fromFirestoreDoc(doc) : null;
}

/** Cập nhật metadata session sau khi thêm message */
export async function touchSession(env, uid, sessionId, patch = {}) {
  const now = new Date().toISOString();
  await firestoreSet(env, `users/${uid}/chat_sessions/${sessionId}`, {
    last_message_at: now,
    updated_at: now,
    ...patch,
  });
  return now;
}
