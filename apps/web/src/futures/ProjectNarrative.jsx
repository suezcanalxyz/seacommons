import React from 'react';
import {narrative,softwareSurfaces} from './projectNarrative.js';
import './project-narrative.css';
export default function ProjectNarrative({section,lang,navigate}){
 const content=narrative[section];
 const t=(it,en)=>lang==='it'?it:en;
 if(!content)return null;
 return <section className="project-narrative" aria-labelledby="project-narrative-title">
 <header><span className="future-eyebrow">{t('DOSSIER PROGETTUALE / SEACOMMONS','PROJECT DOSSIER / SEACOMMONS')}</span><h2 id="project-narrative-title">{content.title[lang]}</h2><p className="project-narrative-lead">{content.lead[lang]}</p></header>
 {section==='brief'&&<div className="project-narrative-facts"><div><span>{t('Ambito','Scope')}</span><strong>{t('Ricerca marittima','Maritime research')}</strong></div><div><span>{t('Area di interesse','Area of interest')}</span><strong>{t('Mediterraneo','Mediterranean')}</strong></div><div><span>{t('Fase attuale','Current phase')}</span><strong className="project-narrative-status">{t('Pilot software','Software pilot')}</strong></div></div>}
 {section==='software'&&<div className="project-surface-grid">{softwareSurfaces.map(s=><article key={s.name}>{s.image&&<img src={s.image} alt={s.name+' — '+t('visualizzazione del software','software visualisation')} loading="lazy"/>}<div><span className="future-pill future-pill--neutral">{s.name}</span><p>{s.desc[lang]}</p>{s.url?<a href={s.url} target="_blank" rel="noreferrer">{t('Apri interfaccia','Open interface')} ↗</a>:<button type="button" onClick={()=>navigate(s.view)}>{t('Esplora','Explore')} ↗</button>}</div></article>)}</div>}
 <div className="project-narrative-blocks">{content.blocks.map((b,i)=><article className="project-narrative-block" key={b.title.en}><span className="project-narrative-index" aria-hidden="true">{String(i+1).padStart(2,'0')}</span><div><h3>{b.title[lang]}</h3>{b.body.map((s,j)=><p key={j}>{s[lang]}</p>)}</div></article>)}</div>
 </section>
}
