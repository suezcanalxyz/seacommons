import test from 'node:test';
import assert from 'node:assert/strict';
import { projectNavtexPayload } from './navtex.js';

test('third-party NAVTEX is labelled as secondary and scoped to Mediterranean', () => {
  const result = projectNavtexPayload({ messages: [
    { id: '102', station: { id: 'station-eg', navarea: 'III' }, text: 'warning' },
    { id: '103', station: { id: 'station-be', navarea: 'I' }, text: 'outside scope' },
    { id: '102', station: { id: 'station-eg', navarea: 'III' }, text: 'duplicate' },
  ] });
  assert.equal(result.messages.length, 1);
  assert.equal(result.messages[0].original_text, 'duplicate');
  assert.equal(result.messages[0].original_url, 'https://navtex.online/messages/102');
  assert.equal(result.messages[0].is_dsc_decode, false);
  assert.equal(result.messages[0].independent_rf_reception, false);
  assert.equal(result.independent_rf_reception, false);
});

test('malformed and empty messages do not generate fake source observations', () => {
  assert.deepEqual(projectNavtexPayload({ messages: [{}] }).messages, []);
  assert.throws(() => projectNavtexPayload({}), /Invalid NAVTEX payload/);
});
