// cloudflare/pages/src/js/realtime.js — Realtime chat messages (<120 lines)
// Ưu tiên Firestore onSnapshot khi có window.__FIREBASE_CONFIG; LUÔN fallback polling 3s.
import { chatApi } from './api.js';

const POLL_INTERVAL_MS = 3000;
const FIREBASE_SDK_VER = '10.12.2';

/**
 * Subscribe messages mới của 1 chat session.
 * @param {string} sessionId
 * @param {Object}   opts
 * @param {Function} opts.onMessages - (messages: Array) => void — mảng message mới (đã parse citations)
 * @param {Function} [opts.onError]  - (err) => void
 * @returns {Function} unsubscribe — gọi để dừng realtime/polling
 */
export function subscribeMessages(sessionId, { onMessages, onError } = {}) {
  let stopped = false;
  let pollTimer = null;
  let firestoreUnsub = null;
  let since = ''; // ISO timestamp lần poll gần nhất

  function parseMessage(m) {
    let citations = m.citations;
    if (typeof citations === 'string') {
      try { citations = JSON.parse(citations); } catch { citations = []; }
    }
    return { ...m, citations: Array.isArray(citations) ? citations : [] };
  }

  // ---------- Polling fallback (luôn sẵn sàng) ----------
  async function pollOnce() {
    try {
      const data = await chatApi.getMessages(sessionId, since);
      if (data.server_time) since = data.server_time;
      const msgs = (data.messages || []).map(parseMessage);
      if (msgs.length) onMessages?.(msgs);
    } catch (err) {
      onError?.(err);
    }
  }

  function startPolling() {
    if (pollTimer || stopped) return;
    pollOnce();
    pollTimer = setInterval(() => { if (!stopped) pollOnce(); }, POLL_INTERVAL_MS);
  }

  // ---------- Firestore onSnapshot (nếu client có config) ----------
  async function tryFirestore() {
    const config = window.__FIREBASE_CONFIG;
    if (!config) return false;
    try {
      const base = `https://www.gstatic.com/firebasejs/${FIREBASE_SDK_VER}`;
      const [{ initializeApp }, fstore] = await Promise.all([
        import(`${base}/firebase-app.js`),
        import(`${base}/firebase-firestore.js`),
      ]);
      const user = JSON.parse(localStorage.getItem('ths_user_data') || '{}');
      const uid = user.uid || user.id;
      if (!uid) return false;

      const app = initializeApp(config);
      const db = fstore.getFirestore(app);
      const colRef = fstore.collection(db, 'users', uid, 'chat_sessions', sessionId, 'messages');
      const q = fstore.query(colRef, fstore.orderBy('created_at', 'asc'));

      firestoreUnsub = fstore.onSnapshot(q, (snap) => {
        const msgs = [];
        snap.docChanges().forEach((ch) => {
          if (ch.type === 'added' || ch.type === 'modified') {
            msgs.push(parseMessage({ id: ch.doc.id, ...ch.doc.data() }));
          }
        });
        if (msgs.length) onMessages?.(msgs);
      }, (err) => {
        // Lỗi snapshot → fallback polling
        console.warn('[realtime] onSnapshot lỗi, fallback polling:', err.message);
        firestoreUnsub?.();
        firestoreUnsub = null;
        startPolling();
      });
      return true;
    } catch (err) {
      console.warn('[realtime] Không khởi tạo được Firestore, fallback polling:', err.message);
      return false;
    }
  }

  // ---------- Khởi động ----------
  (async () => {
    const ok = await tryFirestore();
    if (!ok && !stopped) startPolling();
  })();

  return function unsubscribe() {
    stopped = true;
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    if (firestoreUnsub) { firestoreUnsub(); firestoreUnsub = null; }
  };
}
