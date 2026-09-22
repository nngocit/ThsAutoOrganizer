// src/routes/insights/index.js — Mount insights sub-routes (<50 lines)

import { Hono } from 'hono';
import listRouter from './list.js';
import createRouter from './create.js';
import removeRouter from './remove.js';

const router = new Hono();

router.route('/', listRouter);    // GET /api/ai/insights
router.route('/', createRouter);  // POST /api/ai/insights
router.route('/', removeRouter);  // DELETE /api/ai/insights/:id

export default router;
