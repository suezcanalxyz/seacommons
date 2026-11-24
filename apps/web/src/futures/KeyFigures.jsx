import React from 'react';
import GlossaryText from './GlossaryText.jsx';
export default function KeyFigures({items,label='Key figures'}){
 return <section className="future-keyfigures" aria-label={label}>{items.map(({value,title,detail})=><div key={title} className="future-keyfigure"><span>{title}</span><strong className={value==null?'is-missing':''}>{value==null?'Unavailable':value}</strong><p><GlossaryText>{detail}</GlossaryText></p></div>)}</section>
}
