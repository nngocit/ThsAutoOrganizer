// src/routes/auth/index.js — Google OAuth login & user profile (<100 lines)

import { Hono } from 'hono';
import { verifyIdToken } from '../../lib/auth.js';
import { firestoreSet, firestoreGet, fromFirestoreDoc } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';

const router = new Hono();

/**
 * POST /api/auth/login
 * Body: { id_token: string }
 * Verify Google ID Token → upsert user profile vào Firestore → trả về user info
 */
router.post('/login', async (c) => {
  const origin = c.req.header('Origin') || '';
  try {
    const body = await c.req.json();
    const { id_token } = body;

    if (!id_token) {
      return withCors(c.json({ error: 'id_token là bắt buộc' }, 400), origin);
    }

    const user = await verifyIdToken(c.env, id_token);
    const now = new Date().toISOString();

    // Upsert user profile (PATCH chỉ ghi đè các fields được chỉ định)
    await firestoreSet(c.env, `users/${user.uid}/profile/data`, {
      uid: user.uid,
      email: user.email,
      name: user.name,
      avatar_url: user.picture,
      email_verified: user.email_verified,
      last_login: now,
      updated_at: now,
    });

    return withCors(c.json({
      uid: user.uid,
      email: user.email,
      name: user.name,
      picture: user.picture,
    }), origin);
  } catch (err) {
    console.error('Login error:', err);
    return withCors(c.json({ error: 'Đăng nhập thất bại', detail: err.message }, 401), origin);
  }
});

/**
 * GET /api/auth/me
 * Authorization: Bearer <google_id_token>
 * Trả về thông tin user hiện tại từ Firestore
 */
router.get('/me', async (c) => {
  const origin = c.req.header('Origin') || '';
  try {
    const authHeader = c.req.header('Authorization') || '';
    if (!authHeader.startsWith('Bearer ')) {
      return withCors(c.json({ error: 'Unauthorized' }, 401), origin);
    }
    const token = authHeader.slice(7);
    const user = await verifyIdToken(c.env, token);

    const profileDoc = await firestoreGet(c.env, `users/${user.uid}/profile/data`);
    const profile = profileDoc ? fromFirestoreDoc(profileDoc) : {};

    return withCors(c.json({
      uid: user.uid,
      email: user.email,
      name: user.name,
      picture: user.picture,
      profile,
    }), origin);
  } catch (err) {
    return withCors(c.json({ error: 'Unauthorized', detail: err.message }, 401), origin);
  }
});

export default router;
