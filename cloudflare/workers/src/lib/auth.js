// src/lib/auth.js — Google ID Token verification + requireAuth middleware (<80 lines)

const GOOGLE_TOKEN_INFO_URL = 'https://oauth2.googleapis.com/tokeninfo';

/**
 * Verify Google ID Token và trả về thông tin user.
 * @param {Object} env - Worker environment (cần GOOGLE_CLIENT_ID)
 * @param {string} token - Google ID Token từ Authorization header
 * @returns {Promise<{uid: string, email: string, name: string, picture: string}>}
 * @throws {Error} nếu token không hợp lệ hoặc hết hạn
 */
export async function verifyIdToken(env, token) {
  if (!token || token.trim() === '') throw new Error('No token provided');

  const resp = await fetch(`${GOOGLE_TOKEN_INFO_URL}?id_token=${encodeURIComponent(token)}`);
  if (!resp.ok) throw new Error(`Token verification failed: HTTP ${resp.status}`);

  const data = await resp.json();
  if (data.error) throw new Error(`Token error: ${data.error} — ${data.error_description || ''}`);

  // Kiểm tra audience khớp với Google Client ID
  const validAud = env.GOOGLE_CLIENT_ID;
  if (validAud && data.aud !== validAud) {
    throw new Error('Token audience mismatch — possible token reuse attack');
  }

  // Kiểm tra token chưa hết hạn
  const expiry = parseInt(data.exp || '0', 10);
  if (expiry < Math.floor(Date.now() / 1000)) {
    throw new Error('Token expired');
  }

  return {
    uid: data.sub,           // Google User ID — dùng làm Firestore user namespace
    email: data.email || '',
    name: data.name || '',
    picture: data.picture || '',
    email_verified: data.email_verified === 'true',
  };
}

/**
 * Middleware HOF: wrap route handler để tự động verify auth.
 * Sets c.get('user') = {uid, email, name, picture} nếu hợp lệ.
 *
 * @param {Function} handler - Hono route handler (c) => Response
 * @returns {Function} Wrapped handler
 *
 * @example
 * router.get('/protected', requireAuth(async (c) => {
 *   const user = c.get('user');
 *   return c.json({ uid: user.uid });
 * }));
 */
export function requireAuth(handler) {
  return async (c) => {
    try {
      const authHeader = c.req.header('Authorization') || '';
      if (!authHeader.startsWith('Bearer ')) {
        return c.json({ error: 'Unauthorized', detail: 'Missing Bearer token' }, 401);
      }
      const token = authHeader.slice(7); // Remove "Bearer "
      const user = await verifyIdToken(c.env, token);
      c.set('user', user);
      return handler(c);
    } catch (err) {
      return c.json({ error: 'Unauthorized', detail: err.message }, 401);
    }
  };
}

/**
 * Dùng cho Python local agent (poll task queue) — verify bằng shared secret thay vì Google token.
 * Agent gửi header: X-Agent-Secret: <AGENT_SECRET>
 */
export function requireAgentAuth(handler) {
  return async (c) => {
    const secret = c.req.header('X-Agent-Secret') || '';
    const expected = c.env.AGENT_SECRET || '';
    if (!expected || secret !== expected) {
      return c.json({ error: 'Forbidden', detail: 'Invalid agent secret' }, 403);
    }
    return handler(c);
  };
}
