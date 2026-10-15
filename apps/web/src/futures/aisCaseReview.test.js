import assert from 'node:assert/strict';
import test from 'node:test';
import { aisFreshness, caseIdentity, coordsText, parseAISClock, reviewableCases } from './aisCaseReview.js';

const example = {
  type: 'Feature', id: 'episode:subj:imo:9316359:gap_episode:1',
  geometry: { type: 'Point', coordinates: [-1.15086, 37.16512] },
  properties: { imo: '9316359', linked_mmsi: '636017239', title: 'AIS gap' },
};

test('Live case selection requires real identifier and point', () => {
  assert.deepEqual(caseIdentity(example), { imo: '9316359', mmsi: '636017239' });
  assert.deepEqual(reviewableCases([example, {...example, geometry:{type:'Polygon',coordinates:[]}},
    {...example, properties:{mmsi:'123',imo:'bad'}}]), [example]);
});

test('AIS freshness uses source timestamp, never the map polling clock', () => {
  const now = Date.parse('2026-10-15T12:25:00Z');
  assert.equal(aisFreshness('2026-10-15T12:24:45Z', now), 'recent');
  assert.equal(aisFreshness('2026-10-15T11:25:00Z', now), 'delayed');
  assert.equal(aisFreshness('2026-10-14T09:25:00Z', now), 'stale');
  assert.equal(aisFreshness(null, now), 'unknown');
  assert.equal(parseAISClock('2026-10-15T12:24:45').toISOString(), '2026-10-15T12:24:45.000Z');
  assert.equal(coordsText(-5.5212, 'E', 'W'), '5.52120° W');
});
