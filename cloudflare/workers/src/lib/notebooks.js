// src/lib/notebooks.js — Xác định notebook_id từ course (<50 lines)

import { firestoreGet, fromFirestoreDoc } from './firebase.js';

/** Lấy notebooklm_id của môn học; trả '' nếu môn chưa liên kết NotebookLM */
export async function notebookForCourse(env, uid, courseId) {
  if (!uid || !courseId) return '';
  try {
    const doc = await firestoreGet(env, `users/${uid}/courses/${courseId}`);
    if (!doc) return '';
    const data = fromFirestoreDoc(doc);
    return data.notebooklm_id || data.notebook_id || '';
  } catch (err) {
    console.warn('notebookForCourse lỗi:', err.message);
    return '';
  }
}

/** notebook_id hiệu lực: ưu tiên giá trị tường minh → fallback course */
export async function resolveNotebookId(env, uid, { notebookId = '', courseId = '' } = {}) {
  if (notebookId) return notebookId;
  return notebookForCourse(env, uid, courseId);
}
