// src/index.js — Cloudflare Worker entry point + cron handler (<85 lines)
// Router tổng mount các sub-routes hợp lệ; export fetch + scheduled

import { Hono } from 'hono';
import { cors } from 'hono/cors';
import { optionsResponse, isAllowedOrigin } from './lib/cors.js';
import { handleHardDelete } from './cron/hard_delete.js';
import { recoverStaleTasks } from './cron/task_recovery.js';

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

// Global CORS Middleware
app.use('*', cors({
  origin: (origin) => (isAllowedOrigin(origin) ? origin : (origin || '*')),
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
app.route('/api/ai', aiRouter);               // citations + research + artifact
app.route('/api/chat', chatRouter);           // chat sessions, messages, agent-reply, sources
app.route('/api/courses', coursesRouter);     // Luồng 1: Master Creation Flow
app.route('/api/tasks', syncRouter);          // Task queues polling & status updates
app.route('/api/sync', syncRouter);           // Luồng 3: Reconciliation & Drive Folder Import
app.route('/api/exam', examRouter);           // Trạm Ôn Thi
app.route('/api/settings', settingsRouter);   // Global Settings
app.route('/api/drive', settingsRouter);      // Drive operations (init-root, provision-drive)
app.route('/api/logs', logsRouter);           // System Logs Dashboard

// 404 fallback với CORS headers đầy đủ
app.notFound((c) => {
  const origin = c.req.header('Origin') || '*';
  c.header('Access-Control-Allow-Origin', origin);
  return c.json({ error: 'Not found', path: c.req.path }, 404);
});

// Global error handler: JSON log có cấu trúc & đính kèm CORS headers
app.onError((err, c) => {
  const origin = c.req.header('Origin') || '*';
  const errorLog = {
    level: 'ERROR',
    timestamp: new Date().toISOString(),
    method: c.req.method,
    path: c.req.path,
    error: err.message,
    stack: err.stack,
  };
  console.error('[Worker Fatal Error]', JSON.stringify(errorLog));

  c.header('Access-Control-Allow-Origin', origin);
  c.header('Access-Control-Allow-Methods', 'GET, POST, PUT, PATCH, DELETE, OPTIONS');
  c.header('Access-Control-Allow-Headers', 'Content-Type, Authorization, X-Agent-Secret');

  return c.json({
    error: 'Internal server error',
    detail: err.message,
    path: c.req.path,
    timestamp: errorLog.timestamp,
  }, 500);
});

// Export fetch handler + scheduled cron handler
export default {
  fetch: app.fetch,
  async scheduled(event, env, ctx) {
    console.log(`[Cron] Trigger: ${event.cron} at ${new Date().toISOString()}`);

    // G2: hồi phục task kẹt 'processing' (tự bỏ qua nếu công tắc đang tắt)
    ctx.waitUntil(
      recoverStaleTasks(env).catch((err) =>
        console.error('[Cron] TaskRecovery lỗi:', err.message)
      )
    );

    if (event.cron === '0 2 * * *') {
      ctx.waitUntil(handleHardDelete(env));
    }
  },
};
