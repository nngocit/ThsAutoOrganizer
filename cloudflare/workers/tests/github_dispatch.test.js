// tests/github_dispatch.test.js — Worker báo GitHub Actions (repository_dispatch) khi có task NLM mới

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('../src/lib/firebase.js', () => ({
  firestoreSet: vi.fn(async () => ({})),
}));
vi.mock('../src/lib/folders.js', () => ({ isOutputFolder: () => false }));
vi.mock('../src/lib/notebooks.js', () => ({ resolveNotebookId: vi.fn(async () => 'nb-1') }));

import { enqueueTask, NLM_QUEUE, DRIVE_QUEUE } from '../src/lib/tasks.js';
import { firestoreSet } from '../src/lib/firebase.js';

describe('repository_dispatch — Worker → GitHub Actions', () => {
  let fetchMock;

  beforeEach(() => {
    vi.clearAllMocks();
    fetchMock = vi.fn(async () => ({ ok: true, status: 204 }));
    vi.stubGlobal('fetch', fetchMock);
  });

  afterEach(() => vi.unstubAllGlobals());

  it('thiếu GITHUB_DISPATCH_TOKEN → bỏ qua dispatch, task vẫn ghi bình thường', async () => {
    const id = await enqueueTask({}, NLM_QUEUE, { action: 'source_add' });

    expect(id).toBeTruthy();
    expect(firestoreSet).toHaveBeenCalledTimes(1);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('có token → POST đúng repo/event_type/client_payload', async () => {
    const env = { GITHUB_DISPATCH_TOKEN: 'ghp_test_token' };

    await enqueueTask(env, NLM_QUEUE, { action: 'source_add' });

    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('https://api.github.com/repos/nngocit/ThsAutoOrganizer/dispatches');
    expect(init.method).toBe('POST');
    expect(init.headers.Authorization).toBe('Bearer ghp_test_token');
    expect(JSON.parse(init.body)).toEqual({
      event_type: 'nlm-drain',
      client_payload: { queue: NLM_QUEUE, action: 'source_add' },
    });
  });

  it('GITHUB_DISPATCH_REPO cho phép đổi repo đích', async () => {
    const env = { GITHUB_DISPATCH_TOKEN: 't', GITHUB_DISPATCH_REPO: 'other/repo' };

    await enqueueTask(env, NLM_QUEUE, { action: 'chat_query' });

    expect(fetchMock.mock.calls[0][0]).toContain('/repos/other/repo/dispatches');
  });

  it('drive queue → không dispatch (chỉ NLM queue mới cần runner cloud)', async () => {
    const env = { GITHUB_DISPATCH_TOKEN: 'ghp_test_token' };

    await enqueueTask(env, DRIVE_QUEUE, { action: 'hard_delete' });

    expect(fetchMock).not.toHaveBeenCalled();
  });

  it('GitHub lỗi/mất mạng → KHÔNG làm hỏng request chính, task vẫn tạo', async () => {
    fetchMock.mockRejectedValue(new Error('network down'));

    const id = await enqueueTask({ GITHUB_DISPATCH_TOKEN: 't' }, NLM_QUEUE, { action: 'exam_generate' });

    expect(id).toBeTruthy();
    expect(firestoreSet).toHaveBeenCalledTimes(1);
  });
});
