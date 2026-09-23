import { describe, it, expect } from 'vitest';
import { resolveTargetUid } from '../src/lib/auth.js';

describe('resolveTargetUid Security & Correctness', () => {
  it('should NEVER return an object when user object is mistakenly passed as bodyUid', () => {
    const mockContext = {
      get: (key) => (key === 'user' ? { uid: '', email: '', name: 'agent' } : null),
      env: {},
    };
    const agentUserObj = { uid: '', email: '', name: 'agent' };

    // When queryUid is provided
    const resultWithQuery = resolveTargetUid(mockContext, agentUserObj, 'user_123');
    expect(resultWithQuery).toBe('user_123');

    // When no queryUid is provided
    const resultWithoutQuery = resolveTargetUid(mockContext, agentUserObj, undefined);
    expect(resultWithoutQuery).toBe('');
    expect(typeof resultWithoutQuery).toBe('string');
  });

  it('should return user.uid when user is authenticated with Google token', () => {
    const mockContext = {
      get: (key) => (key === 'user' ? { uid: 'google_user_999', email: 'test@gmail.com' } : null),
      env: {},
    };
    expect(resolveTargetUid(mockContext, null, null)).toBe('google_user_999');
    expect(resolveTargetUid(mockContext, 'attacker_uid', null)).toBe('google_user_999');
  });

  it('should extract uid when body.uid is provided for agent requests', () => {
    const mockContext = {
      get: (key) => (key === 'user' ? { uid: '', name: 'agent' } : null),
      env: {},
    };
    expect(resolveTargetUid(mockContext, 'target_user_456', null)).toBe('target_user_456');
    expect(resolveTargetUid(mockContext, { uid: 'target_user_789' }, null)).toBe('target_user_789');
  });

  it('should extract uid from query param when agent passes ?uid=', () => {
    const mockContext = {
      get: (key) => (key === 'user' ? { uid: '', name: 'agent' } : null),
      env: {},
    };
    expect(resolveTargetUid(mockContext, null, 'query_uid_111')).toBe('query_uid_111');
  });

  it('should fall back to env.DEFAULT_UID if nothing else is provided', () => {
    const mockContext = {
      get: (key) => (key === 'user' ? { uid: '', name: 'agent' } : null),
      env: { DEFAULT_UID: 'default_admin_uid' },
    };
    expect(resolveTargetUid(mockContext, null, null)).toBe('default_admin_uid');
  });
});
