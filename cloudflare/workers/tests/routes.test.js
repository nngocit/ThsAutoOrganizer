import { describe, it, expect } from 'vitest';
import worker from '../src/index.js';

describe('Worker Routes Routing', () => {
  it('POST /api/files/check-hash should not return 404 Not Found', async () => {
    const res = await worker.fetch(new Request('http://localhost/api/files/check-hash', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Agent-Secret': 'test-secret',
      },
      body: JSON.stringify({ sha256: 'a'.repeat(64), uid: 'test-uid' }),
    }), {
      AGENT_SECRET: 'test-secret',
      FIREBASE_SERVICE_ACCOUNT: JSON.stringify({ project_id: 'test', client_email: 'test@test.iam.gserviceaccount.com', private_key: '-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC7\n-----END PRIVATE KEY-----' }),
    });

    const data = await res.json();
    // Route must be found — should NOT be 404 Not Found for /api/files/check-hash
    expect(res.status).not.toBe(404);
    expect(data.path).toBeUndefined();
  });

  it('POST /api/files/register should not return 404 Not Found', async () => {
    const res = await worker.fetch(new Request('http://localhost/api/files/register', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Agent-Secret': 'test-secret',
      },
      body: JSON.stringify({
        uid: 'test-uid',
        filename: 'test.pdf',
        sha256: 'b'.repeat(64),
        drive_file_id: 'drive-123',
        size_bytes: 1024,
        local_path: '/path/test.pdf',
        subject: 'Triết học',
      }),
    }), {
      AGENT_SECRET: 'test-secret',
      FIREBASE_SERVICE_ACCOUNT: JSON.stringify({ project_id: 'test', client_email: 'test@test.iam.gserviceaccount.com', private_key: '-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC7\n-----END PRIVATE KEY-----' }),
    });

    const data = await res.json();
    // Route must be found — should NOT be 404 Not Found for /api/files/register
    expect(res.status).not.toBe(404);
    expect(data.path).toBeUndefined();
  });
});
