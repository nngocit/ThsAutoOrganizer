// cloudflare/pages/src/js/constants.js — Hằng số dùng chung (§1 Hợp đồng Phase 2–4)
// SINGLE SOURCE OF TRUTH — đồng bộ với workers/src/lib/folders.js & local_agent/constants.py

export const FOLDER_MAP = {
  giao_trinh:     '01_Giao_Trinh_Goc',
  slide:          '02_Slide_Giang_Day',
  bai_bao:        '03_Tai_Lieu_Tham_Khao/01_Bai_Bao_Khoa_Hoc',
  unverified_web: '03_Tai_Lieu_Tham_Khao/02_Unverified_Web',
  ket_qua:        '04_Ket_Qua_Xuat_Ban',
};

export const OUTPUT_FOLDER   = '04_Ket_Qua_Xuat_Ban';        // NO-LOOP GUARD
export const ARCHIVE_FOLDER  = '_Archive_Trash_90Days';
export const NO_LOOP_FOLDERS = ['04_Ket_Qua_Xuat_Ban', '_Archive_Trash_90Days']; // Inflow BỎ QUA
export const HARD_DELETE_DAYS = 90;
export const SUPPORTED_EXTENSIONS = ['.pdf', '.docx', '.pptx', '.txt', '.md', '.jpg', '.jpeg', '.png', '.mp3'];

/** Kiểm tra folder path có thuộc vùng NO-LOOP (output/archive) không */
export function isNoLoopPath(folderPath = '') {
  return NO_LOOP_FOLDERS.some((f) => folderPath === f || folderPath.startsWith(f + '/'));
}

/** Lấy extension (lowercase, có dấu chấm) của tên file */
export function getExtension(filename = '') {
  const i = filename.lastIndexOf('.');
  return i >= 0 ? filename.slice(i).toLowerCase() : '';
}

// ----- UI metadata (badge) cho review_status & citation style -----

export const REVIEW_STATUS_META = {
  unreviewed:     { cls: 'badge-pending',    text: '🟡 Chờ duyệt' },
  approved:       { cls: 'badge-synced',     text: '✓ Đã duyệt' },
  rejected:       { cls: 'badge-failed',     text: '✗ Từ chối' },
  not_applicable: { cls: 'badge-processing', text: '— Không cần duyệt' },
};

export const CITATION_STYLES = [
  { value: 'auto',    label: 'Tự động' },
  { value: 'apa7',    label: 'APA 7' },
  { value: 'ieee',    label: 'IEEE' },
  { value: 'harvard', label: 'Harvard' },
];
