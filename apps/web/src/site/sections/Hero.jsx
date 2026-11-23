import React from 'react';

export default function Hero() {
 return <section id="top" className="product-hero" aria-labelledby="product-hero-title">
   <div className="product-hero__top"><span>SEA COMMONS / MARITIME RESEARCH</span><a href="/docs">How it works ↗</a></div>
   <div className="product-hero__frame"><video className="product-hero__video" autoPlay muted loop playsInline preload="metadata" poster="/visualizations/live-visual.png" aria-label="SeaCommons maritime visualization in motion"><source src="/media/seacommons-hero-loop.mp4" type="video/mp4"/></video><div className="product-hero__shade"/><div className="product-hero__content"><span className="product-hero__eyebrow"><i/> LIVE OBSERVATIONS / PILOT</span><h1 id="product-hero-title">The sea,<br/><em>in focus.</em></h1><p>Vessels. Incidents. Evidence.</p><div className="product-hero__actions"><a className="product-hero__primary" href="https://live.seacommons.org"><span>Explore LIVE</span><span aria-hidden="true">↗</span></a><a href="https://play.seacommons.org"><span>Explore PLAY</span><span aria-hidden="true">↗</span></a></div></div><div className="product-hero__caption">SEACOMMONS VISUALIZATION / ILLUSTRATIVE RESEARCH VIEW</div></div>
 </section>;
}
