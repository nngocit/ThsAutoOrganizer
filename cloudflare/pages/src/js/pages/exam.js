// cloudflare/pages/src/js/pages/exam.js — Trạm Ôn thi: tạo đề 50 flashcard + 5 tự luận, cày quiz, lưu điểm (<250 dòng)
import { examApi, coursesApi } from '../api.js';
import { showToast, onTabActivate } from '../app.js';

let _courses = [];
let _practice = null; // { setId, cards, essays, idx, score, answers }

function esc(s) {
  return (s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function parseJsonArray(v) {
  if (typeof v === 'string') { try { return JSON.parse(v); } catch { return []; } }
  return Array.isArray(v) ? v : [];
}

// ---------- Shell ----------
function renderShell() {
  const root = document.getElementById('exam-root');
  if (!root || root.dataset.ready) return;
  root.dataset.ready = '1';
  root.innerHTML = `
    <div class="card" style="margin-bottom:16px">
      <div style="font-weight:600; margin-bottom:12px">📝 Tạo đề ôn thi mới</div>
      <div class="flex gap-2" style="flex-wrap:wrap; align-items:center">
        <select id="exam-course" class="btn btn-ghost btn-sm" style="min-width:180px"></select>
        <span class="text-muted" style="font-size:0.82rem">50 flashcard + 5 câu tự luận (AI tạo qua NotebookLM — mất vài phút)</span>
        <button class="btn btn-primary btn-sm" id="btn-gen-exam">⚡ Tạo đề</button>
        <button class="btn btn-ghost btn-sm" id="btn-refresh-exam">🔄 Làm mới</button>
      </div>
    </div>
    <div id="exam-practice" style="margin-bottom:16px"></div>
    <div id="exam-sets"></div>`;
  document.getElementById('btn-gen-exam').addEventListener('click', generateExam);
  document.getElementById('btn-refresh-exam').addEventListener('click', loadSets);
}

async function loadCourses() {
  const sel = document.getElementById('exam-course');
  if (!sel || sel.options.length) return;
  try {
    const data = await coursesApi.list();
    _courses = data.courses || [];
    sel.innerHTML = _courses.length
      ? _courses.map((c) => `<option value="${c.id}">${esc(c.name || c.subject || c.id)}</option>`).join('')
      : '<option value="">(Chưa có môn học)</option>';
  } catch {
    sel.innerHTML = '<option value="">(Lỗi tải môn học)</option>';
  }
}

async function generateExam() {
  const courseId = document.getElementById('exam-course')?.value;
  if (!courseId) { showToast('Chọn môn học trước', 'error'); return; }
  try {
    const { job_id } = await examApi.generate({ course_id: courseId, flashcard_count: 50, essay_count: 5 });
    showToast(`⚡ Đã xếp hàng tạo đề (job ${job_id}). Agent sẽ xử lý — bấm 🔄 Làm mới sau vài phút.`, 'success', 6000);
  } catch (err) { showToast(`Tạo đề thất bại: ${err.message}`, 'error'); }
}

// ---------- Set list ----------
function renderSetCard(set) {
  return `
    <div class="card">
      <div class="flex items-center gap-2" style="justify-content:space-between; flex-wrap:wrap">
        <div>
          <div style="font-weight:600">${esc(set.title) || 'Đề ôn thi'}</div>
          <div class="text-muted" style="font-size:0.8rem">
            🃏 ${set.flashcard_count ?? 0} flashcard · ✍️ ${set.essay_count ?? 0} tự luận
          </div>
        </div>
        <div class="flex gap-2">
          <button class="btn btn-primary btn-sm btn-practice" data-id="${set.id}">▶ Cày quiz</button>
          <button class="btn btn-danger btn-sm btn-del-set" data-id="${set.id}">🗑</button>
        </div>
      </div>
    </div>`;
}

async function loadSets() {
  const root = document.getElementById('exam-sets');
  if (!root) return;
  root.innerHTML = '<div class="text-muted">Đang tải đề ôn thi...</div>';
  try {
    const { sets } = await examApi.list();
    root.innerHTML = (sets && sets.length)
      ? `<div class="card-grid">${sets.map(renderSetCard).join('')}</div>`
      : '<div class="text-muted">Chưa có đề nào. Tạo đề đầu tiên ở trên!</div>';
    root.querySelectorAll('.btn-practice').forEach((b) =>
      b.addEventListener('click', () => startPractice(b.dataset.id)));
    root.querySelectorAll('.btn-del-set').forEach((b) =>
      b.addEventListener('click', () => deleteSet(b.dataset.id)));
  } catch (err) {
    root.innerHTML = `<div class="text-danger">Lỗi: ${esc(err.message)}</div>`;
  }
}

async function deleteSet(id) {
  if (!confirm('Xoá đề ôn thi này?')) return;
  try {
    await examApi.delete(id);
    showToast('Đã xoá đề', 'success');
    document.getElementById('exam-practice').innerHTML = '';
    loadSets();
  } catch (err) { showToast(`Xoá thất bại: ${err.message}`, 'error'); }
}

// ---------- Practice (cày quiz) ----------
async function startPractice(setId) {
  const box = document.getElementById('exam-practice');
  box.innerHTML = '<div class="card"><div class="text-muted">Đang tải đề...</div></div>';
  try {
    const { set } = await examApi.get(setId);
    const cards = parseJsonArray(set.flashcards);
    const essays = parseJsonArray(set.essays);
    if (!cards.length && !essays.length) {
      box.innerHTML = '<div class="card"><div class="text-warning">Đề chưa có câu hỏi (agent có thể đang tạo).</div></div>';
      return;
    }
    _practice = { setId, cards, essays, idx: 0, score: 0, flipped: false };
    renderPracticeCard();
    box.scrollIntoView({ behavior: 'smooth' });
  } catch (err) {
    box.innerHTML = `<div class="card"><div class="text-danger">Lỗi tải đề: ${esc(err.message)}</div></div>`;
  }
}

function renderPracticeCard() {
  const box = document.getElementById('exam-practice');
  const p = _practice;
  if (p.idx >= p.cards.length) { finishPractice(); return; }
  const card = p.cards[p.idx];
  box.innerHTML = `
    <div class="card" style="border-color:var(--accent)">
      <div class="flex items-center gap-2" style="justify-content:space-between; margin-bottom:12px">
        <span class="badge badge-processing">🃏 Flashcard ${p.idx + 1}/${p.cards.length}</span>
        <span class="text-muted" style="font-size:0.82rem">Đúng: ${p.score}</span>
      </div>
      <div style="font-weight:600; line-height:1.5; margin-bottom:12px">${esc(card.q)}</div>
      <div id="card-answer" class="${p.flipped ? '' : 'hidden'}"
           style="background:var(--bg-elevated); border-radius:var(--r-sm); padding:12px; margin-bottom:12px">
        <div style="font-size:0.875rem; white-space:pre-line">${esc(card.a || '—')}</div>
        ${card.ref ? `<div class="text-muted" style="font-size:0.75rem; margin-top:6px">📎 ${esc(card.ref)}</div>` : ''}
      </div>
      <div class="flex gap-2">
        ${p.flipped
          ? `<button class="btn btn-primary btn-sm" id="btn-correct">✔ Đúng</button>
             <button class="btn btn-danger btn-sm" id="btn-wrong">✘ Sai</button>`
          : `<button class="btn btn-primary btn-sm" id="btn-flip">👁 Lật thẻ</button>`}
        <button class="btn btn-ghost btn-sm" id="btn-quit-practice">Thoát</button>
      </div>
    </div>`;
  box.querySelector('#btn-flip')?.addEventListener('click', () => { p.flipped = true; renderPracticeCard(); });
  box.querySelector('#btn-correct')?.addEventListener('click', () => nextCard(true));
  box.querySelector('#btn-wrong')?.addEventListener('click', () => nextCard(false));
  box.querySelector('#btn-quit-practice')?.addEventListener('click', () => {
    _practice = null; box.innerHTML = '';
  });
}

function nextCard(correct) {
  if (correct) _practice.score++;
  _practice.idx++;
  _practice.flipped = false;
  renderPracticeCard();
}

async function finishPractice() {
  const box = document.getElementById('exam-practice');
  const p = _practice;
  const total = p.cards.length;
  const pct = total ? Math.round((p.score / total) * 100) : 0;
  const essayHtml = p.essays.length ? `
    <div style="margin-top:16px">
      <div style="font-weight:600; margin-bottom:8px">✍️ Câu hỏi tự luận (${p.essays.length})</div>
      ${p.essays.map((e2, i) => `
        <div style="background:var(--bg-elevated); border-radius:var(--r-sm); padding:10px; margin-bottom:8px">
          <div style="font-size:0.875rem; font-weight:500">${i + 1}. ${esc(e2.q)}</div>
          ${e2.hint ? `<div class="text-muted" style="font-size:0.78rem; margin-top:4px">💡 Gợi ý: ${esc(e2.hint)}</div>` : ''}
          ${e2.ref ? `<div class="text-muted" style="font-size:0.72rem">📎 ${esc(e2.ref)}</div>` : ''}
        </div>`).join('')}
    </div>` : '';
  box.innerHTML = `
    <div class="card" style="text-align:center">
      <div style="font-size:2.5rem; font-weight:800; color:var(--accent)">${pct}%</div>
      <div style="margin-top:4px">${p.score}/${total} flashcard đúng</div>
      ${essayHtml}
      <div class="flex gap-2 mt-4" style="justify-content:center">
        <button class="btn btn-primary btn-sm" id="btn-retry-practice">🔄 Cày lại</button>
        <button class="btn btn-ghost btn-sm" id="btn-close-practice">Đóng</button>
      </div>
      <div class="text-muted" style="font-size:0.75rem; margin-top:8px" id="attempt-status">Đang lưu điểm...</div>
    </div>`;
  box.querySelector('#btn-retry-practice').addEventListener('click', () => startPractice(p.setId));
  box.querySelector('#btn-close-practice').addEventListener('click', () => { _practice = null; box.innerHTML = ''; });
  // Lưu điểm qua POST attempt
  try {
    await examApi.saveAttempt(p.setId, { score: p.score, total });
    box.querySelector('#attempt-status').textContent = '✓ Đã lưu điểm';
  } catch (err) {
    box.querySelector('#attempt-status').textContent = `⚠ Lưu điểm thất bại: ${err.message}`;
  }
  _practice = null;
}

export function initExam() {
  onTabActivate('exam', () => { renderShell(); loadCourses(); loadSets(); });
}
