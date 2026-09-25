import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../src/lib/drive.js', () => ({
  createDriveFolder: vi.fn().mockImplementation(async (env, name, parentId) => ({
    id: `new_created_folder_${name}`,
    name,
    parentId,
  })),
  setDriveWriterPermission: vi.fn().mockResolvedValue({ id: 'perm_id_123' }),
  setDriveAnyonePermission: vi.fn().mockResolvedValue({ id: 'perm_anyone_123' }),
  listDriveSubfolders: vi.fn().mockResolvedValue([]),
  findDriveFolderByName: vi.fn(),
}));

vi.mock('../src/lib/firebase.js', () => {
  let store = {};
  return {
    firestoreGet: vi.fn(async (env, path) => store[path] || null),
    firestoreSet: vi.fn(async (env, path, data) => {
      store[path] = data;
      return { ok: true };
    }),
    firestoreList: vi.fn(async () => []),
    fromFirestoreDoc: vi.fn((doc) => doc),
    _clearStore: () => { store = {}; },
    _getStore: () => store,
  };
});

import worker from '../src/index.js';
import { createDriveFolder, setDriveWriterPermission, findDriveFolderByName } from '../src/lib/drive.js';
import { firestoreSet, _getStore, _clearStore } from '../src/lib/firebase.js';

describe('Drive Idempotency & Multi-tenant Isolation API', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    _clearStore();
    vi.stubGlobal('fetch', async (url, options) => {
      const urlStr = String(url);
      if (urlStr.includes('oauth2.googleapis.com/tokeninfo')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            sub: 'user_idem_123',
            email: 'user_idem@domain.com',
            name: 'Idem User',
            email_verified: 'true',
            exp: Math.floor(Date.now() / 1000) + 3600,
          }),
        };
      }
      return { ok: false, status: 404, json: async () => ({}) };
    });
  });

  it('POST /api/settings/provision-drive reuses existing folder if already created on Drive (Idempotency)', async () => {
    // Giả lập Drive đã tồn tại thư mục của user
    findDriveFolderByName.mockResolvedValueOnce({
      id: 'existing_drive_folder_777',
      name: 'ThacSi_HTTT - Idem User',
    });

    const res = await worker.fetch(new Request('http://localhost/api/settings/provision-drive', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer valid_token',
      },
    }), {
      DEFAULT_DRIVE_ROOT: 'master_root_id',
    });

    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.status).toBe('reused');
    expect(data.folder_id).toBe('existing_drive_folder_777');
    expect(data.folder_name).toBe('ThacSi_HTTT - Idem User');
    // KHÔNG được gọi tạo trùng lặp
    expect(createDriveFolder).not.toHaveBeenCalled();
    // Vẫn lưu cấu hình vào Firestore của user
    expect(firestoreSet).toHaveBeenCalledWith(
      expect.anything(),
      'users/user_idem_123/settings/config',
      expect.objectContaining({
        google_drive_root_folder_id: 'existing_drive_folder_777',
      })
    );
  });

  it('POST /api/drive/init-root endpoint also works and creates folder if not existing', async () => {
    // Giả lập chưa tồn tại thư mục
    findDriveFolderByName.mockResolvedValueOnce(null);

    const res = await worker.fetch(new Request('http://localhost/api/drive/init-root', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer valid_token',
      },
    }), {
      DEFAULT_DRIVE_ROOT: 'master_root_id',
    });

    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.status).toBe('provisioned');
    expect(createDriveFolder).toHaveBeenCalled();
    expect(setDriveWriterPermission).toHaveBeenCalledWith(
      expect.anything(),
      expect.stringContaining('new_created_folder_'),
      'user_idem@domain.com'
    );
  });

  it('POST /api/courses creates task in nlm_task_queue with owner_email', async () => {
    const res = await worker.fetch(new Request('http://localhost/api/courses', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer valid_token',
      },
      body: JSON.stringify({
        name: 'Mon Hoc Kiem Thu 101',
      }),
    }), {
      DEFAULT_DRIVE_ROOT: 'master_root_id',
    });

    expect(res.status).toBe(201);
    const store = _getStore();
    const taskEntry = Object.entries(store).find(([k, v]) => k.startsWith('nlm_task_queue/'));
    expect(taskEntry).toBeDefined();
    const task = taskEntry[1];
    expect(task.owner_email).toBe('user_idem@domain.com');
  });
});
