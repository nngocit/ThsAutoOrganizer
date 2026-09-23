// cloudflare/pages/src/js/pages/study_hub.js — AI Study Hub page (<200 lines)
import { insightsApi, coursesApi } from '../api.js';
import { showToast } from '../app.js';
import { renderQuizPlayer } from '../components/quiz_player.js';

const INSIGHT_TYPE_META = {
  quiz:    { icon: '🎯', label: 'Quiz', color: '#A855F7' },
  summary: { icon: '📝', label: 'Tóm tắt', color: '#22C55E' },
  outline: { icon: '📋', label: 'Đề cương', color: '#3B82F6' },
  qa:      { icon: '💬', label: 'Hỏi đáp', color: '#F59E0B' },
};

/** Render thẻ insight thường (summary / outline / qa) */
function renderInsightCard(insight) {
  const meta = INSIGHT_TYPE_META[insight.insight_type] || { icon: '📌', label: insight.insight_type };
  const citations = Array.isArray(insight.citations) ? insight.citations : [];
  const citationHtml = citations.length > 0 ? `
    <div class="citations-drawer" id="cit-${insight.id}">
      <button class="citations-toggle" onclick="toggleCitations('${insight.id}')">
        📎 Trích dẫn nguồn (${citations.length} dẫn chứng) ▸
      </button>
      <div class="citations-list" id="cit-list-${insight.id}">
        ${citations.map((c) => `<div>• ${c.source || ''} trang ${c.page || ''}: "${c.quote || ''}"</div>`).join('')}
      </div>
    </div>` : '';

  return `
    <div class="card" id="insight-${insight.id}">
      <div style="display:flex; justify-content:space-between; align-items:flex-start; margin-bottom:12px">
        <div>
          <span class="badge badge-synced" style="background:${meta.color}22; color:${meta.color}; border-color:${meta.color}">
            ${meta.icon} ${meta.label}
          </span>
          <div style="font-weight:600; margin-top:8px">${escapeHtml(insight.title)}</div>
        </div>
        <button class="btn btn-danger btn-sm" onclick="deleteInsight('${insight.id}')">✕</button>
      </div>
      <div style="color:var(--text-muted); font-size:0.875rem; white-space:pre-line; margin-bottom:12px">
        ${escapeHtml(insight.content).slice(0, 500)}${insight.content.length > 500 ? '…' : ''}
      </div>
      ${citationHtml}
    </div>
  `;
}

function escapeHtml(str) {
  return (str || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

async function loadInsights(filters = {}) {
  const grid = document.getElementById('insights-grid');
  if (!grid) return;
  grid.innerHTML = '<div class="text-muted">Đang tải AI Study Hub...</div>';
  try {
    const { insights } = await insightsApi.list(filters);
    if (!insights.length) {
      grid.innerHTML = '<div class="text-muted">Chưa có insights. Hãy tạo quiz hoặc tóm tắt từ AntiGravity Chat!</div>';
      return;
    }

    const quizCards = insights.filter((i) => i.insight_type === 'quiz');
    const otherCards = insights.filter((i) => i.insight_type !== 'quiz');

    let html = '';
    if (otherCards.length) {
      html += `<div class="card-grid">${otherCards.map(renderInsightCard).join('')}</div>`;
    }
    if (quizCards.length) {
      html += `<div style="margin-top:24px"><h3 style="margin-bottom:16px">🎯 Quiz để luyện tập</h3>
               <div class="card-grid">${quizCards.map(renderQuizCard).join('')}</div></div>`;
    }
    grid.innerHTML = html;
  } catch (err) {
    grid.innerHTML = `<div class="text-danger">Lỗi: ${err.message}</div>`;
  }
}

function renderQuizCard(insight) {
  let questions = [];
  try { questions = JSON.parse(insight.content); } catch { questions = []; }
  if (!Array.isArray(questions) || !questions.length) return renderInsightCard(insight);

  return `
    <div class="card">
      <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px">
        <div>
          <span class="badge badge-processing">🎯 Quiz — ${questions.length} câu</span>
          <div style="font-weight:600; margin-top:8px">${escapeHtml(insight.title)}</div>
        </div>
        <button class="btn btn-danger btn-sm" onclick="deleteInsight('${insight.id}')">✕</button>
      </div>
      <div id="quiz-player-${insight.id}"></div>
    </div>
  `;
}

async function initQuizPlayers(insights) {
  for (const ins of insights) {
    if (ins.insight_type !== 'quiz') continue;
    const container = document.getElementById(`quiz-player-${ins.id}`);
    if (container) {
      let questions = [];
      try { questions = JSON.parse(ins.content); } catch {}
      renderQuizPlayer(container, questions);
    }
  }
}

async function quickResearch() {
  const questionEl = document.getElementById('quick-research-input');
  const courseEl = document.getElementById('quick-research-course');
  const resultEl = document.getElementById('quick-research-result');
  if (!questionEl || !resultEl) return;

  const question = questionEl.value.trim();
  if (!question) { showToast('Nhập câu hỏi trước!', 'error'); return; }

  resultEl.innerHTML = '<div class="flex items-center gap-2"><div class="loading-spinner"></div> Đang tra cứu...</div>';
  // Gửi câu hỏi tới AI Insights API (backend có thể gọi NotebookLM MCP)
  try {
    const data = await insightsApi.create({
      course_id: courseEl?.value || '',
      insight_type: 'qa',
      title: question.slice(0, 80),
      content: question,
      created_by: 'web_user',
    });
    resultEl.innerHTML = `<div class="text-success">✓ Đã lưu vào Hub! ID: ${data.id}</div>`;
    loadInsights();
  } catch (err) {
    resultEl.innerHTML = `<div class="text-danger">Lỗi: ${err.message}</div>`;
  }
}

window.deleteInsight = async (id) => {
  if (!confirm('Xóa insight này?')) return;
  try {
    await insightsApi.delete(id);
    document.getElementById(`insight-${id}`)?.remove();
    showToast('Đã xóa insight', 'success');
  } catch (err) {
    showToast(`Xóa thất bại: ${err.message}`, 'error');
  }
};

window.toggleCitations = (id) => {
  document.getElementById(`cit-list-${id}`)?.classList.toggle('open');
};

export function initStudyHub() {
  loadInsights();
  const sendBtn = document.getElementById('btn-quick-research');
  if (sendBtn) sendBtn.addEventListener('click', quickResearch);
  const input = document.getElementById('quick-research-input');
  if (input) input.addEventListener('keydown', (e) => { if (e.key === 'Enter') quickResearch(); });
}
