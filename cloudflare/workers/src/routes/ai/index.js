// src/routes/ai/index.js — Mount nhóm route /api/ai (<45 lines)
// insights + citations + research (§3.5) + artifact (§3.6)

import { Hono } from 'hono';
import insightsRouter from './insights.js';
import citationsRouter from './citations.js';
import researchRouter from './research.js';
import researchSourcesRouter from './research_sources.js';
import artifactRouter from './artifact.js';

const router = new Hono();

router.route('/insights', insightsRouter);       // /api/ai/insights*
router.route('/citations', citationsRouter);     // POST /api/ai/citations/format
router.route('/research', researchRouter);       // POST|GET /api/ai/research, GET|PATCH /:jobId
router.route('/research', researchSourcesRouter); // POST /api/ai/research/:jobId/sources
router.route('/', artifactRouter);               // /api/ai/artifact/* + GET /api/ai/artifacts

export default router;
