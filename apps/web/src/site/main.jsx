import React from 'react';
import { createRoot } from 'react-dom/client';
import '../ui/ui.css';
import './site.css';
import SiteApp from './SiteApp.jsx';

const el = document.getElementById('site-root');
if (el) createRoot(el).render(<React.StrictMode><SiteApp /></React.StrictMode>);
