import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

const main = fs.readFileSync(path.resolve('src/main.jsx'), 'utf8');
const dashboard = fs.readFileSync(path.resolve('src/components/IntelDashboard.jsx'), 'utf8');

test('public Live primary semantics are Humanitarian and Maritime, never legacy source buckets', () => {
  assert.match(main, /key: 'humanitarian'[\s\S]*label: 'Humanitarian'/);
  assert.match(main, /key: 'maritime'[\s\S]*label: 'Maritime'/);
  assert.doesNotMatch(main, /label: 'Maritime Security'/);
  assert.doesNotMatch(dashboard, /label: 'Direct'/);
  assert.doesNotMatch(dashboard, /label: 'Public feeds'/);
});

test('vessel incident safety filter belongs to Maritime macro', () => {
  const maritime = main.slice(main.indexOf("key: 'maritime'"), main.indexOf('];', main.indexOf("key: 'maritime'")));
  assert.match(maritime, /key: 'incident'/);
  assert.match(maritime, /label: 'Safety'/);
});
