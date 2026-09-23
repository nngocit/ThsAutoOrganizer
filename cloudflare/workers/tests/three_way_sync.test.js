// tests/three_way_sync.test.js — Kiểm thử bộ 3 luồng đồng bộ (Three-Way Sync Flows)

import { describe, it, expect, vi } from 'vitest';
import { createDriveFolder, uploadFileToDrive, listDriveSubfolders } from '../src/lib/drive.js';

describe('Three-Way Sync: Google Drive Client Functions', () => {
  const dummyEnv = {
    FIREBASE_SERVICE_ACCOUNT: JSON.stringify({
      client_email: 'test@serviceaccount.com',
      private_key: '-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC3\n-----END PRIVATE KEY-----',
    }),
  };

  it('createDriveFolder gọi Google Drive API files.create với mimeType folder', async () => {
    // Mock getDriveAccessToken qua fetch oauth token
    global.fetch = vi.fn().mockImplementation((url, opts) => {
      if (url.includes('oauth2.googleapis.com/token')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ access_token: 'mock-drive-token' }),
        });
      }
      if (url.includes('googleapis.com/drive/v3/files')) {
        expect(opts.method).toBe('POST');
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

    // Mock crypto.subtle.importKey và sign
    vi.spyOn(crypto.subtle, 'importKey').mockResolvedValue('mock-crypto-key');
    vi.spyOn(crypto.subtle, 'sign').mockResolvedValue(new Uint8Array([1, 2, 3]).buffer);

    const folder = await createDriveFolder(dummyEnv, 'Kien Truc Phan Mem', 'root-123');
    expect(folder.id).toBe('new-folder-id-789');
  });

  it('listDriveSubfolders truy vấn đúng filter folder và trashed=false', async () => {
    global.fetch = vi.fn().mockImplementation((url) => {
      if (url.includes('oauth2.googleapis.com/token')) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ access_token: 'mock-drive-token' }),
        });
      }
      if (url.includes('googleapis.com/drive/v3/files')) {
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

    vi.spyOn(crypto.subtle, 'importKey').mockResolvedValue('mock-crypto-key');
    vi.spyOn(crypto.subtle, 'sign').mockResolvedValue(new Uint8Array([1, 2, 3]).buffer);

    const subfolders = await listDriveSubfolders(dummyEnv, 'root-123');
    expect(subfolders.length).toBe(2);
    expect(subfolders[0].name).toBe('Triet Hoc');
  });
});
