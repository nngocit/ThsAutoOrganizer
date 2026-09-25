import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../src/lib/drive.js', () => ({
  createDriveFolder: vi.fn().mockImplementation(async (env, name, parentId) => ({
    id: `mock_folder_${name}`,
    name,
    parentId,
  })),
  setDriveWriterPermission: vi.fn().mockResolvedValue({ id: 'perm_id_123' }),
  setDriveAnyonePermission: vi.fn().mockResolvedValue({ id: 'perm_anyone_123' }),
  listDriveSubfolders: vi.fn().mockResolvedValue([]),
  findDriveFolderByName: vi.fn().mockResolvedValue(null),
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
  };
});

import worker from '../src/index.js';
import { createDriveFolder } from '../src/lib/drive.js';
import { _clearStore } from '../src/lib/firebase.js';

describe('Dynamic Config & Custom Root Parameters', () => {
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
            sub: 'user_dynamic_123',
            email: 'user_dynamic@domain.com',
            name: 'Dynamic User',
            email_verified: 'true',
            exp: Math.floor(Date.now() / 1000) + 3600,
          }),
        };
      }
      return { ok: false, status: 404, json: async () => ({}) };
    });
  });

  it('GET /api/settings/config respects env.DEFAULT_DRIVE_ROOT and env.DEFAULT_LOCAL_PATH and populates aliases', async () => {
    const res = await worker.fetch(new Request('http://localhost/api/settings/config?uid=uninitialized_user', {
      method: 'GET',
      headers: {
        'X-Agent-Secret': 'secret_123',
      },
    }), {
      AGENT_SECRET: 'secret_123',
      DEFAULT_DRIVE_ROOT: 'custom_env_root_drive_id',
      DEFAULT_LOCAL_PATH: 'D:\\CustomCourses\\HTTT',
    });

    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.config.google_drive_root_folder_id).toBe('custom_env_root_drive_id');
    expect(data.config.drive_root_folder).toBe('custom_env_root_drive_id');
    expect(data.config.local_base_path).toBe('D:\\CustomCourses\\HTTT');
    expect(data.config.root_folder).toBe('D:\\CustomCourses\\HTTT');
  });

  it('PUT /api/settings/config updates both aliases when root_folder or drive_root_folder are sent', async () => {
    const res = await worker.fetch(new Request('http://localhost/api/settings/config?uid=user_dynamic_123', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer valid_token',
      },
      body: JSON.stringify({
        root_folder: 'E:\\TargetSync\\Folder',
        drive_root_folder: 'custom_drive_folder_id_xyz',
      }),
    }), {
      DEFAULT_DRIVE_ROOT: 'default_drive_id',
      DEFAULT_LOCAL_PATH: 'C:\\Default',
    });

    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.config.local_base_path).toBe('E:\\TargetSync\\Folder');
    expect(data.config.root_folder).toBe('E:\\TargetSync\\Folder');
    expect(data.config.google_drive_root_folder_id).toBe('custom_drive_folder_id_xyz');
    expect(data.config.drive_root_folder).toBe('custom_drive_folder_id_xyz');
  });

  it('POST /api/settings/provision-drive provisions child folder inside env.DEFAULT_DRIVE_ROOT', async () => {
    const res = await worker.fetch(new Request('http://localhost/api/settings/provision-drive', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer valid_token',
      },
    }), {
      DEFAULT_DRIVE_ROOT: 'env_master_drive_root_999',
    });

    expect(res.status).toBe(200);
    expect(createDriveFolder).toHaveBeenCalledWith(
      expect.anything(),
      expect.stringContaining('ThacSi_HTTT'),
      'env_master_drive_root_999'
    );
  });
});
