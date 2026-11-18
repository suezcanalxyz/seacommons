import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../../components/ConePanel.jsx', import.meta.url), 'utf8');

test('LIVE evidence panel exposes both actual trigger fixes with coordinates and timestamps', () => {
  assert.match(source, /movementEvidence\.from_at/);
  assert.match(source, /movementEvidence\.to_at/);
  assert.match(source, /Last observed fix/);
  assert.match(source, /Next recorded fix/);
  assert.match(source, /formatTriggerEndpoint\(triggerEndpoints\[0\]\)/);
  assert.match(source, /formatTriggerEndpoint\(triggerEndpoints\[1\]\)/);
});

test('AIS gaps are explicitly shown as unobserved rather than a verified transit', () => {
  assert.match(source, /AIS not observed; no route inferred/);
  assert.match(source, /strokeDasharray="5 5"/);
});


test('trigger endpoints remain in graphic bounds even with an unrelated public track', () => {
  assert.match(source, /const all = \[\.\.\.observed, \.\.\.forecast, \.\.\.fallback, \.\.\.evidenceEndpoints\]/);
});

test('gap fix sequences are not presented as continuous observed vessel paths', () => {
  assert.match(source, /observed.length >= 2 && !triggerIsGap/);
  assert.match(source, /observed.length >= 2 && triggerIsGap/);
  assert.match(source, /connecting path unverified/);
});
