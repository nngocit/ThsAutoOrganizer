// src/routes/chat/index.js — Mount chat sub-routes (§3.2) (<25 lines)

import { Hono } from 'hono';
import sessionsRouter from './sessions.js';
import sessionDetailRouter from './session_detail.js';
import messagesRouter from './messages.js';
import agentRouter from './agent.js';
import sourcesRouter from './sources.js';

const router = new Hono();

router.route('/', sourcesRouter);        // GET  /api/chat/sources
router.route('/sessions', sessionsRouter);       // GET|POST /api/chat/sessions
router.route('/sessions', sessionDetailRouter);  // GET|PATCH|DELETE /api/chat/sessions/:id
router.route('/sessions', messagesRouter);       // GET|POST /api/chat/sessions/:id/messages
router.route('/sessions', agentRouter);          // POST /api/chat/sessions/:id/agent-reply|agent-fail

export default router;
