// src/routes/chat/agent.js — POST agent-reply | agent-fail (agent auth) (§3.2) (<190 lines)
// QUY ƯỚC: `message_id` trong body = id tin nhắn PROMPT của user (đã gửi qua POST messages).
// Trả về `message_id` MỚI của tin nhắn assistant vừa tạo (idempotent nếu agent gửi lại).

import { Hono } from 'hono';
import { requireAgentAuth, resolveTargetUid } from '../../lib/auth.js';
import { firestoreSet } from '../../lib/firebase.js';
import { withCors } from '../../lib/cors.js';
import { formatReferences, sourceFromFileDoc, normalizeSource } from '../../lib/citations.js';
import { normalizeFileDoc } from '../../lib/folders.js';
import { listUserFiles } from '../../lib/file_lookup.js';
import { parseArray, getOwnedSession, getMessage, touchSession } from '../../lib/chat_sessions.js';

const router = new Hono();

/** Nguồn để chạy Citation Engine: citations agent gửi → fallback nguồn đã chọn trong session */
async function resolveCitationSources(env, uid, session, citations) {
  const provided = parseArray(citations).map(normalizeSource).filter((s) => s.title || s.filename);
  if (provided.length > 0) return provided;

  const ids = parseArray(session.selected_source_ids);
  if (ids.length === 0) return [];

  const files = (await listUserFiles(env, uid, 200)).map(normalizeFileDoc);
  return files
    .filter((f) => ids.includes(f._id) || ids.includes(f.id))
    .map((f) => sourceFromFileDoc(f));
}

function missingUid(c, origin) {
  return withCors(c.json({
    error: 'Thiếu uid',
    detail: 'Agent gọi bằng X-Agent-Secret phải gửi uid (body.uid hoặc ?uid=)',
  }, 400), origin);
}

/**
 * POST /api/chat/sessions/:id/agent-reply
 * Body: {uid, job_id, message_id, content, citations[], citation_style?, model?}
 * → {message_id, session_id, citation_style, reference_block, citations_count}
 */
router.post('/:id/agent-reply', requireAgentAuth(async (c) => {
  const sessionId = c.req.param('id');
  const origin = c.req.header('Origin') || '';

  try {
    const body = await c.req.json();
    const uid = resolveTargetUid(c, body.uid, c.req.query('uid'));
    if (!uid) return missingUid(c, origin);

    const content = String(body.content || '').trim();
    if (!content) {
      return withCors(c.json({ error: 'content là bắt buộc' }, 400), origin);
    }

    const session = await getOwnedSession(c.env, uid, sessionId);
    if (!session) {
      return withCors(c.json({ error: 'Phiên chat không tìm thấy' }, 404), origin);
    }

    // ── Citation Engine (§3.3) ──
    const sources = await resolveCitationSources(c.env, uid, session, body.citations);
    const formatted = formatReferences(sources, body.citation_style || 'auto');

    const now = new Date().toISOString();
    const jobId = body.job_id || '';
    const promptMsg = await getMessage(c.env, uid, sessionId, body.message_id);

    // Idempotent: gửi lại cùng message_id cho tin nhắn assistant → ghi đè, không tạo trùng
    const isRetry = promptMsg?.role === 'assistant';
    const assistantId = isRetry ? body.message_id : crypto.randomUUID();

    await firestoreSet(c.env, `users/${uid}/chat_sessions/${sessionId}/messages/${assistantId}`, {
      id: assistantId,
      session_id: sessionId,
      role: 'assistant',
      content,
      citations: JSON.stringify(sources),
      citation_style: formatted.style,
      reference_block: formatted.reference_block,
      model: body.model || 'notebooklm',
      nlm_job_id: jobId,
      status: 'done',
      error: '',
      created_at: isRetry ? (promptMsg.created_at || now) : now,
    });

    // Đánh dấu tin nhắn prompt đã được trả lời
    if (promptMsg && promptMsg.role === 'user') {
      await firestoreSet(c.env, `users/${uid}/chat_sessions/${sessionId}/messages/${body.message_id}`, {
        status: 'done',
        nlm_job_id: jobId,
      });
    }

    await touchSession(c.env, uid, sessionId, {
      message_count: (parseInt(session.message_count || 0, 10) || 0) + (isRetry ? 0 : 1),
      orphan_warning: false,
      orphan_note: '',
    });

    return withCors(c.json({
      message_id: assistantId,
      session_id: sessionId,
      citation_style: formatted.style,
      reference_block: formatted.reference_block,
      citations_count: sources.length,
    }), origin);
  } catch (err) {
    console.error('Agent reply error:', err);
    return withCors(c.json({ error: 'Lưu câu trả lời của agent thất bại', detail: err.message }, 500), origin);
  }
}));

/**
 * POST /api/chat/sessions/:id/agent-fail
 * Body: {uid, job_id, message_id, error} → đánh dấu message 'failed' (Orphan Data / lỗi CLI).
 */
router.post('/:id/agent-fail', requireAgentAuth(async (c) => {
  const sessionId = c.req.param('id');
  const origin = c.req.header('Origin') || '';

  try {
    const body = await c.req.json();
    const uid = resolveTargetUid(c, body.uid, c.req.query('uid'));
    if (!uid) return missingUid(c, origin);

    const session = await getOwnedSession(c.env, uid, sessionId);
    if (!session) {
      return withCors(c.json({ error: 'Phiên chat không tìm thấy' }, 404), origin);
    }

    const errMsg = String(body.error || 'Lỗi không xác định từ NotebookLM CLI');
    const jobId = body.job_id || '';
    const now = new Date().toISOString();
    const existing = await getMessage(c.env, uid, sessionId, body.message_id);

    let failedId = body.message_id;
    if (existing) {
      await firestoreSet(c.env, `users/${uid}/chat_sessions/${sessionId}/messages/${body.message_id}`, {
        status: 'failed',
        error: errMsg,
        nlm_job_id: jobId || existing.nlm_job_id || '',
      });
    } else {
      // Không tìm thấy message → tạo message 'system' để lỗi không bị mất dấu (Orphan Data)
      failedId = body.message_id || crypto.randomUUID();
      await firestoreSet(c.env, `users/${uid}/chat_sessions/${sessionId}/messages/${failedId}`, {
        id: failedId,
        session_id: sessionId,
        role: 'system',
        content: `⚠️ Không thể trả lời: ${errMsg}`,
        citations: '[]',
        citation_style: 'none',
        reference_block: '',
        model: '',
        nlm_job_id: jobId,
        status: 'failed',
        error: errMsg,
        created_at: now,
      });
    }

    await touchSession(c.env, uid, sessionId, {
      orphan_warning: true,
      orphan_note: errMsg,
    });

    return withCors(c.json({
      status: 'failed',
      message_id: failedId,
      session_id: sessionId,
      error: errMsg,
    }), origin);
  } catch (err) {
    console.error('Agent fail error:', err);
    return withCors(c.json({ error: 'Ghi nhận lỗi agent thất bại', detail: err.message }, 500), origin);
  }
}));

export default router;
