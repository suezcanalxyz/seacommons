import test from 'node:test';
import assert from 'node:assert/strict';
import { liveAisGapFeatures } from './aisGapLive.js';
test('open AIS gap has last observed point but no invented return', () => {
  const features = liveAisGapFeatures([{ type:'Feature', geometry:{type:'Point',coordinates:[15,35]}, properties:{episode_family:'gap_episode',gap_still_open:true,current_silent_seconds:7200,linked_mmsi:'123456789'} }]).features;
  assert.equal(features.length,1);
  assert.equal(features[0].properties.status,'open_gap_no_reappearance');
});
test('bounded gap has observed endpoints and unobserved connection', () => {
  const points = [{at:'2026-11-17T09:00:00Z',lat:35,lon:15},{at:'2026-11-17T10:00:00Z',lat:35.1,lon:15.1}];
  const features = liveAisGapFeatures([{properties:{episode_family:'gap_episode',observed_track:points}}]).features;
  assert.deepEqual(features.map(f=>f.properties.kind),['ais_gap_unobserved_connection','ais_last_observed','ais_first_reappearance']);
});
test('non-gap signals never create gap geometry', () => {
  assert.equal(liveAisGapFeatures([{geometry:{type:'Point',coordinates:[15,35]},properties:{type:'humanitarian',observed_track:[]}}]).features.length,0);
});
