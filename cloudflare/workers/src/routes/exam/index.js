// src/routes/exam/index.js — Mount nhóm route /api/exam (§3.7) (<25 lines)

import { Hono } from 'hono';
import generateRouter from './generate.js';
import setsRouter from './sets.js';
import attemptRouter from './attempt.js';

const router = new Hono();

router.route('/sets', generateRouter); // POST /api/exam/sets/generate
router.route('/sets', setsRouter);     // POST|GET /api/exam/sets, GET|DELETE /api/exam/sets/:id
router.route('/sets', attemptRouter);  // POST /api/exam/sets/:id/attempt

export default router;
