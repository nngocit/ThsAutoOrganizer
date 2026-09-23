// cloudflare/pages/src/js/api.js — API client với Worker base URL (<150 lines)

const WORKER_URL = 'https://ths-organizer-api.ths-organizer-nngocit.workers.dev';

/**
 * Lấy Google ID Token hiện tại của user (từ Google Sign-In).
 * @returns {string|null}
 */
function getIdToken() {
  return window._googleIdToken || localStorage.getItem('ths_google_id_token') || null;
}

// ===== 401 handler hook (app.js đăng ký: dọn token hết hạn + prompt login lại) =====
let _unauthorizedHandler = null;
let _last401At = 0;

/** app.js gọi 1 lần khi init để xử lý tập trung mọi response 401 */
export function setUnauthorizedHandler(fn) { _unauthorizedHandler = fn; }

/**
 * Tạo headers chuẩn cho API requests.
 */
function buildHeaders(extra = {}) {
  const headers = { 'Content-Type': 'application/json', ...extra };
  const token = getIdToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;
  return headers;
}

/**
 * Helper chung để gọi Worker API.
 * @param {string} path - API path (vd: /api/files)
 * @param {RequestInit} options - fetch options
 * @returns {Promise<any>} Parsed JSON response
 * @throws {Error} nếu HTTP status >= 400
 */
async function apiFetch(path, options = {}) {
  const url = `${WORKER_URL}${path}`;
  const resp = await fetch(url, {
    ...options,
    headers: buildHeaders(options.headers || {}),
  });
  let data;
  try {
    data = await resp.json();
  } catch {
    data = {};
  }
  if (!resp.ok) {
    // Debounce 5s để nhiều request 401 đồng thời không spam handler
    if (resp.status === 401 && _unauthorizedHandler) {
      const now = Date.now();
      if (now - _last401At > 5000) { _last401At = now; _unauthorizedHandler(); }
    }
    const msg = data.error || data.detail || `HTTP ${resp.status}`;
    throw Object.assign(new Error(msg), { status: resp.status, data });
  }
  return data;
}

// ============================
// Auth API
// ============================

export const authApi = {
  /** Đăng nhập bằng Google ID Token */
  login: (idToken) => apiFetch('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ id_token: idToken }),
  }),

  /** Lấy thông tin user hiện tại */
  me: () => apiFetch('/api/auth/me'),
};

// ============================
// Files API
// ============================

export const filesApi = {
  /** Luồng 2: Upload trực tiếp file lên Worker -> Google Drive -> Firestore */
  upload: async (formData) => {
    const url = `${WORKER_URL}/api/files/upload`;
    const token = getIdToken();
    const headers = {};
    if (token) headers['Authorization'] = `Bearer ${token}`;

    const resp = await fetch(url, {
      method: 'POST',
      headers,
      body: formData,
    });
    let data;
    try { data = await resp.json(); } catch { data = {}; }
    if (!resp.ok) {
      const msg = data.error || data.detail || `HTTP ${resp.status}`;
      throw Object.assign(new Error(msg), { status: resp.status, data });
    }
    return data;
  },

  /** Phase 1: Khởi tạo upload session (legacy) */
  initUpload: (meta) => apiFetch('/api/files/upload/init', {
    method: 'POST', body: JSON.stringify(meta),
  }),

  /** Phase 3: Hoàn tất upload (legacy) */
  completeUpload: (payload) => apiFetch('/api/files/upload/complete', {
    method: 'POST', body: JSON.stringify(payload),
  }),

  /** List files với filter tùy chọn */
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch(`/api/files${qs ? '?' + qs : ''}`);
  },

  /** Xóa file (Safe Cascade Delete 4 bước) */
  delete: (fileId) => apiFetch(`/api/files/${fileId}`, { method: 'DELETE' }),
};

// ============================
// Courses API
// ============================

export const coursesApi = {
  list: () => apiFetch('/api/courses'),

  create: (data) => apiFetch('/api/courses', {
    method: 'POST', body: JSON.stringify(data),
  }),

  linkNotebookLM: (courseId, notebooklmId) =>
    apiFetch(`/api/courses/${courseId}/notebooklm`, {
      method: 'PUT', body: JSON.stringify({ notebooklm_id: notebooklmId }),
    }),
};

// ============================
// AI Insights API
// ============================

export const insightsApi = {
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch(`/api/ai/insights${qs ? '?' + qs : ''}`);
  },

  create: (data) => apiFetch('/api/ai/insights', {
    method: 'POST', body: JSON.stringify(data),
  }),

  delete: (id) => apiFetch(`/api/ai/insights/${id}`, { method: 'DELETE' }),
};

// ============================
// Chat API (Phase 3) — §3.2
// ============================

export const chatApi = {
  listSessions: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch(`/api/chat/sessions${qs ? '?' + qs : ''}`);
  },
  createSession: (data) => apiFetch('/api/chat/sessions', {
    method: 'POST', body: JSON.stringify(data),
  }),
  getSession: (id) => apiFetch(`/api/chat/sessions/${id}`),
  updateSession: (id, data) => apiFetch(`/api/chat/sessions/${id}`, {
    method: 'PATCH', body: JSON.stringify(data),
  }),
  /** soft delete (archive) mặc định; hard=true → xoá session + toàn bộ messages */
  deleteSession: (id, hard = false) =>
    apiFetch(`/api/chat/sessions/${id}${hard ? '?hard=1' : ''}`, { method: 'DELETE' }),
  /** Polling realtime: since = ISO timestamp, trả {messages, server_time} */
  getMessages: (id, since = '', limit = 100) => {
    const qs = new URLSearchParams({ limit: String(limit) });
    if (since) qs.set('since', since);
    return apiFetch(`/api/chat/sessions/${id}/messages?${qs}`);
  },
  /** Gửi prompt → 202 {message_id, job_id, status:'queued'} */
  sendMessage: (id, data) => apiFetch(`/api/chat/sessions/${id}/messages`, {
    method: 'POST', body: JSON.stringify(data),
  }),
  /** Source Selector: loại rejected & chưa uploaded */
  listSources: (courseId = '') => {
    const qs = courseId ? `?course_id=${encodeURIComponent(courseId)}` : '';
    return apiFetch(`/api/chat/sources${qs}`);
  },
};

// ============================
// Review API (Phase 4) — §3.4
// ============================

export const reviewApi = {
  list: (status = 'unreviewed') =>
    apiFetch(`/api/files/review?status=${encodeURIComponent(status)}`),
  /** {review_status:'approved'|'rejected', note?} → approved: queue source_add nếu chưa sync */
  review: (fileId, data) => apiFetch(`/api/files/${fileId}/review`, {
    method: 'POST', body: JSON.stringify(data),
  }),
};

// ============================
// Deep Research API (Phase 4) — §3.5
// ============================

export const researchApi = {
  /** → 202 {job_id, task_id, status:'queued'} */
  create: (data) => apiFetch('/api/ai/research', {
    method: 'POST', body: JSON.stringify(data),
  }),
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch(`/api/ai/research${qs ? '?' + qs : ''}`);
  },
  get: (jobId) => apiFetch(`/api/ai/research/${jobId}`),
};

// ============================
// Artifacts API (Phase 4) — §3.6
// ============================

export const artifactApi = {
  /** Queue tải artifact về 04_Ket_Qua_Xuat_Ban → 202 {task_id} */
  download: (data) => apiFetch('/api/ai/artifact/download', {
    method: 'POST', body: JSON.stringify(data),
  }),
  /** Files is_output===true */
  list: (courseId = '') => {
    const qs = courseId ? `?course_id=${encodeURIComponent(courseId)}` : '';
    return apiFetch(`/api/ai/artifacts${qs}`);
  },
};

// ============================
// Exam API (Phase 4) — §3.7
// ============================

export const examApi = {
  /** Tạo đề: 50 flashcard + 5 tự luận → 202 {job_id, task_id} */
  generate: (data) => apiFetch('/api/exam/sets/generate', {
    method: 'POST', body: JSON.stringify(data),
  }),
  /** List (không kèm flashcards/essays) */
  list: (courseId = '') => {
    const qs = courseId ? `?course_id=${encodeURIComponent(courseId)}` : '';
    return apiFetch(`/api/exam/sets${qs}`);
  },
  /** Full set (đã JSON.parse) */
  get: (id) => apiFetch(`/api/exam/sets/${id}`),
  delete: (id) => apiFetch(`/api/exam/sets/${id}`, { method: 'DELETE' }),
  /** Lưu điểm: {score, total, answers?} */
  saveAttempt: (id, data) => apiFetch(`/api/exam/sets/${id}/attempt`, {
    method: 'POST', body: JSON.stringify(data),
  }),
};

// ============================
// Citation Engine API — §3.3
// ============================

export const citationsApi = {
  /** {sources:[{title,authors,year,publisher,journal,url,doi,source_id,page}], style:'auto'|'apa7'|'ieee'|'harvard', inline:true} */
  format: (data) => apiFetch('/api/ai/citations/format', {
    method: 'POST', body: JSON.stringify(data),
  }),
};

// ============================
// Settings API — §3.8
// ============================

export const settingsApi = {
  /** Lấy cấu hình hệ thống hiện tại */
  getConfig: () => apiFetch('/api/settings/config'),
  /** Cập nhật cấu hình hệ thống */
  updateConfig: (data) => apiFetch('/api/settings/config', {
    method: 'PUT', body: JSON.stringify(data),
  }),
};

// ============================
// System Logs API — §3.9
// ============================

export const logsApi = {
  /** Danh sách logs: level, source, resolved, limit */
  list: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return apiFetch(`/api/logs${qs ? '?' + qs : ''}`);
  },
  /** Ghi log sự cố mới */
  create: (data) => apiFetch('/api/logs', {
    method: 'POST', body: JSON.stringify(data),
  }),
  /** Đánh dấu log đã được giải quyết/khắc phục */
  resolve: (logId) => apiFetch(`/api/logs/${logId}/resolve`, {
    method: 'PATCH',
  }),
};

/**
 * Tính SHA-256 của File object phía client (Web Crypto API).
 * @param {File} file
 * @returns {Promise<string>} hex string
 */
export async function computeSHA256(file) {
  const buffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest('SHA-256', buffer);
  return Array.from(new Uint8Array(hashBuffer))
    .map((b) => b.toString(16).padStart(2, '0'))
    .join('');
}

