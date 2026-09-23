// src/lib/notebooks.js — Xác định notebook_id từ course hoặc subject (<60 lines)

import { firestoreGet, firestoreList, fromFirestoreDoc } from './firebase.js';

/** Lấy notebooklm_id của môn học theo courseId; trả '' nếu môn chưa liên kết NotebookLM */
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

/** Lấy notebooklm_id theo tên môn học (subject) */
export async function notebookForSubject(env, uid, subject) {
  if (!uid || !subject) return '';
  try {
    const resp = await firestoreList(env, `users/${uid}/courses`, 100);
    const courses = (resp.documents || []).map(fromFirestoreDoc);
    const sNorm = subject.toLowerCase().replace(/[^a-z0-9]/g, '');
    const matched = courses.find((c) => {
      const nameNorm = (c.name || '').toLowerCase().replace(/[^a-z0-9]/g, '');
      const keyNorm = (c.subject_key || '').toLowerCase().replace(/[^a-z0-9]/g, '');
      const folderNorm = (c.folder_name || '').toLowerCase().replace(/[^a-z0-9]/g, '');
      return (nameNorm && (nameNorm === sNorm || sNorm.includes(nameNorm) || nameNorm.includes(sNorm))) ||
             (keyNorm && (keyNorm === sNorm || sNorm.includes(keyNorm) || keyNorm.includes(sNorm))) ||
             (folderNorm && folderNorm === sNorm);
    });
    if (matched) {
      return matched.notebooklm_id || matched.notebook_id || '';
    }
  } catch (err) {
    console.warn('notebookForSubject lỗi:', err.message);
  }
  return '';
}

/** notebook_id hiệu lực: ưu tiên giá trị tường minh → course → subject */
export async function resolveNotebookId(env, uid, { notebookId = '', courseId = '', subject = '' } = {}) {
  if (notebookId) return notebookId;
  if (courseId) {
    const fromCourse = await notebookForCourse(env, uid, courseId);
    if (fromCourse) return fromCourse;
  }
  if (subject) {
    const fromSubj = await notebookForSubject(env, uid, subject);
    if (fromSubj) return fromSubj;
  }
  return '';
}

