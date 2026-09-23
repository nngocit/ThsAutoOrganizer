// src/lib/cors.js — CORS helpers (<50 lines)
// Quản lý tập trung các CORS headers cho tất cả Worker endpoints

const ALLOWED_ORIGINS = [
  'https://ths-organizer.pages.dev',
  'https://aeb9c0e2.ths-organizer.pages.dev',
  'https://ths-organizer-api.ths-organizer-nngocit.workers.dev',
  'http://localhost:3000',
  'http://localhost:8080',
  'http://127.0.0.1:3000',
];

/**
 * Trả về CORS headers cho origin được phép.
 * @param {string} requestOrigin
 * @returns {Object} headers object
 */
export function corsHeaders(requestOrigin) {
  const origin = ALLOWED_ORIGINS.includes(requestOrigin)
    ? requestOrigin
    : ALLOWED_ORIGINS[0];
  return {
    'Access-Control-Allow-Origin': origin,
    'Access-Control-Allow-Methods': 'GET, POST, PUT, PATCH, DELETE, OPTIONS',
    'Access-Control-Allow-Headers': 'Content-Type, Authorization',
    'Access-Control-Max-Age': '86400',
  };
}

/**
 * Thêm CORS headers vào response hiện có.
 * @param {Response} response
 * @param {string} requestOrigin
 * @returns {Response}
 */
export function withCors(response, requestOrigin) {
  const headers = corsHeaders(requestOrigin);
  const newResp = new Response(response.body, response);
  for (const [k, v] of Object.entries(headers)) {
    newResp.headers.set(k, v);
  }
  return newResp;
}

/**
 * Trả về 204 No Content cho OPTIONS preflight.
 * @param {string} requestOrigin
 * @returns {Response}
 */
export function optionsResponse(requestOrigin) {
  return new Response(null, {
    status: 204,
    headers: corsHeaders(requestOrigin),
  });
}
