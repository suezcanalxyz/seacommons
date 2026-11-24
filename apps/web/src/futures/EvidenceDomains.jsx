import React,{useState} from 'react';
import {useLocale} from './locale.jsx';
import {domainValues} from './domainMetrics.js';
const groups=[
 {id:'ngo',it:'ONG e fonti umanitarie',en:'NGOs and humanitarian sources',rows:[
 ['ngoRaw','Record originali da fonti ONG','Original NGO source records','Somma dei record di fonti riconosciute dal registro delle identità, comprese le comunicazioni pubbliche e gli allegati. Le fonti non attribuibili sono escluse.','Sum of records from recognised source identities, including public communications and attachments. Unattributed sources are excluded.'],
 ['ngoNormalized','Record ONG normalizzati','Normalized NGO records','Record trasformati nello schema Intel, non numero di soccorsi o persone.','Records converted to the Intel schema, not a count of rescues or people.']
 ],note:['Il totale storico per ONG non è esposto dall’API pubblica. Le finestre recenti richiedono accesso autorizzato; il conteggio riguarda soltanto le identità riconosciute presenti nella risposta, non tutte le attività delle ONG.','The public API does not expose historical totals by NGO. Recent windows require authorized access; counts cover only recognised identities returned by the service, not all NGO activity.']},
 {id:'satellite',it:'Satelliti',en:'Satellite',rows:[
 ['satellite','Osservazioni satellitari','Satellite observations','Record effettivamente conservati o acquisiti nel periodo. Non equivalgono a identificazioni confermate.','Stored or discovered observation records, not confirmed identifications.'],
 ['satelliteRaw','Record originali GFW / VIIRS','GFW / VIIRS original records','Sottoinsieme documentale identificato dai nomi canonici delle fonti.','Documentary subset identified by canonical source names.'],
 ['satelliteNormalized','Record GFW / VIIRS normalizzati','Normalized GFW / VIIRS records','Record elaborati dalle fonti riconosciute. Non sommare alle osservazioni satellitari.','Processed records from recognised sources. Do not add to satellite observations.']
 ],note:['Il conteggio misura la disponibilità di record, non la percentuale di mare osservata, la risoluzione delle immagini o l’accuratezza di un rilevamento.','Counts measure record availability, not sea coverage, image resolution or detection accuracy.']},
 {id:'radio',it:'Radio',en:'Radio',rows:[
 ['radioBursts','Impulsi ricevuti','Received bursts','Segnali radio acquisiti prima della validazione.','Signals captured before validation.'],
 ['radioEvents','Eventi radio strutturati','Structured radio events','Record decodificati e trasformati in eventi; non costituiscono automaticamente richieste di soccorso.','Decoded structured records; not automatically distress calls.']
 ],note:['I due conteggi hanno popolazioni e riferimenti temporali distinti; il loro rapporto non è un tasso di decodifica validato.','The two counts use different populations and clocks; their ratio is not a validated decoding rate.']},
 {id:'ais',it:'AIS',en:'AIS',rows:[['ais','Record di posizione AIS','AIS position records','Record di osservazione con timestamp di fonte, non navi uniche. Il totale può essere stimato.','Source-timestamped observation records, not distinct vessels. The overall inventory may be estimated.']],note:['L’assenza di osservazioni non distingue da sola perdita di ricezione, copertura assente o mancata trasmissione.','Missing observations alone do not distinguish reception loss, missing coverage or absent transmissions.']},
 {id:'sources',it:'Fonti e contributi',en:'Sources and contributions',rows:[
 ['sources','Identificativi di fonte distinti','Distinct source identifiers','Fonti rappresentate nelle osservazioni grezze del periodo. Non equivalgono a origini indipendenti.','Source identifiers represented in raw observations. They are not necessarily independent origins.'],
 ['partnerSignals','Segnalazioni da connettori','Connector signals','Record ricevuti da connettori autorizzati, non casi verificati.','Records received from authorized connectors, not verified cases.']
 ],note:['Le fonti con frequenze di acquisizione differenti non sono confrontabili direttamente per qualità. I record dei connettori richiedono accesso autorizzato.','Sources with different collection frequencies cannot be compared directly for quality. Connector counts require authorized access.']}
];
export default function EvidenceDomains({snapshots}){
 const lang=useLocale(),it=lang==='it',tr=(a,b)=>it?a:b;
 const [selected,setSelected]=useState('ngo');
 const g=groups.find(x=>x.id===selected);
 const periods=['24h','7d','overall'];
 const fmt=new Intl.NumberFormat(it?'it-IT':'en-GB');
 const time=new Intl.DateTimeFormat(it?'it-IT':'en-GB',{dateStyle:'short',timeStyle:'short'});
 const values=snapshots.map((s,i)=>domainValues(s,periods[i]));
 const available=g.rows.reduce((n,[key])=>n+values.filter(v=>v[key]!==null).length,0);
 const expected=g.rows.length*periods.length;
 const busy=snapshots.some(s=>s.loading);
 const label=s=>s.loading?tr('Caricamento','Loading'):s.source==='operator'?tr('API autorizzata','Authorized API'):s.source==='public-aggregate'?tr('Archivio pubblico','Public inventory'):s.source==='public'?tr('Aggregato pubblico','Public aggregate'):tr('Non disponibile','Unavailable');
 return <section className="intel-compare">
 <header className="intel-compare-head"><div><h1>{tr('Fonti e domini di ricerca','Research sources and domains')}</h1><p>{tr('Misurazioni documentali per categoria, con le tre finestre a confronto.','Documentary measurements by category across the three time windows.')}</p></div><button type="button" disabled={snapshots.some(s=>s.loading)} onClick={()=>snapshots.forEach(s=>s.refresh())}>{tr('Aggiorna','Refresh')}</button></header>
 <nav className="futures-switcher" aria-label={tr('Domini','Domains')}>{groups.map(x=><button key={x.id} type="button" aria-pressed={selected===x.id} onClick={()=>setSelected(x.id)}>{x[lang]||x.en}</button>)}</nav>
 <div className="intel-domain-title"><h2>{g[lang]||g.en}</h2><span className={'future-pill future-pill--'+(busy?'neutral':available===expected?'good':available?'warn':'neutral')}>{busy?tr('Aggiornamento','Refreshing'):available+' / '+expected+' '+tr('misure disponibili','available measures')}</span></div>
 {!busy&&available===0&&<p className="intel-domain-empty" role="status">{tr('Nessuna misurazione disponibile per questa categoria. Verifica accesso e disponibilità delle fonti; i campi vuoti non indicano assenza di attività.','No measurements are available for this category. Check access and source availability; empty fields do not imply absence of activity.')}</p>}
 <table className="intel-matrix"><thead><tr><th>{tr('Misurazione','Measure')}</th><th>24h</th><th>{tr('7 giorni','7 days')}</th><th>{tr('Totale','Overall')}</th></tr></thead><tbody>{g.rows.map(([key,titleIt,titleEn,helpIt,helpEn])=><tr key={key}><th scope="row"><details><summary>{tr(titleIt,titleEn)}</summary><p>{tr(helpIt,helpEn)}</p></details></th>{values.map((v,i)=>{const n=v[key],estimate=i===2&&snapshots[i].data?.estimated_fields?.includes({ais:'ais_fixes',sources:'active_source_names'}[key]);return <td key={periods[i]} className={n===null?'is-missing':''}>{n===null?snapshots[i].loading?'…':'—':(estimate?'≈ ':'')+fmt.format(n)}</td>})}</tr>)}</tbody><tfoot><tr><th>{tr('Provenienza','Provenance')}</th>{snapshots.map((s,i)=><td key={periods[i]}><small><span className={'future-pill future-pill--'+(s.loading?'neutral':s.source?'good':'neutral')}>{label(s)}</span></small><small>{s.data?.generated_at&&Number.isFinite(Date.parse(s.data.generated_at))?time.format(new Date(s.data.generated_at)):'—'}</small></td>)}</tr></tfoot></table>
 <p className="intel-domain-note">{g.note[it?0:1]}</p><p className="intel-domain-note">{tr('— non disponibile o non attribuibile; … caricamento; ≈ stima. I conteggi non sono additivi.','— unavailable or unattributable; … loading; ≈ estimate. Counts are not additive.')}</p>
 </section>
}
