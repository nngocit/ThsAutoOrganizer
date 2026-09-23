import { describe, it, expect, vi } from 'vitest';
import { setPublicReaderPermission } from '../src/lib/drive.js';

describe('Google Drive Public Reader Permission', () => {
  it('BẮT BUỘC gọi drive.permissions.create với type: anyone, role: reader và trả về webViewLink', async () => {
    const mockAccessToken = 'mock-access-token';
    const mockFileId = 'mock-drive-file-id-123';
    const expectedLink = 'https://drive.google.com/file/d/mock-drive-file-id-123/view';

    // Mock fetch toàn cục
    global.fetch = vi.fn().mockImplementation((url, options) => {
      // 1. permissions.create
      if (url.includes(`/files/${mockFileId}/permissions`)) {
        expect(options.method).toBe('POST');
        expect(options.headers.Authorization).toBe(`Bearer ${mockAccessToken}`);
        const body = JSON.parse(options.body);
        expect(body.type).toBe('anyone');
        expect(body.role).toBe('reader');
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ id: 'permission-id-123' }),
          text: () => Promise.resolve(''),
        });
      }

      // 2. files.get để lấy webViewLink
      if (url.includes(`/files/${mockFileId}?fields=`)) {
        expect(options.headers.Authorization).toBe(`Bearer ${mockAccessToken}`);
        return Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({
            id: mockFileId,
            webViewLink: expectedLink,
          }),
          text: () => Promise.resolve(''),
        });
      }

      return Promise.reject(new Error(`Unexpected URL: ${url}`));
    });

    const webViewLink = await setPublicReaderPermission(mockAccessToken, mockFileId);
    expect(webViewLink).toBe(expectedLink);
  });

  it('Báo lỗi nếu drive.permissions.create thất bại', async () => {
    global.fetch = vi.fn().mockImplementation((url) => {
      if (url.includes('/permissions')) {
        return Promise.resolve({
          ok: false,
          status: 403,
          text: () => Promise.resolve('Insufficient permissions'),
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({}) });
    });

    await expect(setPublicReaderPermission('token', 'file123'))
      .rejects
      .toThrow('drive.permissions.create failed (403)');
  });
});
