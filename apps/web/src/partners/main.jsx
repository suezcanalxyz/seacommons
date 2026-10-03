import { createRoot } from 'react-dom/client';
import '../ui/ui.css';
import './partners.css';
import PartnerGate from './PartnerGate.jsx';
import Workspace from './Workspace.jsx';

createRoot(document.getElementById('partner-root')).render(<PartnerGate><Workspace /></PartnerGate>);
