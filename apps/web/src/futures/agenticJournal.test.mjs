import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
const read=name=>JSON.parse(readFileSync(new URL(name,import.meta.url),'utf8'));
const journal=read('./strategyJournal.json');
const runs=read('./agenticRuns.json');
const categories=['engineering','data','ui','docs','strategy'];
const bilingual=r=>['it','en'].every(l=>typeof r[l]?.title==='string'&&r[l].title.trim()&&typeof r[l]?.body==='string'&&r[l].body.trim());
test('journal is deduplicated, dated, bilingual and links verified release states to evidence',()=>{
 assert.equal(new Set(journal.map(r=>r.commit)).size,journal.length);
 for(const r of journal){
  assert.match(r.commit,/^[0-9a-f]{7,40}$/);
  assert.match(r.date,/^\d{4}-\d{2}-\d{2}$/);
  assert.ok(Number.isFinite(Date.parse(r.date)));
  assert.ok(categories.includes(r.category));
  assert.ok(['deployment_ready','commit_verified'].includes(r.status));
  assert.ok(['manual_backfill','scheduled','manual'].includes(r.origin));
  assert.ok(bilingual(r));
  if(r.status==='deployment_ready')assert.match(r.deployment,/^dpl_[A-Za-z0-9]+$/);
  else assert.equal(r.deployment,null);
 }
});
test('run register distinguishes manual work from scheduled work',()=>{
 assert.equal(new Set(runs.map(r=>r.id)).size,runs.length);
 for(const r of runs){
  assert.ok(r.id&&Number.isFinite(Date.parse(r.at)));
  assert.ok(['manual','scheduled'].includes(r.origin));
  assert.ok(['verified','unverified'].includes(r.status));
  assert.ok(bilingual(r));
  if(r.origin==='scheduled'&&r.status==='verified')assert.ok(r.executionRef,'Verified scheduled runs require an execution reference');
 }
});
