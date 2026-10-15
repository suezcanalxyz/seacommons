import assert from 'node:assert/strict';
import {test} from 'node:test';
import {glossary,tokenizeGlossary} from './glossary.js';
test('recognises domain terms, preserves text and does not match substrings',()=>{
 const s='AIS, OIDC and VM are not hypotheses. RAISE is unrelated.';
 const x=tokenizeGlossary(s);
 assert.equal(x.map(t=>t.text).join(''),s);
 for(const word of ['AIS','OIDC','VM','hypotheses'])assert.ok(x.some(t=>t.term===word));
 assert.equal(tokenizeGlossary('AISCLONE RAISE').some(t=>t.term),false);
 assert.match(glossary.AIS,/does not prove/i);
});
