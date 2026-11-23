import React from 'react';

export default function Hero() {
 return <section id="top" className="product-hero" aria-labelledby="product-hero-title">
   <div className="product-hero__top"><span>SEA COMMONS / MARITIME RESEARCH</span><a href="/docs">How it works ↗</a></div>
   <div className="product-hero__frame"><img src="/visualizations/live-visual.png" alt="SeaCommons LIVE visualization showing vessel signals, sensor layers and maritime events" fetchPriority="high"/><div className="product-hero__shade"/><div className="product-hero__content"><span className="product-hero__eyebrow"><i/> LIVE OBSERVATIONS / PILOT</span><h1 id="product-hero-title">See the sea<br/><em>differently.</em></h1><p>Vessel movements. Maritime incidents. Evidence you can explore.</p><div className="product-hero__actions"><a className="product-hero__primary" href="https://live.seacommons.org"><span>Explore LIVE</span><span aria-hidden="true">↗</span></a><a href="https://play.seacommons.org"><span>Explore PLAY</span><span aria-hidden="true">↗</span></a></div></div><div className="product-hero__caption">SEACOMMONS VISUALIZATION / ILLUSTRATIVE RESEARCH VIEW</div></div>
 </section>;
}
