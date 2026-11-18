import assert from 'node:assert/strict';
import test from 'node:test';
import { reviewedArchiveCase } from './humanitarianReview.js';

test('a destination-only report keeps the missing case but withdraws the inferred location', () => {
  const record = { incident_id: '57dce9fa', main_category: 'humanitarian', incident_type: 'missing',
    source: 'alarm_phone', geometry: { type: 'Polygon' }, has_satellite: true };
  const reviewed = reviewedArchiveCase(record);
  assert.equal(reviewed.incident_type, 'missing');
  assert.equal(reviewed.geometry, null);
  assert.equal(reviewed.has_satellite, false);
  assert.equal(record.geometry.type, 'Polygon');
});

test('public archive excludes reviewed advocacy and untraceable generic entries', () => {
  assert.equal(reviewedArchiveCase({ incident_id: 'a8154c20', main_category: 'humanitarian' }), null);
  assert.equal(reviewedArchiveCase({ title: 'Humanitarian incident', main_category: 'humanitarian' }), null);
  const distress = { title: 'People in distress', main_category: 'humanitarian', source: 'alarm_phone' };
  assert.equal(reviewedArchiveCase(distress), distress);
});

test('named places become two contextual markers and no vessel track', async () => {
  const { archiveGeographicClues, geographicClueFeatures } = await import('./humanitarianReview.js');
  const features = geographicClueFeatures(archiveGeographicClues({ incident_id: '57dce9fa' }));
  assert.deepEqual(features.map((item) => item.geometry.type), ['Point', 'Point']);
  assert.deepEqual(features.map((item) => item.properties.kind), ['clue_departure', 'clue_destination']);
  assert.equal(archiveGeographicClues({ incident_id: 'unknown' }).length, 0);
});

test('explicit test records are excluded without discarding historical reports by age', () => {
  assert.equal(reviewedArchiveCase({ archive_source: 'fixture', main_category: 'maritime' }), null);
  assert.equal(reviewedArchiveCase({ is_synthetic: true, main_category: 'humanitarian' }), null);
  const historical = { source: 'alarm_phone', reported_at: '2024-10-19T00:00:00Z' };
  assert.equal(reviewedArchiveCase(historical), historical);
});
