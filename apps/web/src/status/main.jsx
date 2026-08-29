import React from 'react';
import { createRoot } from 'react-dom/client';
import '../ui/ui.css';
import './status.css';
import StatusApp from './StatusApp.jsx';

const el = document.getElementById('status-root');
if (el) createRoot(el).render(<React.StrictMode><StatusApp /></React.StrictMode>);
