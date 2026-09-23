// src/lib/file_ids.js — Sinh/kiểm tra id tài liệu (<40 lines)

/** sha256 hợp lệ: hex 64 ký tự (lowercase) */
export function isValidSha256(value) {
  return /^[a-f0-9]{64}$/.test(String(value || '').toLowerCase());
}

/** id doc ổn định theo sha256 (idempotent khi Local watcher đăng ký lại) */
export function stableFileId(sha256) {
  return `m_${String(sha256 || '').toLowerCase().slice(0, 20)}`;
}

/** Chuẩn hoá sha256 về lowercase hex */
export function normalizeSha256(value) {
  return String(value || '').trim().toLowerCase();
}
