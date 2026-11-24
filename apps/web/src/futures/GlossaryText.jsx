import React,{useState} from 'react';
import {glossary,tokenizeGlossary} from './glossary.js';
import glossaryIt from './glossary.it.json';
import {useLocale,translate} from './locale.jsx';
const aliases={'record normalizzati':'normalized records','criteri di accettazione':'acceptance criteria','qualità dei dati':'data quality','telemetria':'telemetry','provenienza':'provenance','corroborazione':'corroboration','ipotesi':'hypotheses','indicatore derivato':'derived cue','osservazione grezza':'raw observation','evento normalizzato':'normalized event','record conservati':'retained records','finestra mobile':'rolling window','gateway periferico':'edge gateway','catena di evidenze':'evidence chain'};
const italianPattern=new RegExp('(?<![\\p{L}\\p{N}])('+Object.keys(aliases).sort((a,b)=>b.length-a.length).join('|')+')(?![\\p{L}\\p{N}])','giu');
function tokenizeItalian(value){return tokenizeGlossary(value).flatMap(x=>{if(x.term)return [x];const out=[];let cursor=0;for(const m of x.text.matchAll(italianPattern)){if(m.index>cursor)out.push({text:x.text.slice(cursor,m.index),term:null});out.push({text:m[0],term:aliases[m[0].toLowerCase()]});cursor=m.index+m[0].length}if(cursor<x.text.length)out.push({text:x.text.slice(cursor),term:null});return out;})}
function Term({value,term}){
 const [open,setOpen]=useState(false);
 const lang=useLocale();
 const id=React.useId();
 return <span className={'future-educational-term'+(open?' is-open':'')}>
 <button type="button" className="future-educational-trigger" aria-expanded={open} aria-describedby={id} onClick={()=>setOpen(x=>!x)} onKeyDown={e=>{if(e.key==='Escape')setOpen(false)}} onBlur={()=>setOpen(false)}>{value}</button>
 <span role="tooltip" id={id} className="future-educational-tooltip">{lang==='it'?glossaryIt[term]||glossary[term]:glossary[term]}</span>
 </span>;
}
export default function GlossaryText({children}){
 const lang=useLocale();
 if(typeof children!=='string')return children??null;
 const value=translate(children,lang);
 return <>{(lang==='it'?tokenizeItalian(value):tokenizeGlossary(value)).map((x,i)=>x.term?<Term value={x.text} term={x.term} key={i}/>:<React.Fragment key={i}>{x.text}</React.Fragment>)}</>;
}
