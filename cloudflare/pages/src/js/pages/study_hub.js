// cloudflare/pages/src/js/pages/study_hub.js — AI Study Hub page (<250 lines)
import { insightsApi, coursesApi, chatApi } from '../api.js';
import { showToast, onTabActivate } from '../app.js';
import { renderQuizPlayer } from '../components/quiz_player.js';

const INSIGHT_TYPE_META = {
  quiz:    { icon: '🎯', label: 'Quiz', color: '#A855F7' },
  summary: { icon: '📝', label: 'Tóm tắt', color: '#22C55E' },
  outline: { icon: '📋', label: 'Đề cương', color: '#3B82F6' },
  qa:      { icon: '💬', label: 'Hỏi đáp', color: '#F59E0B' },
};

/** Dữ liệu citations thực tế gồm nhiều dạng: chuẩn {source,page,quote},
 *  NotebookLM raw {text:"3: <uuid>"}, hoặc {source:"<uuid>"} — chuẩn hoá 1 chỗ. */
function formatCitation(c, idx) {
  if (typeof c === 'string') return escapeHtml(c);
  if (c && typeof c === 'object') {
    if (c.text) return escapeHtml(String(c.text));                       // raw NLM "3: <uuid>"
    const name = c.source_name || c.title || c.filename || '';
    const rawSource = c.source || c.source_id || '';
    const isUuid = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}/i.test(rawSource);
    const label = name || (isUuid ? `Nguồn ${idx + 1}` : rawSource) || `Nguồn ${idx + 1}`;
    const page = c.page ? ` — trang ${c.page}` : '';
    const quote = c.quote ? `: "${escapeHtml(c.quote)}"` : '';
    return `${escapeHtml(label)}${page}${quote}`;
  }
  return `Nguồn ${idx + 1}`;
}

/** Render thẻ insight thường (summary / outline / qa) */
function renderInsightCard(insight) {
  const meta = INSIGHT_TYPE_META[insight.insight_type] || { icon: '📌', label: insight.insight_type };
  let citations = Array.isArray(insight.citations) ? insight.citations : [];
  // Gộp các trích dẫn trùng nhau (NLM thường lặp 1 source nhiều lần)
  citations = [...new Set(citations.map((c) => JSON.stringify(c)))].map((s) => JSON.parse(s));
  const citationHtml = citations.length > 0 ? `
    <div class="citations-drawer" id="cit-${insight.id}">
      <button class="citations-toggle" onclick="toggleCitations('${insight.id}')">
        📎 Trích dẫn nguồn (${citations.length} dẫn chứng) ▸
      </button>
      <div class="citations-list" id="cit-list-${insight.id}">
        ${citations.map((c, i) => `<div>• ${formatCitation(c, i)}</div>`).join('')}
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

async function loadCourseSelect() {
  const select = document.getElementById('quick-research-course');
  if (!select) return;
  try {
    const data = await coursesApi.list();
    const courses = (data.courses || []).filter((c) => c.kind === 'subject');
    select.innerHTML = '<option value="">-- Chọn môn học --</option>' +
      courses.map((c) => {
        const id = c.id || c._id;
        const tag = c.notebook_id ? ' (✓ NLM)' : '';
        return `<option value="${id}">${escapeHtml(c.name || c.folder_name)}${tag}</option>`;
      }).join('');
    // Ưu tiên chọn môn toàn cục hoặc môn đã liên kết NotebookLM nếu chưa chọn gì
    if (window._activeCourseId) {
      select.value = window._activeCourseId;
    } else if (!select.value) {
      const linked = courses.find((c) => c.notebook_id);
      if (linked) select.value = linked.id || linked._id;
    }
  } catch (err) {
    console.warn('Lỗi tải danh sách môn học cho Quick Research:', err);
  }
}

async function quickResearch() {
  const questionEl = document.getElementById('quick-research-input');
  const courseEl = document.getElementById('quick-research-course');
  const resultEl = document.getElementById('quick-research-result');
  if (!questionEl || !resultEl) return;

  const question = questionEl.value.trim();
  if (!question) {
    showToast('Nhập câu hỏi trước!', 'error');
    return;
  }

  if (courseEl && !courseEl.value && window._activeCourseId) {
    courseEl.value = window._activeCourseId;
  }
  const courseId = courseEl?.value || window._activeCourseId || '';
  if (!courseId) {
    showToast('Vui lòng chọn môn học đã liên kết NotebookLM!', 'warning');
    return;
  }

  const selectedText = courseEl.options[courseEl.selectedIndex]?.text || '';
  if (selectedText && !selectedText.includes('(✓ NLM)')) {
    showToast('Môn học này chưa liên kết NotebookLM (notebooklm_id trống)', 'warning');
  }

  resultEl.innerHTML = `
    <div style="background:var(--bg-elevated); border:1px solid var(--border); border-radius:var(--r-sm); padding:12px">
      <div class="flex items-center gap-2 text-muted" id="qr-status">
        <div class="loading-spinner"></div>
        <span>Đang gửi câu hỏi tới NotebookLM...</span>
      </div>
    </div>`;

  try {
    // 1. Tạo phiên chat Quick Research
    const sessionRes = await chatApi.createSession({
      course_id: courseId,
      title: `⚡ Quick: ${question.slice(0, 45)}`,
    });
    const sessionId = sessionRes.id || sessionRes._id;

    if (sessionRes.orphan_warning) {
      resultEl.innerHTML = `<div class="text-danger" style="margin-top:8px">⚠️ Môn học này chưa có NotebookLM liên kết. Vui lòng chọn môn khác hoặc cập nhật NotebookLM ID.</div>`;
      return;
    }

    const statusEl = document.getElementById('qr-status');
    if (statusEl) {
      statusEl.innerHTML = `<div class="loading-spinner"></div> <span>Đang xếp hàng câu hỏi vào nlm_task_queue...</span>`;
    }

    // 2. Gửi câu hỏi vào pipeline chat (enqueue action 'chat_query')
    const sendRes = await chatApi.sendMessage(sessionId, {
      content: question,
      citation_style: 'auto',
    });

    const promptMsgId = sendRes.message_id;
    let pollCount = 0;
    const maxPolls = 60; // 60 x 2s = 120s

    const pollInterval = setInterval(async () => {
      pollCount++;
      if (statusEl) {
        statusEl.innerHTML = `<div class="loading-spinner"></div> <span>NotebookLM đang xử lý câu trả lời... (${pollCount * 2}s)</span>`;
      }

      try {
        const { messages } = await chatApi.getMessages(sessionId);
        const assistantMsg = (messages || []).find((m) => m.role === 'assistant');
        const userMsg = (messages || []).find((m) => m.id === promptMsgId);

        if (assistantMsg) {
          clearInterval(pollInterval);

          let citations = Array.isArray(assistantMsg.citations) ? assistantMsg.citations : [];
          citations = [...new Set(citations.map((c) => JSON.stringify(c)))].map((s) => JSON.parse(s));

          const citHtml = citations.length > 0 ? `
            <div class="citations-drawer" style="margin-top:10px">
              <button class="citations-toggle" onclick="this.nextElementSibling.classList.toggle('open')">
                📎 ${citations.length} nguồn dẫn chứng ▸
              </button>
              <div class="citations-list">
                ${citations.map((c, i) => `<div>• ${formatCitation(c, i)}</div>`).join('')}
              </div>
            </div>` : '';

          const refHtml = assistantMsg.reference_block ? `
            <div style="margin-top:8px; font-size:0.8rem; color:var(--text-muted); border-top:1px solid var(--border); padding-top:6px; white-space:pre-line">
              ${escapeHtml(assistantMsg.reference_block)}
            </div>` : '';

          resultEl.innerHTML = `
            <div style="background:var(--bg-elevated); border:1px solid var(--border); border-radius:var(--r-sm); padding:16px">
              <div class="flex items-center gap-2" style="justify-content:space-between; margin-bottom:8px">
                <span class="badge badge-synced" style="background:#22C55E22; color:#22C55E; border-color:#22C55E">✓ Trả lời từ NotebookLM</span>
                <span class="text-muted" style="font-size:0.75rem">${escapeHtml(selectedText.replace(' (✓ NLM)', ''))}</span>
              </div>
              <div style="font-size:0.9rem; line-height:1.6; white-space:pre-line; color:var(--text)">${escapeHtml(assistantMsg.content)}</div>
              ${citHtml}
              ${refHtml}
              <div style="margin-top:12px; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px">
                <span class="text-success" style="font-size:0.8rem">✓ Đã lưu câu trả lời vào AI Study Hub</span>
                <button class="btn btn-ghost btn-sm" onclick="if(window.activateTab){window.activateTab('chat');}">Mở trong Chat AI →</button>
              </div>
            </div>`;

          // Lưu tự động vào AI Insights
          try {
            await insightsApi.create({
              course_id: courseId,
              insight_type: 'qa',
              title: question.slice(0, 80),
              content: assistantMsg.content,
              citations,
              created_by: 'agent',
            });
            loadInsights();
          } catch (saveErr) {
            console.warn('Lưu insight tự động:', saveErr);
          }

        } else if (userMsg?.status === 'failed') {
          clearInterval(pollInterval);
          resultEl.innerHTML = `<div class="text-danger" style="margin-top:8px">✗ NotebookLM không thể trả lời: ${escapeHtml(userMsg.error || 'Lỗi không xác định')}</div>`;
        } else if (pollCount >= maxPolls) {
          clearInterval(pollInterval);
          resultEl.innerHTML = `
            <div class="text-warning" style="margin-top:8px">
              ⏳ Tác vụ đang mất nhiều thời gian hơn bình thường. Bạn có thể mở tab <strong>💬 Chat AI</strong> để kiểm tra kết quả khi hoàn tất.
            </div>`;
        }
      } catch (pollErr) {
        console.warn('Quick research poll error:', pollErr);
      }
    }, 2000);

  } catch (err) {
    resultEl.innerHTML = `<div class="text-danger" style="margin-top:8px">Lỗi: ${escapeHtml(err.message)}</div>`;
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

function triggerStudioQuickAction(promptText) {
  if (window.activateTab) window.activateTab('study-hub');
  const courseSel = document.getElementById('quick-research-course');
  if (courseSel && window._activeCourseId) {
    courseSel.value = window._activeCourseId;
  }
  const input = document.getElementById('quick-research-input');
  if (input) {
    input.value = promptText;
    input.focus();
  }
  quickResearch();
}

export function initStudyHub() {
  loadInsights();
  loadCourseSelect();
  onTabActivate('study-hub', () => {
    loadInsights();
    loadCourseSelect();
  });
  const sendBtn = document.getElementById('btn-quick-research');
  if (sendBtn) sendBtn.addEventListener('click', quickResearch);
  const input = document.getElementById('quick-research-input');
  if (input) input.addEventListener('keydown', (e) => { if (e.key === 'Enter') quickResearch(); });

  // Gắn sự kiện cho các nút hành động nhanh ở Cột Studio
  document.getElementById('studio-action-quiz')?.addEventListener('click', () => {
    triggerStudioQuickAction('Tạo bộ 5 câu hỏi trắc nghiệm ôn tập kèm đáp án giải thích chi tiết dựa trên các tài liệu đã nạp');
  });
  document.getElementById('studio-action-summary')?.addEventListener('click', () => {
    triggerStudioQuickAction('Tóm tắt tổng quan những nội dung cốt lõi và bài học trọng tâm từ các tài liệu môn học này');
  });
  document.getElementById('studio-action-outline')?.addEventListener('click', () => {
    triggerStudioQuickAction('Lập đề cương ôn thi chi tiết từng chủ đề và các câu hỏi trọng tâm thường gặp trong đề thi');
  });
  document.getElementById('studio-action-slides')?.addEventListener('click', () => {
    if (window.activateTab) window.activateTab('artifacts');
    showToast('Chuyển sang kho Slide thuyết trình & Xuất bản', 'info');
  });
}
