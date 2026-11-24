import assert from 'node:assert/strict';
import {test} from 'node:test';
import {narrative,softwareSurfaces} from './projectNarrative.js';
const pair=x=>['it','en'].every(k=>typeof x[k]==='string'&&x[k].trim().length>0);
test('project dossier includes substantive paired Italian and English sections',()=>{
 for(const id of ['brief','software','applications','governance']){
  const s=narrative[id];assert.ok(pair(s.title)&&pair(s.lead));
  assert.ok(s.blocks.length>=4);
  for(const b of s.blocks){assert.ok(pair(b.title));assert.ok(b.body.length);for(const q of b.body)assert.ok(pair(q));}
  for(const lang of ['it','en'])assert.ok(s.blocks.flatMap(b=>b.body.map(q=>q[lang])).join(' ').split(/\s+/).length>=180);
 }
});
test('software overview identifies four interfaces with bilingual descriptions',()=>{
 assert.deepEqual(softwareSurfaces.map(s=>s.name),['LIVE','PLAY','FUTURES','API']);
 for(const s of softwareSurfaces){assert.ok(pair(s.desc));assert.ok(s.url||s.view);}
});
