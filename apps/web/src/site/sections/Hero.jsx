import React, { useEffect, useRef, useState } from 'react';
import { SplitText, Magnetic, ShinyText, Reveal } from '../../ui/index.js';
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

      <a className="hero__scroll" href="#environments" aria-label="Scroll to environments">
        <span />
      </a>
    </section>
  );
}
