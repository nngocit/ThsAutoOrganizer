// tests/task_queue_maintenance.test.js — G1 (truy vấn pending phía server) + G2 (hồi phục task kẹt)
// Dùng vi.mock cho tầng Firestore để không cần service account thật.

import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../src/lib/firebase.js', () => ({
  firestoreGet: vi.fn(),
  firestoreSet: vi.fn(async () => ({})),
  firestoreList: vi.fn(async () => ({ documents: [] })),
  getAccessToken: vi.fn(async () => 'test-token'),
  firestoreRestBaseUrl: () => 'https://firestore.test/documents',
  fromFirestoreDoc: (doc) => {
    if (!doc || !doc.fields) return {};
    const out = { _id: (doc.name || '').split('/').pop() };
    for (const [k, v] of Object.entries(doc.fields)) {
      if (v.stringValue !== undefined) out[k] = v.stringValue;
      else if (v.integerValue !== undefined) out[k] = parseInt(v.integerValue, 10);
      else if (v.doubleValue !== undefined) out[k] = v.doubleValue;
      else if (v.booleanValue !== undefined) out[k] = v.booleanValue;
      else out[k] = null;
    }
    if (!out.id) out.id = out._id;
    return out;
  },
}));

vi.mock('../src/lib/firestore_query.js', () => ({
  firestoreRunQuery: vi.fn(async () => []),
}));

import worker from '../src/index.js';
import { firestoreGet, firestoreSet, firestoreList } from '../src/lib/firebase.js';
import { firestoreRunQuery } from '../src/lib/firestore_query.js';
import { recoverStaleTasks } from '../src/cron/task_recovery.js';
import { getTaskFlags, resetTaskFlagCache, taskFlagsFromEnv } from '../src/lib/feature_flags.js';

const BASE_ENV = { AGENT_SECRET: 'test-secret', FIREBASE_SERVICE_ACCOUNT: '{}' };

/** Doc kiểu Firestore cho system_config/default */
const flagDoc = (fields) => ({ name: 'system_config/default', fields });

beforeEach(() => {
  vi.clearAllMocks();
  resetTaskFlagCache();
});

describe('Feature flags — công tắc hàng đợi', () => {
  it('mặc định: query mode bật, recovery bật, ngưỡng 15 phút', () => {
    const flags = taskFlagsFromEnv({});
    expect(flags.queryMode).toBe('query');
    expect(flags.recoveryEnabled).toBe(true);
    expect(flags.staleMinutes).toBe(15);
  });

  it('env có thể ép chế độ legacy / tắt recovery / đổi ngưỡng', () => {
    const flags = taskFlagsFromEnv({
      TASKS_QUERY_MODE: 'legacy',
      TASKS_RECOVERY_ENABLED: 'false',
      TASKS_STALE_MINUTES: '45',
    });
    expect(flags.queryMode).toBe('legacy');
    expect(flags.recoveryEnabled).toBe(false);
    expect(flags.staleMinutes).toBe(45);
  });

  it('Firestore (Web UI) ưu tiên hơn env và có cache 30s', async () => {
    firestoreGet.mockResolvedValue(flagDoc({
      tasks_query_mode: { stringValue: 'legacy' },
      tasks_recovery_enabled: { booleanValue: false },
      tasks_stale_minutes: { integerValue: '30' },
    }));

    const first = await getTaskFlags(BASE_ENV);
    expect(first).toMatchObject({
      queryMode: 'legacy', recoveryEnabled: false, staleMinutes: 30, source: 'firestore',
    });

    await getTaskFlags(BASE_ENV);
    expect(firestoreGet).toHaveBeenCalledTimes(1); // lần 2 lấy từ cache

    resetTaskFlagCache();
    await getTaskFlags(BASE_ENV);
    expect(firestoreGet).toHaveBeenCalledTimes(2);
  });

  it('lỗi đọc Firestore → fallback env, không crash', async () => {
    firestoreGet.mockRejectedValue(new Error('boom'));
    const flags = await getTaskFlags(BASE_ENV);
    expect(flags.queryMode).toBe('query');
  });
});

describe('G1 — GET /api/tasks/:queue', () => {
  it('chế độ query: gọi runQuery và sắp xếp FIFO (không lấy N document đầu)', async () => {
    firestoreGet.mockResolvedValue(null); // không có config → mặc định 'query'
    firestoreRunQuery.mockResolvedValue([
      { id: 'task_new', action: 'source_add', status: 'pending', created_at: '2026-09-25T10:00:00Z' },
      { id: 'task_old', action: 'source_add', status: 'pending', created_at: '2026-09-20T10:00:00Z' },
    ]);

    const res = await worker.fetch(new Request('http://localhost/api/tasks/nlm_task_queue', {
      headers: { 'X-Agent-Secret': 'test-secret' },
    }), BASE_ENV);
    const data = await res.json();

    expect(res.status).toBe(200);
    expect(data.mode).toBe('query');
    expect(data.tasks.map((t) => t.id)).toEqual(['task_old', 'task_new']);
    expect(firestoreRunQuery).toHaveBeenCalledWith(
      BASE_ENV,
      'nlm_task_queue',
      { fieldPath: 'status', value: 'pending', limit: 10 }
    );
    expect(firestoreList).not.toHaveBeenCalled();
  });

  it('chế độ legacy (env): dùng firestoreList rồi lọc pending', async () => {
    firestoreGet.mockResolvedValue(null);
    firestoreList.mockResolvedValue({
      documents: [
        { name: 'nlm_task_queue/a', fields: { id: { stringValue: 'a' }, status: { stringValue: 'pending' } } },
        { name: 'nlm_task_queue/b', fields: { id: { stringValue: 'b' }, status: { stringValue: 'done' } } },
      ],
    });

    const res = await worker.fetch(new Request('http://localhost/api/tasks/nlm_task_queue', {
      headers: { 'X-Agent-Secret': 'test-secret' },
    }), { ...BASE_ENV, TASKS_QUERY_MODE: 'legacy' });
    const data = await res.json();

    expect(data.mode).toBe('legacy');
    expect(data.tasks.map((t) => t.id)).toEqual(['a']);
    expect(firestoreRunQuery).not.toHaveBeenCalled();
  });
});

describe('G2 — recoverStaleTasks', () => {
  it('trả task processing quá ngưỡng về pending, bỏ qua task vừa claim', async () => {
    const now = new Date('2026-09-25T12:00:00Z');
    firestoreGet.mockResolvedValue(null); // recovery mặc định = bật
    firestoreRunQuery.mockResolvedValue([
      { id: 'stale', status: 'processing', processed_at: '2026-09-25T11:30:00Z' },
      { id: 'fresh', status: 'processing', processed_at: '2026-09-25T11:59:30Z' },
    ]);

    const stats = await recoverStaleTasks(BASE_ENV, { now });

    expect(stats.recovered).toBe(2); // 1 task × 2 queue (cùng mock)
    expect(stats.checked).toBe(4);   // 2 task × 2 queue
    expect(firestoreSet).toHaveBeenCalledWith(
      BASE_ENV,
      'nlm_task_queue/stale',
      expect.objectContaining({ status: 'pending', recovered_from: 'processing' })
    );
    const touchedPaths = firestoreSet.mock.calls.map((call) => call[1]);
    expect(touchedPaths).not.toContain('nlm_task_queue/fresh');
    expect(touchedPaths).not.toContain('drive_task_queue/fresh');
  });

  it('task không có mốc thời gian → không hồi phục (tránh hồi phục oan)', async () => {
    firestoreGet.mockResolvedValue(null);
    firestoreRunQuery.mockResolvedValue([{ id: 'no_ts', status: 'processing' }]);

    const stats = await recoverStaleTasks(BASE_ENV);
    expect(stats.recovered).toBe(0);
    expect(firestoreSet).not.toHaveBeenCalled();
  });

  it('tắt bằng công tắc → không làm gì', async () => {
    firestoreGet.mockResolvedValue(flagDoc({ tasks_recovery_enabled: { booleanValue: false } }));

    const stats = await recoverStaleTasks(BASE_ENV);

    expect(stats.enabled).toBe(false);
    expect(firestoreRunQuery).not.toHaveBeenCalled();
    expect(firestoreSet).not.toHaveBeenCalled();
  });

  it('force=true chạy dù công tắc đang tắt', async () => {
    firestoreGet.mockResolvedValue(flagDoc({ tasks_recovery_enabled: { booleanValue: false } }));
    firestoreRunQuery.mockResolvedValue([
      { id: 'stale', status: 'processing', processed_at: '2020-01-01T00:00:00Z' },
    ]);

    const stats = await recoverStaleTasks(BASE_ENV, { force: true });
    expect(stats.enabled).toBe(true);
    expect(stats.recovered).toBe(2);
  });
});

describe('Endpoint bảo trì', () => {
  it('POST /api/tasks/maintenance/recover trả 200 kèm thống kê', async () => {
    firestoreGet.mockResolvedValue(null);

    const res = await worker.fetch(new Request('http://localhost/api/tasks/maintenance/recover?force=true', {
      method: 'POST',
      headers: { 'X-Agent-Secret': 'test-secret' },
    }), BASE_ENV);
    const data = await res.json();

    expect(res.status).toBe(200);
    expect(data.status).toBe('ok');
    expect(data).toHaveProperty('recovered');
  });

  it('GET + PUT /api/settings/task-flags hoạt động', async () => {
    firestoreGet.mockResolvedValue(null);
    firestoreSet.mockResolvedValue({});

    const getRes = await worker.fetch(new Request('http://localhost/api/settings/task-flags', {
      headers: { 'X-Agent-Secret': 'test-secret' },
    }), BASE_ENV);
    expect(getRes.status).toBe(200);
    const getData = await getRes.json();
    expect(getData.flags.queryMode).toBe('query');

    const putRes = await worker.fetch(new Request('http://localhost/api/settings/task-flags', {
      method: 'PUT',
      headers: { 'X-Agent-Secret': 'test-secret', 'Content-Type': 'application/json' },
      body: JSON.stringify({ queryMode: 'legacy', recoveryEnabled: false, staleMinutes: 60 }),
    }), BASE_ENV);
    expect(putRes.status).toBe(200);
    expect(firestoreSet).toHaveBeenCalledWith(
      BASE_ENV,
      'system_config/default',
      expect.objectContaining({
        tasks_query_mode: 'legacy',
        tasks_recovery_enabled: false,
        tasks_stale_minutes: 60,
      })
    );
  });
});
