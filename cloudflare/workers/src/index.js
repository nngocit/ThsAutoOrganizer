// src/index.js — Cloudflare Worker entry point + cron handler (<75 lines)
// Router tổng mount tất cả sub-routes; export fetch + scheduled

import { Hono } from 'hono';
import { cors } from 'hono/cors'; // <--- 1. Import cors từ hono
import { optionsResponse } from './lib/cors.js';
import { handleHardDelete } from './cron/hard_delete.js';

// Route modules
import authRouter from './routes/auth/index.js';
import filesRouter from './routes/files/index.js';
import aiRouter from './routes/ai/index.js';
import chatRouter from './routes/chat/index.js';
import coursesRouter from './routes/courses/index.js';
import syncRouter from './routes/sync/index.js';
import examRouter from './routes/exam/index.js';
import settingsRouter from './routes/settings/index.js';
import logsRouter from './routes/logs/index.js';

const app = new Hono();


// <--- 2. Bật CORS Middleware toàn cục cho tất cả các Route
app.use('*', cors({
  origin: '*',
  allowMethods: ['GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS'],
  allowHeaders: ['Content-Type', 'Authorization', 'X-Agent-Secret'],
}));

// Global CORS preflight handler
app.options('*', (c) => optionsResponse(c.req.header('Origin') || ''));

// Health check — KHÔNG đổi shape response (UI production đang phụ thuộc)
app.get('/health', (c) =>
  c.json({ status: 'ok', ts: Date.now(), service: 'ths-organizer-api' })
);

// Mount sub-routers
app.route('/api/auth', authRouter);
app.route('/api/files', filesRouter);
app.route('/api/ai', aiRouter);       // insights + citations + research + artifact
app.route('/api/chat', chatRouter);   // chat sessions, messages, agent-reply, sources
app.route('/api/courses', coursesRouter);
app.route('/api/tasks', syncRouter);
app.route('/api/exam', examRouter);   // Trạm Ôn Thi (§3.7)
app.route('/api/settings', settingsRouter); // Global Settings (§1)
app.route('/api/logs', logsRouter);         // System Logs Dashboard (§2)

// 404 fallback
app.notFound((c) =>
  c.json({ error: 'Not found', path: c.req.path }, 404)
);

// Global error handler
app.onError((err, c) => {
  console.error('[Worker Error]', err);
  return c.json({ error: 'Internal server error', detail: err.message }, 500);
});

// Export fetch handler + scheduled cron handler
export default {
  fetch: app.fetch,
  async scheduled(event, env, ctx) {
    console.log(`[Cron] Trigger: ${event.cron} at ${new Date().toISOString()}`);
    if (event.cron === '0 2 * * *') {
      ctx.waitUntil(handleHardDelete(env));
    }
  },
};
