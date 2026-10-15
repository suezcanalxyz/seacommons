export const glossary={
 AIS:'Automatic Identification System: vessel identity and position broadcasts. Missing reception does not prove concealment.',
 GNSS:'Satellite navigation and timing systems, including GPS and Galileo.',
 GPS:'Satellite positioning system. Precision depends on device, environment and corrections.',
 SAR:'Search and Rescue; a SAR-related observation does not confirm a rescue action.',
 OSINT:'Open-source intelligence: systematic research using accessible sources with provenance and verification.',
 API:'Application Programming Interface: a documented interface for exchanging structured data.',
 OIDC:'OpenID Connect, a standard for authenticated user sign-in and identity verification.',
 VM:'Virtual machine: a software-defined computer using shared physical infrastructure.',
 OCPU:'Oracle computing unit; an eighth of an OCPU is not a full CPU.',
 SDR:'Software-defined radio: radio-frequency signal reception and decoding in software.',
 DSC:'Digital Selective Calling, structured maritime safety signalling rather than voice audio.',
 NAVTEX:'Maritime safety information service transmitted on medium-frequency channels.',
 VHF:'Very high frequency radio band used in maritime communications and AIS.',
 LoRa:'Low-power radio that needs a reachable gateway, not reliable for unsupported offshore coverage.',
 LoRaWAN:'Networking protocol for low-power radio devices via gateways.',
 IoT:'Internet of Things: connected devices measuring real-world conditions.',
 telemetry:'A sensor or device reporting readings, location and operational health.',
 provenance:'Trace of a record origin, acquisition time, changes and sources.',
 corroboration:'Support from independent evidence sources, not copies of the same original report.',
 hypothesis:'An explanation being tested, not a confirmed finding.',
 hypotheses:'Provisional explanations under investigation, not confirmed incidents.',
 'derived cue':'An algorithmic pattern indicating something to examine, not proof.',
 'raw observation':'Original incoming source record before normalization.',
 'normalized event':'A source record translated into a common format for comparison.',
 'retained records':'Data still in storage today; previously deleted records are excluded.',
 'rolling window':'A period counted backwards from now, such as the latest 24 hours.',
 'edge gateway':'Local device that stores observations temporarily and securely forwards them.',
 'data lineage':'Traceable history of sources, processing transformations and outputs.',
 'evidence chain':'Series of sources and reasoning supporting or challenging an assessment.',
 'Always Free':'Cloud resources free within published region, capacity and usage quotas.'
};
const ordered=Object.keys(glossary).sort((a,b)=>b.length-a.length);
const quote=s=>s.replace(/[.*+?^$(){}|[\]\\]/g,'\\$&');
const pattern=new RegExp('(?<![\\p{L}\\p{N}])('+ordered.map(quote).join('|')+')(?![\\p{L}\\p{N}])','giu');
export function tokenizeGlossary(value){
 if(typeof value!=='string'||!value)return [{text:value??'',term:null}];
 const out=[];let cursor=0;
 for(const m of value.matchAll(pattern)){
  if(m.index>cursor)out.push({text:value.slice(cursor,m.index),term:null});
  out.push({text:m[0],term:ordered.find(s=>s.toLowerCase()===m[0].toLowerCase())});
  cursor=m.index+m[0].length;
 }
 if(cursor<value.length)out.push({text:value.slice(cursor),term:null});
 return out.length?out:[{text:value,term:null}];
}
