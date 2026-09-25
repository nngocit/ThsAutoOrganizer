import { describe, it, expect, vi, beforeEach } from 'vitest';

// Mock drive.js and firebase.js
vi.mock('../src/lib/drive.js', () => ({
  createDriveFolder: vi.fn().mockResolvedValue({ id: 'mock_drive_folder_id_123', name: 'ThacSi_HTTT - Nguyen Van A' }),
  setDriveWriterPermission: vi.fn().mockResolvedValue({ id: 'perm_id_123' }),
  setDriveAnyonePermission: vi.fn().mockResolvedValue({ id: 'perm_anyone_123' }),
  findDriveFolderByName: vi.fn().mockResolvedValue(null),
}));

vi.mock('../src/lib/firebase.js', () => ({
  firestoreGet: vi.fn().mockResolvedValue(null),
  firestoreSet: vi.fn().mockResolvedValue({ ok: true }),
  fromFirestoreDoc: vi.fn((doc) => doc),
}));

import worker from '../src/index.js';

describe('Settings & Drive Provisioning API', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', async (url, options) => {
      const urlStr = String(url);
      if (urlStr.includes('oauth2.googleapis.com/tokeninfo')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            sub: 'u_123',
            email: 'student@gmail.com',
            name: 'Nguyen Van A',
            email_verified: 'true',
            exp: Math.floor(Date.now() / 1000) + 3600,
          }),
        };
      }
      return { ok: false, status: 404, json: async () => ({}) };
    });
  });

  it('POST /api/settings/provision-drive should require authentication (401 without Bearer)', async () => {
    const res = await worker.fetch(new Request('http://localhost/api/settings/provision-drive', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
    }), {});

    expect(res.status).toBe(401);
  });

  it('GET /api/settings/config should return default master root if not initialized', async () => {
    const res = await worker.fetch(new Request('http://localhost/api/settings/config?uid=test_new_user', {
      method: 'GET',
      headers: {
        'X-Agent-Secret': 'test-secret',
      },
    }), {
      AGENT_SECRET: 'test-secret',
      DEFAULT_UID: 'test_new_user',
    });

    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.config).toBeDefined();
    expect(data.config.google_drive_root_folder_id).toBe('1xAZK2zEeqgm2zN5_37ZafJPqYFhtuXtg');
  });

  it('POST /api/settings/provision-drive should create folder and share permission for user', async () => {
    const res = await worker.fetch(new Request('http://localhost/api/settings/provision-drive', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer valid_user_token',
      },
    }), {});

    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.status).toBe('provisioned');
    expect(data.folder_id).toBe('mock_drive_folder_id_123');
    expect(data.user_email).toBe('student@gmail.com');
    expect(data.config.google_drive_root_folder_id).toBe('mock_drive_folder_id_123');
  });
});
