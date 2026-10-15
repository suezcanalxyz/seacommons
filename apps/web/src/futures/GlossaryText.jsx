import React,{useState} from 'react';
import {glossary,tokenizeGlossary} from './glossary.js';
function Term({value,term}){
 const [open,setOpen]=useState(false);
 const id=React.useId();
 return <span className={'future-educational-term'+(open?' is-open':'')}>
 <button type="button" className="future-educational-trigger" aria-expanded={open} aria-describedby={id} onClick={()=>setOpen(x=>!x)} onKeyDown={e=>{if(e.key==='Escape')setOpen(false)}} onBlur={()=>setOpen(false)}>{value}</button>
 <span role="tooltip" id={id} className="future-educational-tooltip">{glossary[term]}</span>
 </span>;
}
export default function GlossaryText({children}){
 if(typeof children!=='string')return children??null;
 return <>{tokenizeGlossary(children).map((x,i)=>x.term?<Term value={x.text} term={x.term} key={i}/>:<React.Fragment key={i}>{x.text}</React.Fragment>)}</>;
}
