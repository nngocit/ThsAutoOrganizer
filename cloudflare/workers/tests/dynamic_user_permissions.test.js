import { describe, it, expect, vi, beforeEach } from 'vitest';

const writerPermissions = [];
const createdFolders = [];
const savedDocs = {};

vi.mock('../src/lib/drive.js', () => ({
  createDriveFolder: vi.fn(async (env, name, parentId) => {
    const id = `folder_${name.replace(/[^a-zA-Z0-9]/g, '_')}`;
    createdFolders.push({ id, name, parentId });
    return { id, name };
  }),
  setDriveWriterPermission: vi.fn(async (env, fileId, email) => {
    writerPermissions.push({ fileId, email });
    return { id: `perm_${fileId}_${email}` };
  }),
  setDriveAnyonePermission: vi.fn().mockResolvedValue({ id: 'perm_anyone' }),
  setDrivePublicReader: vi.fn().mockResolvedValue('https://drive.google.com/file/view'),
  findDriveFolderByName: vi.fn().mockResolvedValue(null),
  uploadFileToDrive: vi.fn().mockResolvedValue({ id: 'uploaded_drive_file_999' }),
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

describe('100% Dynamic Multi-Tenant Drive Permissions (Zero Hardcode)', () => {
  beforeEach(() => {
    writerPermissions.length = 0;
    createdFolders.length = 0;
    for (const k of Object.keys(savedDocs)) delete savedDocs[k];
  });

  it('provisions root folder and grants full writer permission dynamically to ANY logged in user email', async () => {
    const randomUserEmail = 'alex_student_2026@university.edu';
    
    vi.stubGlobal('fetch', async (url) => {
      const urlStr = String(url);
      if (urlStr.includes('oauth2.googleapis.com/tokeninfo')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            sub: 'user_alex_101',
            email: randomUserEmail,
            name: 'Alex Student',
            email_verified: 'true',
            exp: Math.floor(Date.now() / 1000) + 3600,
          }),
        };
      }
      return { ok: false, status: 404, json: async () => ({}) };
    });

    const res = await worker.fetch(new Request('http://localhost/api/settings/provision-drive', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer token_alex',
      },
    }), {});

    expect(res.status).toBe(200);
    const data = await res.json();
    expect(data.user_email).toBe(randomUserEmail);
    expect(data.folder_name).toBe('ThacSi_HTTT');

    // Phải cấp quyền trực tiếp cho email đang đăng nhập alex_student_2026@university.edu
    expect(writerPermissions.some((p) => p.email === randomUserEmail)).toBe(true);
    // Tuyệt đối không được gán quyền cho email hardcode lạ
    expect(writerPermissions.some((p) => p.email === 'xuanngocit@gmail.com')).toBe(false);
    expect(writerPermissions.some((p) => p.email === 'itxuanngoc@gmail.com')).toBe(false);
  });

  it('grants full writer permission to logged in user on both root and course folder when creating course', async () => {
    const randomUserEmail = 'maria_engineer@techcorp.io';

    vi.stubGlobal('fetch', async (url) => {
      const urlStr = String(url);
      if (urlStr.includes('oauth2.googleapis.com/tokeninfo')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            sub: 'user_maria_202',
            email: randomUserEmail,
            name: 'Maria Engineer',
            email_verified: 'true',
            exp: Math.floor(Date.now() / 1000) + 3600,
          }),
        };
      }
      return { ok: false, status: 404, json: async () => ({}) };
    });

    const res = await worker.fetch(new Request('http://localhost/api/courses', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': 'Bearer token_maria',
      },
      body: JSON.stringify({
        display_name: 'Kien Truc He Thong',
      }),
    }), {});

    expect(res.status).toBe(201);
    // User maria phải được cấp quyền writer
    const mariaPerms = writerPermissions.filter((p) => p.email === randomUserEmail);
    expect(mariaPerms.length).toBeGreaterThanOrEqual(1);

    // Tuyệt đối không xuất hiện email hardcode
    expect(writerPermissions.some((p) => p.email === 'xuanngocit@gmail.com')).toBe(false);
  });

  it('grants writer permission to logged in user when uploading file to course', async () => {
    const randomUserEmail = 'dan_researcher@lab.org';
    const courseId = 'course_test_456';
    const driveFolderId = 'folder_course_drive_789';

    // Mock course in DB
    savedDocs[`users/user_dan_303/courses/${courseId}`] = {
      fields: {
        id: courseId,
        display_name: 'Machine Learning',
        drive_folder_id: driveFolderId,
        notebooklm_id: 'nb_123',
      },
    };

    vi.stubGlobal('fetch', async (url) => {
      const urlStr = String(url);
      if (urlStr.includes('oauth2.googleapis.com/tokeninfo')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            sub: 'user_dan_303',
            email: randomUserEmail,
            name: 'Dan Researcher',
            email_verified: 'true',
            exp: Math.floor(Date.now() / 1000) + 3600,
          }),
        };
      }
      return { ok: false, status: 404, json: async () => ({}) };
    });

    const formData = new FormData();
    formData.append('file', new File(['test document content'], 'sample.pdf', { type: 'application/pdf' }));
    formData.append('course_id', courseId);

    const res = await worker.fetch(new Request('http://localhost/api/files/upload', {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer token_dan',
      },
      body: formData,
    }), {});

    expect(res.status).toBe(201);
    // User dan phải được cấp quyền writer cho file vừa upload
    expect(writerPermissions.some((p) => p.email === randomUserEmail && p.fileId === 'uploaded_drive_file_999')).toBe(true);
    // Tuyệt đối không xuất hiện email hardcode
    expect(writerPermissions.some((p) => p.email === 'xuanngocit@gmail.com')).toBe(false);
  });
});
