// src/routes/ai/citations.js — POST /api/ai/citations/format (auth-or-agent) (§3.3) (<90 lines)

import { Hono } from 'hono';
import { requireAuthOrAgent } from '../../lib/auth.js';
import { withCors } from '../../lib/cors.js';
import { formatReferences } from '../../lib/citations.js';

const router = new Hono();

const ALLOWED_STYLES = ['auto', 'apa7', 'ieee', 'harvard'];

/**
 * POST /api/ai/citations/format
 * Body: {sources:[{title, authors, year, publisher, journal, url, doi, source_id, page}],
 *        style:'auto'|'apa7'|'ieee'|'harvard', inline:true}
 * → {style, references, reference_block, inline_markers}
 */
router.post('/format', requireAuthOrAgent(async (c) => {
  const origin = c.req.header('Origin') || '';

  try {
    const body = await c.req.json();
    const style = body.style || 'auto';

    if (!ALLOWED_STYLES.includes(style)) {
      return withCors(c.json({
        error: `style không hợp lệ: ${style}`,
        detail: `Cho phép: ${ALLOWED_STYLES.join(', ')}`,
      }, 400), origin);
    }

    const sources = body.sources;
    if (typeof sources === 'string') {
      try {
        JSON.parse(sources);
      } catch (err) {
        return withCors(c.json({ error: 'sources phải là mảng hoặc JSON string hợp lệ' }, 400), origin);
      }
    } else if (sources !== undefined && !Array.isArray(sources)) {
      return withCors(c.json({ error: 'sources phải là mảng nguồn' }, 400), origin);
    }

    const result = formatReferences(sources || [], style);

    // inline=false → không trả marker trong thân bài
    const inlineMarkers = body.inline === false ? [] : result.inline_markers;

    return withCors(c.json({
      style: result.style,
      references: result.references,
      reference_block: result.reference_block,
      inline_markers: inlineMarkers,
      count: result.references.length,
    }), origin);
  } catch (err) {
    console.error('Format citations error:', err);
    return withCors(c.json({ error: 'Định dạng trích dẫn thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
