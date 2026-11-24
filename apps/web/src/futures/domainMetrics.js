// Counts describe documentary records, not people, vessels, incidents or coverage.
const NGO_KEYS=new Set(['alarmphone','sosmediterranee','sosmedintl','msf','msfsea','seawatch','seawatchcrew','openarms','openarmsfund','proactivaopenarms','soshumanity','seaeye','seaeyeorg','resqship','emergency','emergencyong']);
const normalize=s=>String(s).normalize('NFKD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]/g,'');
export const validCount=n=>Number.isSafeInteger(n)&&n>=0?n:null;
export function recognizedSourceCount(map,keys){
 if(!map||typeof map!=='object'||Array.isArray(map))return null;
 const found=Object.entries(map).filter(([key])=>keys.has(normalize(key)));
 if(!found.length||found.some(([,n])=>validCount(n)===null))return null;
 const sum=found.reduce((total,[,n])=>total+n,0);
 return validCount(sum);
}
export const ngoDocumentCount=map=>recognizedSourceCount(map,NGO_KEYS);
export const satelliteDocumentCount=map=>recognizedSourceCount(map,new Set(['gfw','viirsvbd']));
export function domainValues(snapshot,period){
 const data=snapshot?.data;
 const sensors=period==='overall'?data?.sensor_activity:data?.pipeline_status?.sensor_activity;
 const protectedOverview=period!=='overall'&&snapshot?.source==='operator'&&data?.lookback_hours===(period==='7d'?168:24);
 return {
  ais:validCount(sensors?.ais_fixes),radioBursts:validCount(sensors?.radio_bursts),radioEvents:validCount(sensors?.radio_events),
  satellite:validCount(sensors?.satellite_observations),
  sources:validCount(period==='overall'?sensors?.source_names:sensors?.active_source_names),
  ngoRaw:protectedOverview?ngoDocumentCount(data?.source_observations?.by_source):null,
  ngoNormalized:protectedOverview?ngoDocumentCount(data?.parsed_events?.by_source):null,
  satelliteRaw:protectedOverview?satelliteDocumentCount(data?.source_observations?.by_source):null,
  satelliteNormalized:protectedOverview?satelliteDocumentCount(data?.parsed_events?.by_source):null,
  partnerSignals:protectedOverview?validCount(data?.counts?.ingested_signals):null,
 };
}
