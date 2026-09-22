// src/cron/hard_delete.js — Cron job xóa hard sau 90 ngày (<150 lines)
// Chạy hàng ngày lúc 02:00 UTC theo trigger trong wrangler.toml

import { firestoreList, firestoreDelete, firestoreSet, fromFirestoreDoc } from '../lib/firebase.js';

/**
 * Query tất cả archived_files có hard_delete_at <= now và xóa chúng.
 * Ghi audit log vào file_deletion_logs trước khi xóa.
 *
 * @param {Object} env - Cloudflare Worker environment bindings
 * @returns {Promise<{checked: number, deleted: number, errors: number}>}
 */
export async function handleHardDelete(env) {
  const now = new Date().toISOString();
  console.log(`[HardDelete Cron] Bắt đầu lúc ${now}`);

  const stats = { checked: 0, deleted: 0, errors: 0 };

  try {
    // Lấy tất cả archived_files (flat collection dễ query)
    const resp = await firestoreList(env, 'archived_files', 200);
    const docs = (resp.documents || []).map((doc) => ({
      _path: doc.name.split('/documents/')[1],
      ...fromFirestoreDoc(doc),
    }));

    stats.checked = docs.length;
    console.log(`[HardDelete Cron] Tìm thấy ${docs.length} files đã archive`);

    for (const fileData of docs) {
      const hardDeleteAt = fileData.hard_delete_at || '';

      // Chỉ xóa nếu đã qua thời hạn 90 ngày
      if (!hardDeleteAt || hardDeleteAt > now) continue;

      try {
        // Ghi audit log vào file_deletion_logs TRƯỚC khi xóa
        const logId = crypto.randomUUID();
        await firestoreSet(env, `file_deletion_logs/${logId}`, {
          id: logId,
          original_doc_path: fileData._path || '',
          filename: fileData.filename || 'unknown',
          sha256: fileData.sha256 || '',
          user_email: fileData.user_email || '',
          uid: fileData.uid || '',
          drive_file_id: fileData.drive_file_id || '',
          archived_at: fileData.archived_at || '',
          hard_deleted_at: now,
          backup_cloud_link: fileData.drive_file_id
            ? `https://drive.google.com/file/d/${fileData.drive_file_id}`
            : '',
        });

        // Queue task cho Python agent để xóa file Drive vĩnh viễn
        if (fileData.drive_file_id && fileData.uid) {
          const taskId = crypto.randomUUID();
          await firestoreSet(env, `drive_task_queue/${taskId}`, {
            id: taskId,
            action: 'hard_delete',
            uid: fileData.uid,
            file_id: fileData._id || '',
            drive_file_id: fileData.drive_file_id,
            status: 'pending',
            created_at: now,
          });
        }

        // Xóa Firestore document khỏi archived_files
        const docId = fileData._id || fileData._path?.split('/').pop();
        if (docId) {
          await firestoreDelete(env, `archived_files/${docId}`);
        }

        stats.deleted++;
        console.log(`[HardDelete] Đã xóa: ${fileData.filename} (${fileData.user_email})`);
      } catch (itemErr) {
        stats.errors++;
        console.error(`[HardDelete] Lỗi với file ${fileData._path}:`, itemErr.message);
        // Tiếp tục xử lý các file khác dù có lỗi
      }
    }

    console.log(
      `[HardDelete Cron] Hoàn tất: checked=${stats.checked}, deleted=${stats.deleted}, errors=${stats.errors}`
    );
    return stats;
  } catch (err) {
    console.error('[HardDelete Cron] Lỗi nghiêm trọng:', err.message);
    throw err;
  }
}
