import React from 'react';
import { Reveal, Magnetic } from '../../ui/index.js';

export default function Engine() {
  return (
    <section className="section engine">
      <div className="engine__visual" aria-hidden="true">
        <div className="engine__horizon" />
        <div className="engine__grid" />
        <div className="engine__wire"><i /><span /><b /></div>
        <div className="engine__marker engine__marker--1">WIND 07.2 M/S</div>
        <div className="engine__marker engine__marker--2">CURRENT 0.41 M/S</div>
        <div className="engine__marker engine__marker--3">T+12 ENVELOPE</div>
      </div>
      <Reveal className="engine__copy">
        <p className="section-label section-label--light">
          <span>Engine / 006</span>
          <span>Immersive renderer, in development</span>
        </p>
        <h2 className="display">A physically calibrated renderer for the same drift record.</h2>
        <p>
          ENGINE is built on Unreal Engine 5.2: a tiled, physically based ocean surface driven by the
          persisted significant wave height, period and direction, with weather and vessel response
          computed from the same drift-scene schema PLAY reads. It is delivered through browser-based
          WebRTC streaming, so no local installation or dedicated hardware is required on the viewing
          end. The simulation API remains authoritative in every case.
        </p>
        <p>
          Realism work is not complete: vessel buoyancy and motion are still being calibrated against
          reference cases. Access is being designed as accredited and gated from the outset, for
          research and training use rather than open public release.
        </p>
        <dl>
          <div><dt>Renderer</dt><dd>Unreal Engine 5.2<br />Cesium for Unreal georeference</dd></div>
          <div><dt>Delivery</dt><dd>Browser-based<br />WebRTC streaming, no local install</dd></div>
          <div><dt>Boundary</dt><dd>Bounded scenarios only<br />Live distress data is never used here</dd></div>
        </dl>
        <Magnetic strength={0.18}>
          <a className="btn btn--light" href="#environments">Compare the three environments <span aria-hidden="true">↓</span></a>
        </Magnetic>
      </Reveal>
    </section>
  );
}
