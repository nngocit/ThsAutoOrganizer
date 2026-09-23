// cloudflare/pages/src/js/components/quiz_player.js — Interactive Quiz Player (<200 lines)

const OPTION_LETTERS = ['A', 'B', 'C', 'D', 'E'];

/**
 * Render interactive quiz player vào container.
 * 
 * @param {HTMLElement} container
 * @param {Array<{q: string, options: string[], ans: string, explain?: string}>} questions
 */
export function renderQuizPlayer(container, questions) {
  if (!questions || !questions.length) {
    container.innerHTML = '<div class="text-muted">Quiz không có câu hỏi hợp lệ.</div>';
    return;
  }

  const state = {
    current: 0,
    score: 0,
    answered: new Array(questions.length).fill(null),
    finished: false,
  };

  function renderQuestion(idx) {
    const q = questions[idx];
    if (!q) return '';
    const answered = state.answered[idx];
    const optionsHtml = (q.options || []).map((opt, i) => {
      const letter = OPTION_LETTERS[i] || String(i + 1);
      const isCorrect = letter === q.ans;
      const isChosen = answered === letter;
      let cls = '';
      if (answered !== null) {
        if (isCorrect) cls = 'correct';
        else if (isChosen) cls = 'wrong';
      }
      return `
        <button class="quiz-option ${cls}" 
                data-letter="${letter}"
                data-qidx="${idx}"
                ${answered !== null ? 'disabled' : ''}>
          <span class="quiz-letter">${letter}</span>
          <span>${opt}</span>
        </button>
      `;
    }).join('');

    const showExplain = answered !== null && q.explain;

    return `
      <div class="quiz-question" id="qq-${idx}" data-idx="${idx}">
        <div style="font-size:0.78rem; color:var(--text-muted); margin-bottom:8px">
          Câu ${idx + 1} / ${questions.length}
        </div>
        <div style="font-weight:600; margin-bottom:12px; line-height:1.5">${q.q}</div>
        <div class="quiz-options">${optionsHtml}</div>
        <div class="quiz-explain ${showExplain ? 'visible' : ''}" id="explain-${idx}">
          ${showExplain ? '💡 ' + q.explain : ''}
        </div>
      </div>
    `;
  }

  function renderScoreBoard() {
    const pct = Math.round((state.score / questions.length) * 100);
    const grade = pct >= 80 ? '🎉 Xuất sắc!' : pct >= 60 ? '👍 Khá tốt' : '📚 Ôn lại nhé';
    return `
      <div style="text-align:center; padding:32px 0">
        <div style="font-size:3rem; font-weight:800; color:var(--accent)">${pct}%</div>
        <div style="font-size:1.1rem; margin-top:8px">${grade}</div>
        <div class="text-muted" style="margin-top:4px">${state.score} / ${questions.length} câu đúng</div>
        <button class="btn btn-primary" style="margin-top:20px" id="btn-retry">🔄 Làm lại</button>
      </div>
    `;
  }

  function render() {
    if (state.finished) {
      container.innerHTML = renderScoreBoard();
      container.querySelector('#btn-retry')?.addEventListener('click', reset);
      return;
    }

    const navHtml = `
      <div class="flex gap-2 mt-4" style="justify-content:space-between; align-items:center">
        <button class="btn btn-ghost btn-sm" id="btn-prev" ${state.current === 0 ? 'disabled' : ''}>← Trước</button>
        <span class="text-muted" style="font-size:0.8rem">${state.current + 1}/${questions.length}</span>
        ${state.current === questions.length - 1
          ? `<button class="btn btn-primary btn-sm" id="btn-finish" ${state.answered[state.current] === null ? 'disabled' : ''}>Xem kết quả ✓</button>`
          : `<button class="btn btn-ghost btn-sm" id="btn-next" ${state.answered[state.current] === null ? 'disabled' : ''}>Tiếp →</button>`
        }
      </div>
    `;

    container.innerHTML = renderQuestion(state.current) + navHtml;
    attachQuizHandlers();
  }

  function attachQuizHandlers() {
    // Option click handler
    container.querySelectorAll('.quiz-option').forEach((btn) => {
      btn.addEventListener('click', () => {
        const idx = parseInt(btn.dataset.qidx);
        const letter = btn.dataset.letter;
        if (state.answered[idx] !== null) return;

        state.answered[idx] = letter;
        if (letter === questions[idx].ans) state.score++;

        // Show feedback without full re-render
        container.querySelectorAll(`.quiz-option[data-qidx="${idx}"]`).forEach((b) => {
          b.disabled = true;
          if (b.dataset.letter === questions[idx].ans) b.classList.add('correct');
          else if (b.dataset.letter === letter) b.classList.add('wrong');
        });

        // Show explanation
        const explainEl = container.querySelector(`#explain-${idx}`);
        if (explainEl && questions[idx].explain) {
          explainEl.innerHTML = '💡 ' + questions[idx].explain;
          explainEl.classList.add('visible');
        }

        // Enable next/finish button
        const nextBtn = container.querySelector('#btn-next') || container.querySelector('#btn-finish');
        if (nextBtn) nextBtn.disabled = false;
      });
    });

    container.querySelector('#btn-prev')?.addEventListener('click', () => {
      state.current = Math.max(0, state.current - 1); render();
    });
    container.querySelector('#btn-next')?.addEventListener('click', () => {
      state.current = Math.min(questions.length - 1, state.current + 1); render();
    });
    container.querySelector('#btn-finish')?.addEventListener('click', () => {
      state.finished = true; render();
    });
  }

  function reset() {
    state.current = 0;
    state.score = 0;
    state.answered.fill(null);
    state.finished = false;
    render();
  }

  render();
}
