import {test} from 'node:test';
import assert from 'node:assert/strict';
import {ngoDocumentCount,domainValues,satelliteDocumentCount} from './domainMetrics.js';
test('documentary NGO counts use exact canonical source aliases, never generic social feeds',()=>{
 assert.equal(ngoDocumentCount({'alarm_phone':3,'SOSMedIntl':2,'Twitter':999,'not_seawatchcrew':100}),5);
 assert.equal(ngoDocumentCount({'Twitter':100}),null);
 assert.equal(ngoDocumentCount({'Alarm Phone':0}),0);
 assert.equal(ngoDocumentCount({'Alarm Phone':'10'}),null);
 assert.equal(satelliteDocumentCount({'GFW':4,'VIIRS VBD':7,'other':500}),11);
});
test('source-specific counts require authorized matching rolling window',()=>{
 const data={lookback_hours:168,source_observations:{by_source:{alarm_phone:7}},parsed_events:{by_source:{alarm_phone:3}},pipeline_status:{sensor_activity:{satellite_observations:12}},counts:{ingested_signals:2}};
 assert.equal(domainValues({source:'operator',data},'7d').ngoRaw,7);
 assert.equal(domainValues({source:'operator',data},'24h').ngoRaw,null);
 assert.equal(domainValues({source:'public',data},'7d').ngoRaw,null);
 assert.equal(domainValues({source:'public',data},'7d').satellite,12);
 assert.equal(domainValues({source:'operator',data},'overall').ngoRaw,null);
});
test('zero is preserved, missing and malformed counters remain unknown',()=>{
 assert.equal(domainValues({data:{sensor_activity:{radio_events:0,ais_fixes:null,satellite_observations:'2'}}},'overall').radioEvents,0);
 assert.equal(domainValues({data:{sensor_activity:{ais_fixes:null}}},'overall').ais,null);
 assert.equal(domainValues({data:{sensor_activity:{satellite_observations:'2'}}},'overall').satellite,null);
});
