// cloudflare/pages/src/js/api.js — API client với Worker base URL (<150 lines)

const WORKER_URL = 'https://ths-organizer-api.ths-organizer-nngocit.workers.dev';

/**
 * Lấy Google ID Token hiện tại của user (từ Google Sign-In).
 * @returns {string|null}
 */
function getIdToken() {
  return window._googleIdToken || null;
}

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
  /** Phase 1: Khởi tạo upload session */
  initUpload: (meta) => apiFetch('/api/files/upload/init', {
    method: 'POST', body: JSON.stringify(meta),
  }),

  /** Phase 3: Hoàn tất upload */
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
