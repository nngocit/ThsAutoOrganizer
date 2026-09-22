// src/index.js — Cloudflare Worker entry point + cron handler (<60 lines)
// Router tổng mount tất cả sub-routes; export fetch + scheduled

import { Hono } from 'hono';
import { optionsResponse } from './lib/cors.js';
import { handleHardDelete } from './cron/hard_delete.js';

// Route modules
import authRouter from './routes/auth/index.js';
import filesRouter from './routes/files/index.js';
import insightsRouter from './routes/insights/index.js';
import coursesRouter from './routes/courses/index.js';
import syncRouter from './routes/sync/index.js';

const app = new Hono();

// Global CORS preflight handler
app.options('*', (c) => optionsResponse(c.req.header('Origin') || ''));

// Health check (không cần auth)
app.get('/health', (c) =>
  c.json({ status: 'ok', ts: Date.now(), service: 'ths-organizer-api' })
);

// Mount sub-routers
app.route('/api/auth', authRouter);
app.route('/api/files', filesRouter);
app.route('/api/ai/insights', insightsRouter);
app.route('/api/courses', coursesRouter);
app.route('/api/tasks', syncRouter);

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

  /**
   * Cron trigger handler — chạy theo wrangler.toml [triggers].crons
   * Lịch: "0 2 * * *" = 02:00 UTC mỗi ngày
   */
  async scheduled(event, env, ctx) {
    console.log(`[Cron] Trigger: ${event.cron} at ${new Date().toISOString()}`);
    if (event.cron === '0 2 * * *') {
      ctx.waitUntil(handleHardDelete(env));
    }
  },
};
