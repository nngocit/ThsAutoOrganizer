// src/lib/feature_flags.js — Công tắc tính năng hàng đợi task (G1 + G2) (<120 lines)
// Thứ tự ưu tiên khi đọc cờ:
//   1. Firestore system_config/default  → chỉnh được ngay trên Web UI (Cài đặt → Bảo trì hàng đợi)
//   2. Biến môi trường Worker           → wrangler.toml [vars] (hoặc Dashboard → Settings → Variables)
//   3. Giá trị mặc định trong file này
// Cache 30 giây/isolate để không đọc Firestore mỗi request; mọi lỗi đọc đều fallback an toàn.

import { firestoreGet, firestoreSet, fromFirestoreDoc } from './firebase.js';

export const FLAG_KEYS = {
  queryMode: 'tasks_query_mode',
  recoveryEnabled: 'tasks_recovery_enabled',
  staleMinutes: 'tasks_stale_minutes',
  updatedAt: 'updated_at',
};

export const FLAG_DEFAULTS = {
  queryMode: 'query',        // 'query' = lọc pending phía server | 'legacy' = cách cũ (lấy N doc rồi lọc)
  recoveryEnabled: true,     // tự trả task kẹt 'processing' về 'pending'
  staleMinutes: 15,          // ngưỡng coi là "kẹt"
};

const CACHE_TTL_MS = 30_000;
let _cache = null;
let _cachedAt = 0;

function toBool(value, fallback) {
  if (value === undefined || value === null || value === '') return fallback;
  if (typeof value === 'boolean') return value;
  return ['1', 'true', 'yes', 'on', 'bat', 'bật'].includes(String(value).trim().toLowerCase());
}

function toMinutes(value, fallback) {
  const n = parseInt(value, 10);
  if (Number.isNaN(n)) return fallback;
  return Math.min(Math.max(n, 1), 1440);
}

/** Chuẩn hoá cờ từ config Firestore + env */
function normalize(cfg = {}, env = {}) {
  const rawMode = cfg[FLAG_KEYS.queryMode] ?? env.TASKS_QUERY_MODE ?? FLAG_DEFAULTS.queryMode;
  const mode = String(rawMode).trim().toLowerCase() === 'legacy' ? 'legacy' : 'query';
  return {
    queryMode: mode,
    recoveryEnabled: toBool(
      cfg[FLAG_KEYS.recoveryEnabled] ?? env.TASKS_RECOVERY_ENABLED,
      FLAG_DEFAULTS.recoveryEnabled
    ),
    staleMinutes: toMinutes(
      cfg[FLAG_KEYS.staleMinutes] ?? env.TASKS_STALE_MINUTES,
      FLAG_DEFAULTS.staleMinutes
    ),
    source: Object.keys(cfg).length ? 'firestore' : 'env_or_default',
  };
}

/** Chỉ lấy cờ từ env + mặc định (không gọi Firestore — dùng cho unit test/khởi động nhanh) */
export function taskFlagsFromEnv(env = {}) {
  return normalize({}, env);
}

/** Đọc cờ (có cache). Không bao giờ throw — lỗi Firestore sẽ fallback env/mặc định. */
export async function getTaskFlags(env, { forceRefresh = false } = {}) {
  const now = Date.now();
  if (!forceRefresh && _cache && now - _cachedAt < CACHE_TTL_MS) return _cache;

  let cfg = {};
  try {
    const doc = await firestoreGet(env, 'system_config/default');
    if (doc) cfg = fromFirestoreDoc(doc);
  } catch (err) {
    console.warn('getTaskFlags: không đọc được system_config (dùng env/mặc định):', err.message);
    return normalize({}, env); // không cache khi lỗi
  }

  _cache = normalize(cfg, env);
  _cachedAt = now;
  return _cache;
}

/** Ghi cờ vào Firestore system_config/default (merge — không xoá các key khác) */
export async function setTaskFlags(env, patch = {}) {
  const data = { [FLAG_KEYS.updatedAt]: new Date().toISOString() };

  if (patch.queryMode !== undefined) {
    data[FLAG_KEYS.queryMode] = String(patch.queryMode).toLowerCase() === 'legacy' ? 'legacy' : 'query';
  }
  if (patch.recoveryEnabled !== undefined) {
    data[FLAG_KEYS.recoveryEnabled] = toBool(patch.recoveryEnabled, FLAG_DEFAULTS.recoveryEnabled);
  }
  if (patch.staleMinutes !== undefined) {
    data[FLAG_KEYS.staleMinutes] = toMinutes(patch.staleMinutes, FLAG_DEFAULTS.staleMinutes);
  }

  await firestoreSet(env, 'system_config/default', data);
  _cache = null;
  _cachedAt = 0;
  return getTaskFlags(env, { forceRefresh: true });
}

/** Xoá cache (dùng cho unit test và khi cần áp dụng cờ ngay lập tức) */
export function resetTaskFlagCache() {
  _cache = null;
  _cachedAt = 0;
}
