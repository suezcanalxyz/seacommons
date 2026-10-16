import assert from 'node:assert/strict';
import test from 'node:test';
import { validIMO, validMMSI, vesselFinderEmbedHtml, isolatedVesselFinderFrameUrl, vesselFinderPageUrl } from './aisCrossCheck.js';

test('only valid maritime identifiers enter external embed HTML', () => {
  assert.equal(validIMO('9316359'), true);
  assert.equal(validMMSI('636017239'), true);
  assert.equal(validIMO('9316359<script>'), false);
  assert.equal(validMMSI('123'), false);
  const html = vesselFinderEmbedHtml({ imo: '9316359', mmsi: '636017239' });
  assert.match(html, /var imo="9316359"/);
  assert.doesNotMatch(html, /var mmsi=/);
  assert.match(html, /show_track=true/);
  assert.match(html, /vesselfinder.com\/aismap.js/);
});

test('rejects untrusted IDs without loading an external script', () => {
  assert.throws(() => vesselFinderEmbedHtml({ imo: '<script>', mmsi: '' }), /valid IMO or MMSI/);
  const html = vesselFinderEmbedHtml({ imo: '', mmsi: '636017239' });
  assert.match(html, /var mmsi="636017239"/);
  assert.doesNotMatch(html, /<script>636017239/);
});

test('ship selection constructs an opaque-origin widget and human fallback', () => {
  const identity={imo:'9316359',mmsi:'636017239'};
  const url=isolatedVesselFinderFrameUrl(identity);
  assert.match(url,/^data:text\/html;charset=utf-8,/);
  const html=decodeURIComponent(url.split(',').slice(1).join(','));
  assert.match(html,/var imo="9316359"/);
  assert.match(html,/vesselfinder.com\/aismap.js/);
  assert.equal(vesselFinderPageUrl(identity),'https://www.vesselfinder.com/vessels/details/9316359');
  assert.equal(vesselFinderPageUrl({mmsi:'636017239'}),'https://www.vesselfinder.com/vessels');
  assert.equal(vesselFinderPageUrl({imo:'<script>'}),'');
  assert.throws(()=>isolatedVesselFinderFrameUrl({imo:'9316359<script>'}),/valid IMO or MMSI/);
});
