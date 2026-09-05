import React from 'react';
import { createRoot } from 'react-dom/client';

import PlayTimeline from './features/play/PlayTimeline.jsx';
import './features/play/play.css';

function playApiBase() {
  const envBase = import.meta.env.VITE_API_BASE;
  if (envBase) return envBase.replace(/\/$/, '');
  const { hostname, origin, protocol } = window.location;
  if (hostname === 'localhost' || hostname === '127.0.0.1') {
    return `${protocol}//${hostname}:8000`;
  }
  return origin;
}

createRoot(document.getElementById('root')).render(
  <PlayTimeline apiBase={playApiBase()} />,
);
