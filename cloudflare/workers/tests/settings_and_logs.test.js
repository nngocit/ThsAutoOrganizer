import { describe, it, expect } from 'vitest';
import worker from '../src/index.js';

describe('Global Settings & System Logs API', () => {
  const env = {
    AGENT_SECRET: 'test-agent-secret',
    DEFAULT_UID: 'test-user-uid',
    FIREBASE_SERVICE_ACCOUNT: JSON.stringify({
      project_id: 'test',
      client_email: 'test@test.iam.gserviceaccount.com',
      private_key: '-----BEGIN PRIVATE KEY-----\nMIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQC7\n-----END PRIVATE KEY-----',
    }),
  };

  it('GET /api/settings/config should not return 404 Not Found', async () => {
    const res = await worker.fetch(new Request('http://localhost/api/settings/config', {
      method: 'GET',
      headers: {
        'X-Agent-Secret': 'test-agent-secret',
      },
    }), env);

    expect(res.status).not.toBe(404);
  });

  it('PUT /api/settings/config should not return 404 Not Found', async () => {
    const res = await worker.fetch(new Request('http://localhost/api/settings/config', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'X-Agent-Secret': 'test-agent-secret',
      },
      body: JSON.stringify({
        local_base_path: 'D:\\Study\\2026',
        google_drive_root_folder_id: 'folder-test-123',
      }),
    }), env);

    expect(res.status).not.toBe(404);
  });

  it('POST /api/logs should not return 404 Not Found', async () => {
    const res = await worker.fetch(new Request('http://localhost/api/logs', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Agent-Secret': 'test-agent-secret',
      },
      body: JSON.stringify({
        level: 'ERROR',
        module: 'nlm_task_handler',
        message: 'Test log message',
      }),
    }), env);

    expect(res.status).not.toBe(404);
  });

  it('GET /api/logs should not return 404 Not Found', async () => {
    const res = await worker.fetch(new Request('http://localhost/api/logs', {
      method: 'GET',
      headers: {
        'X-Agent-Secret': 'test-agent-secret',
      },
    }), env);

    expect(res.status).not.toBe(404);
  });
});
