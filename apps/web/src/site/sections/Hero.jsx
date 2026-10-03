import React, { useEffect, useRef } from 'react';
import { SplitText, Magnetic, ShinyText, Reveal } from '../../ui/index.js';
import { useReducedMotion } from '../../ui/motion.js';

export default function Hero() {
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
        <div className="hero__grain" />
        <div className="hero__vignette" />
      </div>

      <div className="hero__copy">
        <p className="kicker"><ShinyText static>Humanitarian incidents · Maritime investigations</ShinyText></p>
        <h1 id="hero-title" className="hero__title">
          <SplitText text="Maritime intelligence" as="span" />
          <br />
          <em><SplitText text="with traceable evidence." as="span" delay={520} /></em>
        </h1>
        <Reveal className="hero__intro" delay={200}>
          <p>
            SeaCommons is open-source research infrastructure for humanitarian incidents and
            maritime investigations. It connects public reports with vessel, radio, satellite
            and environmental evidence to build case records from incomplete evidence,
            preserving source lineage and uncertainty.
          </p>
          <div className="hero__actions">
            <Magnetic>
              <a className="btn btn--primary" href="https://live.seacommons.org">
                Open Live <span aria-hidden="true">↗</span>
              </a>
            </Magnetic>
            <a className="btn btn--ghost" href="/partners.html">
              Partner workspace <span aria-hidden="true">→</span>
            </a>
          </div>
        </Reveal>
      </div>

      <a className="hero__scroll" href="#humanitarian" aria-label="Scroll to Humanitarian and Maritime overview">
        <span />
      </a>
    </section>
  );
}
