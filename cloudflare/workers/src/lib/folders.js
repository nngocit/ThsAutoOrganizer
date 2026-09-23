// src/lib/folders.js — Hằng số dùng chung (§1 hợp đồng API) (<110 lines)
// Nguồn sự thật: docs/superpowers/specs/2026-09-23-phase2-4-api-contract.md
// KHÔNG đổi tên/key — local_agent/constants.py và pages/src/js/constants.js phải khớp.

export const FOLDER_MAP = {
  giao_trinh:     '01_Giao_Trinh_Goc',
  slide:          '02_Slide_Giang_Day',
  bai_bao:        '03_Tai_Lieu_Tham_Khao/01_Bai_Bao_Khoa_Hoc',
  unverified_web: '03_Tai_Lieu_Tham_Khao/02_Unverified_Web',
  ket_qua:        '04_Ket_Qua_Xuat_Ban',
};

export const OUTPUT_FOLDER = '04_Ket_Qua_Xuat_Ban';           // NO-LOOP GUARD
export const ARCHIVE_FOLDER = '_Archive_Trash_90Days';
export const NO_LOOP_FOLDERS = [OUTPUT_FOLDER, ARCHIVE_FOLDER]; // Inflow BỎ QUA
export const HARD_DELETE_DAYS = 90;
export const SUPPORTED_EXTENSIONS = [
  '.pdf', '.docx', '.pptx', '.txt', '.md', '.jpg', '.jpeg', '.png', '.mp3',
];

export const DEFAULT_FOLDER = FOLDER_MAP.giao_trinh;
export const DEFAULT_DOCUMENT_TYPE = 'giao_trinh';

/** Trạng thái duyệt nguồn (§2) */
export const REVIEW_STATUSES = ['unreviewed', 'approved', 'rejected', 'not_applicable'];
/** Nguồn gốc file (§2) */
export const SOURCE_KINDS = ['local_scan', 'web_upload', 'deep_research', 'artifact'];

/** Chuẩn hoá path: bỏ khoảng trắng, đổi \ thành /, bỏ '/' ở đầu và cuối */
export function normalizePath(folderPath) {
  let p = String(folderPath || '').trim().replace(/\\/g, '/');
  p = p.replace(/^\/+/, '').replace(/\/+$/, '');
  let prev = '';
  while (prev !== p) { prev = p; p = p.replace('//', '/'); }
  return p;
}

/** Lấy extension (lowercase, kèm dấu chấm) của filename */
export function extensionOf(filename) {
  const name = String(filename || '');
  const idx = name.lastIndexOf('.');
  return idx <= 0 ? '' : name.slice(idx).toLowerCase();
}

/** File có nằm trong danh sách extension được hỗ trợ không */
export function isSupportedFile(filename) {
  return SUPPORTED_EXTENSIONS.includes(extensionOf(filename));
}

/** Lớp 1 NO-LOOP: path có phải thư mục output 04_Ket_Qua_Xuat_Ban không */
export function isOutputFolder(folderPath) {
  const p = normalizePath(folderPath);
  if (!p) return false;
  return p === OUTPUT_FOLDER || p.startsWith(`${OUTPUT_FOLDER}/`);
}

/** Path thuộc vùng cấm inflow (output hoặc archive) */
export function isNoLoopFolder(folderPath) {
  const p = normalizePath(folderPath);
  if (!p) return false;
  return NO_LOOP_FOLDERS.some((f) => p === f || p.startsWith(`${f}/`));
}

/** document_type → folder_path (fallback 01_Giao_Trinh_Goc) */
export function folderForDocType(docType) {
  return FOLDER_MAP[docType] || DEFAULT_FOLDER;
}

/** folder_path → document_type (fallback giao_trinh) — dùng cho Local watcher */
export function docTypeFromFolder(folderPath) {
  const p = normalizePath(folderPath);
  if (!p) return DEFAULT_DOCUMENT_TYPE;
  // Ưu tiên path khớp dài nhất (tránh nhầm 01_Bai_Bao_Khoa_Hoc / 02_Unverified_Web)
  const hit = Object.entries(FOLDER_MAP)
    .filter(([, folder]) => p === folder || p.startsWith(`${folder}/`))
    .sort((a, b) => b[1].length - a[1].length)[0];
  return hit ? hit[0] : DEFAULT_DOCUMENT_TYPE;
}

/** §2: review_status mặc định theo document_type (ket_qua đã là output → approved) */
export function defaultReviewStatus(docType) {
  if (docType === 'unverified_web') return 'unreviewed';
  if (REVIEW_STATUSES.includes(docType)) return docType;
  return 'approved';
}

/** Chuẩn hoá doc file trả về client: luôn có review_status / is_output / source_kind */
export function normalizeFileDoc(doc) {
  const docType = doc.document_type || DEFAULT_DOCUMENT_TYPE;
  const folderPath = doc.folder_path || folderForDocType(docType);
  return {
    ...doc,
    document_type: docType,
    folder_path: folderPath,
    review_status: REVIEW_STATUSES.includes(doc.review_status)
      ? doc.review_status
      : defaultReviewStatus(docType),
    is_output: doc.is_output === true || isOutputFolder(folderPath),
    source_kind: SOURCE_KINDS.includes(doc.source_kind) ? doc.source_kind : 'web_upload',
  };
}
