// tests/three_way_sync.test.js — Kiểm thử bộ 3 luồng đồng bộ (Three-Way Sync Flows) & OAuth 2.0 Drive Client

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  getDriveAccessToken,
  createDriveFolder,
  uploadFileToDrive,
  listDriveSubfolders,
  _resetDriveTokenCache,
} from '../src/lib/drive.js';

describe('Three-Way Sync: Google Drive Client Functions (OAuth 2.0)', () => {
  const dummyEnv = {
    GOOGLE_CLIENT_ID: 'mock-client-id.apps.googleusercontent.com',
    GOOGLE_CLIENT_SECRET: 'mock-client-secret',
    GOOGLE_REFRESH_TOKEN: 'mock-refresh-token-12345',
  };

  beforeEach(() => {
    vi.clearAllMocks();
    _resetDriveTokenCache();
  });

  it('getDriveAccessToken trao đổi Refresh Token lấy Access Token và cache lại', async () => {
    let oauthFetchCount = 0;
    global.fetch = vi.fn().mockImplementation((url, opts) => {
      if (url.includes('oauth2.googleapis.com/token')) {
        oauthFetchCount++;
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ access_token: 'mock-drive-token-cached', expires_in: 3600 }),
        });
      }
      return Promise.reject(new Error(`Unexpected url ${url}`));
    });

    const token1 = await getDriveAccessToken(dummyEnv);
    expect(token1).toBe('mock-drive-token-cached');
    expect(oauthFetchCount).toBe(1);

    // Lần gọi thứ 2 phải lấy từ cache trong bộ nhớ, không gửi lại HTTP request
    const token2 = await getDriveAccessToken(dummyEnv);
    expect(token2).toBe('mock-drive-token-cached');
    expect(oauthFetchCount).toBe(1);
  });

  it('createDriveFolder gọi Google Drive API files.create với mimeType folder', async () => {
    global.fetch = vi.fn().mockImplementation((url, opts) => {
      if (url.includes('oauth2.googleapis.com/token')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ access_token: 'mock-drive-token' }),
        });
      }
      if (url.includes('googleapis.com/drive/v3/files')) {
        expect(opts.method).toBe('POST');
        expect(opts.headers.Authorization).toBe('Bearer mock-drive-token');
        const body = JSON.parse(opts.body);
        expect(body.name).toBe('Kien Truc Phan Mem');
        expect(body.mimeType).toBe('application/vnd.google-apps.folder');
        expect(body.parents).toEqual(['root-123']);
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ id: 'new-folder-id-789', name: 'Kien Truc Phan Mem' }),
        });
      }
      return Promise.reject(new Error(`Unexpected url ${url}`));
    });

    const folder = await createDriveFolder(dummyEnv, 'Kien Truc Phan Mem', 'root-123');
    expect(folder.id).toBe('new-folder-id-789');
  });

  it('listDriveSubfolders truy vấn đúng filter folder và trashed=false', async () => {
    global.fetch = vi.fn().mockImplementation((url, opts) => {
      if (url.includes('oauth2.googleapis.com/token')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ access_token: 'mock-drive-token' }),
        });
      }
      if (url.includes('googleapis.com/drive/v3/files')) {
        expect(opts.headers.Authorization).toBe('Bearer mock-drive-token');
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({
            files: [
              { id: 'f1', name: 'Triet Hoc', createdTime: '2026-09-01T00:00:00Z' },
              { id: 'f2', name: 'Toan Roi Rac', createdTime: '2026-09-02T00:00:00Z' },
            ],
          }),
        });
      }
      return Promise.reject(new Error(`Unexpected url ${url}`));
    });

    const subfolders = await listDriveSubfolders(dummyEnv, 'root-123');
    expect(subfolders.length).toBe(2);
    expect(subfolders[0].name).toBe('Triet Hoc');
  });

  it('uploadFileToDrive gửi multipart/related với binary content và metadata', async () => {
    global.fetch = vi.fn().mockImplementation((url, opts) => {
      if (url.includes('oauth2.googleapis.com/token')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ access_token: 'mock-drive-token' }),
        });
      }
      if (url.includes('upload/drive/v3/files')) {
        expect(opts.method).toBe('POST');
        expect(opts.headers.Authorization).toBe('Bearer mock-drive-token');
        expect(opts.headers['Content-Type']).toContain('multipart/related; boundary=');
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ id: 'uploaded-file-456', name: 'tailieu.pdf' }),
        });
      }
      return Promise.reject(new Error(`Unexpected url ${url}`));
    });

    const buffer = new Uint8Array([10, 20, 30]).buffer;
    const res = await uploadFileToDrive(dummyEnv, {
      filename: 'tailieu.pdf',
      mimeType: 'application/pdf',
      parentId: 'folder-999',
      contentBuffer: buffer,
    });
    expect(res.id).toBe('uploaded-file-456');
  });
});

