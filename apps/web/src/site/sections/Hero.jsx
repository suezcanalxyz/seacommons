import React, { useEffect, useRef, useState } from 'react';
import { SplitText, Magnetic, SpotlightCard, ShinyText, Reveal } from '../../ui/index.js';
import { useReducedMotion } from '../../ui/motion.js';

function useUtcClock() {
  const [t, setT] = useState('--:--:--');
  useEffect(() => {
    const tick = () => setT(new Date().toISOString().slice(11, 19));
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, []);
  return t;
}

export default function Hero() {
  const utc = useUtcClock();
  const reducedMotion = useReducedMotion();
  const videoRef = useRef(null);

  useEffect(() => {
    const el = videoRef.current;
    if (!el) return;
    if (reducedMotion) el.pause();
    else el.play().catch(() => {});
  }, [reducedMotion]);

  return (
    <section id="top" className="hero" aria-labelledby="hero-title">
      <div className="hero__bg" aria-hidden="true">
        <video
          ref={videoRef}
          className="hero__video"
          src="/media/seacommons-hero-loop.mp4"
          autoPlay={!reducedMotion}
          muted
          loop
          playsInline
          preload="auto"
        />
        <div className="hero__grid" />
        <div className="hero__vignette" />
      </div>

      <Reveal className="hero__meta" y={12} duration={600}>
        <p><span className="dot" /> Research prototype / 2026</p>
        <p>Mediterranean test surface</p>
        <p><span className="mono">UTC {utc}</span></p>
      </Reveal>

      <div className="hero__copy">
        <p className="kicker"><ShinyText static>Observe · qualify · simulate · preserve</ShinyText></p>
        <h1 id="hero-title" className="hero__title">
          <SplitText text="Uncertainty-aware fusion of fragmented" as="span" />
          <br />
          <em><SplitText text="maritime distress signals." as="span" delay={520} /></em>
        </h1>
        <Reveal className="hero__intro" delay={200}>
          <p>
            SeaCommons is an open research programme for transforming fragmented maritime
            observations into traceable, contestable and uncertainty-aware analysis.
          </p>
          <div className="hero__actions">
            <Magnetic>
              <a className="btn btn--primary" href="https://live.seacommons.org">
                Open Live <span aria-hidden="true">↗</span>
              </a>
            </Magnetic>
            <a className="btn btn--ghost" href="#research">
              Read the research <span aria-hidden="true">↓</span>
            </a>
          </div>
        </Reveal>
      </div>

      <SpotlightCard as="aside" className="hero__hud" aria-label="Illustrative signal trace">
        <div className="hero__hud-head">
          <span>SIM / TRACE 0041</span>
          <span>MODEL VIEW</span>
        </div>
        <svg className="hero__hud-trace" viewBox="0 0 240 96" role="img" aria-label="Illustrative vessel trajectory with widening uncertainty">
          <defs>
            <linearGradient id="heroCone" x1="0" x2="1">
              <stop offset="0" stopColor="#c7dcf5" stopOpacity="0" />
              <stop offset="1" stopColor="#c7dcf5" stopOpacity=".2" />
            </linearGradient>
          </defs>
          <polygon points="18,76 222,-8 222,32" fill="url(#heroCone)" />
          <path d="M18,76 C78,60 140,36 222,12" fill="none" stroke="var(--sc-brand-dim)" strokeWidth="1.2" strokeDasharray="1 5" strokeLinecap="round" />
          <g fill="none" stroke="var(--sc-brand-dim)" strokeWidth="1.2">
            <polygon transform="translate(18,76) rotate(-24)" points="0,-4 3.2,3 -3.2,3" />
            <polygon transform="translate(92,53) rotate(-24)" points="0,-4 3.2,3 -3.2,3" />
            <polygon transform="translate(158,30) rotate(-24)" points="0,-4 3.2,3 -3.2,3" />
          </g>
          <polygon className="hero__hud-mark" transform="translate(222,12) rotate(-24)" points="0,-5 4,4 -4,4" fill="var(--sc-brand)" stroke="none" />
        </svg>
        <dl>
          <div><dt>Origin</dt><dd>35.511° N<br />12.604° E</dd></div>
          <div><dt>Window</dt><dd>T + 24 H</dd></div>
          <div><dt>Output</dt><dd>Ensemble<br />not certainty</dd></div>
        </dl>
        <p>Illustrative coordinates. No operational incident is represented.</p>
      </SpotlightCard>

      <div className="hero__index" aria-hidden="true">SC / 01</div>
      <a className="hero__scroll" href="#environments" aria-label="Scroll to environments">
        <span />
      </a>
    </section>
  );
}
