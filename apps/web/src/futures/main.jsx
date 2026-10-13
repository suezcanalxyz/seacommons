import React from 'react';
import { createRoot } from 'react-dom/client';
import { AuthGate } from '../auth.jsx';
import './futures.css';
import FuturesApp from './FuturesApp.jsx';

const root = document.getElementById('futures-root');

if (root) {
  createRoot(root).render(
    <React.StrictMode>
      <AuthGate>
        <FuturesApp />
      </AuthGate>
    </React.StrictMode>,
  );
}

if ('serviceWorker' in navigator && window.location.hostname === 'futures.seacommons.org') {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/futures-sw.js', { scope: '/' }).catch(() => {});
  });
}
