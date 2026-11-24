import {L} from './locale.jsx';
import React from 'react';
import GlossaryText from './GlossaryText.jsx';
export default function KeyFigures({items,label='Key figures'}){
 return <section className="future-keyfigures" aria-label={label}>{items.map(({value,title,detail})=><div key={title} className="future-keyfigure"><span><L>{title}</L></span><strong className={value==null?'is-missing':''}><L>{value==null?'Unavailable':value}</L></strong><p><GlossaryText>{detail}</GlossaryText></p></div>)}</section>
}
