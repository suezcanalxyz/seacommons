import assert from 'node:assert/strict';
import test from 'node:test';
import { workspaceTarget } from '../../../api/workspace.js';

test('workspace proxy uses configured TLS origin and constrained private paths', () => {
  assert.equal(workspaceTarget({ path: 'records', limit: '200' }, 'https://api.example.org').href,
    'https://api.example.org/api/v1/workspace/records?limit=200');
  assert.throws(() => workspaceTarget({ path: 'records' }, 'http://api.example.org'));
  assert.throws(() => workspaceTarget({ path: '../admin' }, 'https://api.example.org'));
  assert.throws(() => workspaceTarget({ path: 'https://attacker.example' }, 'https://api.example.org'));
  assert.throws(() => workspaceTarget({ path: 'records' }, 'https://user:secret@api.example.org'));
});
