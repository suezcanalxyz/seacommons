import React, { useEffect, useMemo, useRef, useState } from 'react';

import { pixelStreamingEnvelope } from '../simulation/sceneAdapter.js';

export default function UnrealPixelStream({ active, streamUrl, scenario }) {
  const frameRef = useRef(null);
  const [status, setStatus] = useState('waiting for stream');
  const envelope = useMemo(() => {
    if (!scenario) return null;
    try { return pixelStreamingEnvelope(scenario); } catch { return null; }
  }, [scenario]);
  const streamOrigin = useMemo(
    () => new URL(streamUrl, window.location.origin).origin,
    [streamUrl],
  );

  function publishScene() {
    if (!envelope || !frameRef.current?.contentWindow) return;
    frameRef.current.contentWindow.postMessage(envelope, streamOrigin);
    setStatus(`scene ${scenario.scenario_id.slice(0, 8)} sent`);
  }

  useEffect(() => {
    if (!active || !envelope) return;
    publishScene();
  }, [active, envelope]);

  useEffect(() => {
    const handleMessage = (event) => {
      if (event.origin !== streamOrigin) return;
      if (event.data?.type === 'seacommons.scene.ready') {
        setStatus(`Unreal ready · ${String(event.data.scenario_id || '').slice(0, 8)}`);
      }
    };
    window.addEventListener('message', handleMessage);
    return () => window.removeEventListener('message', handleMessage);
  }, [streamOrigin]);

  if (!active) return null;
  return (
    <section className="play-unreal" aria-label="Unreal Engine Pixel Streaming">
      <iframe
        ref={frameRef}
        src={streamUrl}
        title="SeaCommons Unreal Engine"
        allow="autoplay; fullscreen; gamepad; microphone"
        onLoad={() => { setStatus('stream connected'); publishScene(); }}
      />
      <div className="play-unreal__status">UNREAL / PIXEL STREAMING · {status}</div>
    </section>
  );
}
