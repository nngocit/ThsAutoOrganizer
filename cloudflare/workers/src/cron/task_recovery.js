// src/cron/task_recovery.js — G2: hồi phục task kẹt 'processing' (<120 lines)
// BỐI CẢNH: Agent/GitHub runner PATCH status='processing' trước khi chạy. Nếu tiến trình bị
// ngắt giữa chừng (PC tắt đột ngột, job GitHub hết timeout), task kẹt vĩnh viễn vì
// GET /api/tasks chỉ trả 'pending' → không ai nhặt lại.
// GIẢI PHÁP: task 'processing' quá X phút (mặc định 15) được trả về 'pending'.
// CÔNG TẮC: tắt bằng tasks_recovery_enabled=false (Firestore/Web UI) hoặc env.

import { firestoreSet } from '../lib/firebase.js';
import { firestoreRunQuery } from '../lib/firestore_query.js';
import { getTaskFlags } from '../lib/feature_flags.js';

export const RECOVERABLE_QUEUES = ['nlm_task_queue', 'drive_task_queue'];

/**
 * Trả các task 'processing' đã quá hạn về 'pending'.
 *
 * @param {Object} env
 * @param {{force?: boolean, now?: string|Date}} options
 *        force=true → chạy bỏ qua công tắc (nút "Hồi phục ngay" trên Web UI)
 * @returns {Promise<{enabled: boolean, checked: number, recovered: number, errors: number, stale_minutes: number}>}
 */
export async function recoverStaleTasks(env, { force = false, now = null } = {}) {
  const flags = await getTaskFlags(env, { forceRefresh: force });

  if (!force && !flags.recoveryEnabled) {
    console.log('[TaskRecovery] Đang TẮT (tasks_recovery_enabled=false) — bỏ qua');
    return { enabled: false, checked: 0, recovered: 0, errors: 0, stale_minutes: flags.staleMinutes };
  }

  const nowMs = now ? new Date(now).getTime() : Date.now();
  const thresholdMs = flags.staleMinutes * 60_000;
  const stats = {
    enabled: true,
    checked: 0,
    recovered: 0,
    errors: 0,
    stale_minutes: flags.staleMinutes,
  };

  for (const queue of RECOVERABLE_QUEUES) {
    let tasks = [];
    try {
      tasks = await firestoreRunQuery(env, queue, {
        fieldPath: 'status',
        value: 'processing',
        limit: 200,
      });
    } catch (err) {
      stats.errors++;
      console.error(`[TaskRecovery] Không truy vấn được ${queue}:`, err.message);
      continue;
    }

    stats.checked += tasks.length;

    for (const task of tasks) {
      const taskId = task.id || task._id || '';
      if (!taskId) continue;

      const claimedAt = task.processed_at || task.created_at || '';
      const claimedMs = claimedAt ? new Date(claimedAt).getTime() : 0;
      // Không có mốc thời gian → coi như mới claim, để vòng sau xử lý (tránh hồi phục oan)
      if (!claimedMs || nowMs - claimedMs < thresholdMs) continue;

      try {
        await firestoreSet(env, `${queue}/${taskId}`, {
          status: 'pending',
          error: '',
          recovered_at: new Date(nowMs).toISOString(),
          recovered_from: 'processing',
        });
        stats.recovered++;
        console.log(`[TaskRecovery] Trả về pending: ${queue}/${taskId} (kẹt từ ${claimedAt})`);
      } catch (err) {
        stats.errors++;
        console.error(`[TaskRecovery] Lỗi hồi phục ${queue}/${taskId}:`, err.message);
      }
    }
  }

  console.log(
    `[TaskRecovery] checked=${stats.checked} recovered=${stats.recovered} errors=${stats.errors} (ngưỡng ${stats.stale_minutes} phút)`
  );
  return stats;
}
