import { describe, it, expect, vi, beforeEach } from 'vitest';

const createdFolders = [];
const sharedPermissions = [];
const savedDocs = {};

vi.mock('../src/lib/drive.js', () => ({
  createDriveFolder: vi.fn(async (env, name, parentId) => {
    const id = `folder_${name.replace(/[^a-zA-Z0-9]/g, '_')}_${Date.now()}`;
    createdFolders.push({ id, name, parentId });
    return { id, name };
  }),
  setDriveWriterPermission: vi.fn(async (env, fileId, email) => {
    sharedPermissions.push({ fileId, email });
    return { id: `perm_${fileId}` };
  }),
  setDriveAnyonePermission: vi.fn().mockResolvedValue({ id: 'perm_anyone' }),
  findDriveFolderByName: vi.fn().mockResolvedValue(null),
}));

vi.mock('../src/lib/firebase.js', () => ({
  firestoreGet: vi.fn(async (env, path) => savedDocs[path] || null),
  firestoreSet: vi.fn(async (env, path, data) => {
    savedDocs[path] = { fields: data };
    return { ok: true };
  }),
  firestoreList: vi.fn().mockResolvedValue({ documents: [] }),
  fromFirestoreDoc: vi.fn((doc) => doc?.fields || doc),
}));

import worker from '../src/index.js';

describe('Auto-Provisioning in Course Creation', () => {
  beforeEach(() => {
    createdFolders.length = 0;
    sharedPermissions.length = 0;
    for (const k of Object.keys(savedDocs)) delete savedDocs[k];

    vi.stubGlobal('fetch', async (url) => {
      const urlStr = String(url);
      if (urlStr.includes('oauth2.googleapis.com/tokeninfo')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            sub: 'user_auto_new_1',
            email: 'newuser@gmail.com',
            name: 'New Student',
            email_verified: 'true',
            exp: Math.floor(Date.now() / 1000) + 3600,
          }),
        };
      }
      return { ok: false, status: 404, json: async () => ({}) };
    });
  });

  it('should auto-provision dedicated drive root and share permission when creating first course', async () => {
    const res = await worker.fetch(new Request('http://localhost/api/courses', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer valid_new_user_token',
      },
      body: JSON.stringify({
        display_name: 'Nhập Môn AI',
      }),
    }), {});

    expect(res.status).toBe(201);
    const data = await res.json();
    expect(data.display_name).toBe('Nhập Môn AI');

    // Folder 1: User's dedicated root folder
    // Folder 2: Course subfolder inside the user's dedicated root folder
    expect(createdFolders.length).toBe(2);
    const userRootFolder = createdFolders[0];
    const courseFolder = createdFolders[1];

    expect(userRootFolder.name).toBe('ThacSi_HTTT');
    expect(courseFolder.name).toBe('Nhập Môn AI');
    expect(courseFolder.parentId).toBe(userRootFolder.id);

    // Permission shared for user
    expect(sharedPermissions.some(p => p.fileId === userRootFolder.id && p.email === 'newuser@gmail.com')).toBe(true);

    // Saved to users/user_auto_new_1/settings/config
    const userCfg = savedDocs['users/user_auto_new_1/settings/config'];
    expect(userCfg).toBeDefined();
    expect(userCfg.fields.google_drive_root_folder_id).toBe(userRootFolder.id);
  });

  it('should reuse existing google_drive_root_folder_id if user already has one configured', async () => {
    savedDocs['users/user_auto_new_1/settings/config'] = {
      fields: {
        google_drive_root_folder_id: 'existing_custom_folder_999',
        google_drive_root_name: 'Custom User Root',
      },
    };

    const res = await worker.fetch(new Request('http://localhost/api/courses', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer valid_new_user_token',
      },
      body: JSON.stringify({
        display_name: 'Học Máy Nâng Cao',
      }),
    }), {});

    expect(res.status).toBe(201);
    // Only 1 folder created (the course folder), because root was already configured
    expect(createdFolders.length).toBe(1);
    const courseFolder = createdFolders[0];
    expect(courseFolder.name).toBe('Học Máy Nâng Cao');
    expect(sharedPermissions.some((p) => p.fileId === courseFolder.id && p.email === 'newuser@gmail.com')).toBe(true);
  });
});

