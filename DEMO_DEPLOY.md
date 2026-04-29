# SeaCommons Live Demo Deployment

## Overview
This guide prepares SeaCommons for a **live demo with real data** using **free hosting services**:

- **Frontend**: Vercel (free tier) - https://seacommons-demo.vercel.app
- **Backend**: Render.com (free tier) - https://seacommons-api-demo.onrender.com
- **Data Sources**: Open-Meteo (free weather), Copernicus Marine (free ocean currents with account)

## What the Demo Includes

✅ **Real-time weather data** (Open-Meteo API - no key needed)
✅ **Real ocean currents** (Copernicus Marine - credentials in .env.demo)
✅ **Live AIS vessel tracking** (AISStream - key configured)
✅ **Drift simulation** (OpenDrift with real meteorological data)
✅ **SAR alert creation** with trajectory prediction
✅ **Interactive map** with satellite layers (MapTiler)

## Quick Deploy (15 minutes)

### Step 1: Deploy Backend to Render.com

1. Fork/clone repo to your GitHub account
2. Go to [render.com](https://render.com) → New → Blueprint
3. Connect your GitHub repo
4. Render will auto-detect `deploy/render-demo.yaml`
5. Set `CMEMS_PASSWORD` environment variable manually in Render dashboard
6. Deploy (5-10 minutes)

**Result**: `https://seacommons-api-demo.onrender.com`

### Step 2: Deploy Frontend to Vercel

1. Go to [vercel.com](https://vercel.com) → New Project
2. Import your GitHub repo
3. Configure project:
   - **Root Directory**: `apps/web`
   - **Build Command**: `npm run build`
   - **Output Directory**: `dist`
4. Add environment variables:
   - `VITE_API_BASE`: `https://seacommons-api-demo.onrender.com`
   - `VITE_PUBLIC_BASE`: `/`
   - `VITE_MAPTILER_KEY`: `6jaqasGIOmmn1nyMIvPo`
5. Deploy (2-3 minutes)

**Result**: `https://seacommons-demo.vercel.app`

### Step 3: Test the Demo

1. Open frontend URL
2. Check map loads with satellite imagery
3. Verify weather data: click weather layer
4. Check vessels: enable AIS layer
5. Create test alert: POST to `/api/v1/alert` or use UI
6. View drift prediction with real weather/currents

## Alternative: Docker Deployment (Local/VPS)

```bash
# Clone and configure
cd seacommons
cp .env.demo .env

# Deploy with Docker Compose
docker-compose -f deploy/docker-compose.pilot.yml up -d

# Access
# Frontend: http://localhost:3000
# Backend: http://localhost:8000
# API Docs: http://localhost:8000/docs
```

## Demo Features to Showcase

### 1. Live Weather Overlay
- Colored wind vectors on map
- Real-time data from Open-Meteo
- No API key required

### 2. Ocean Currents Simulation
- Real CMEMS data (Mediterranean)
- Visual drift prediction
- 6h/12h/24h uncertainty cones

### 3. Vessel Tracking
- Live AIS via AISStream
- 8+ mock vessels (or real if AISStream connected)
- Proximity alerts to distress signals

### 4. SAR Alert Creation
- Click map → Create alert
- Automatic drift calculation
- Forensic signing (Ed25519)

### 5. Interactive Map
- MapTiler satellite basemap
- Toggle layers (weather, vessels, alerts)
- Responsive design

## Environment Variables Reference

### Backend (.env)
```bash
MOCK=false                    # Enable real data
DEMO_PUBLIC_MODE=true         # Public demo mode
SUEZCANAL_AUTH=false          # No auth for demo
CMEMS_USERNAME=...           # Your Copernicus Marine username
CMEMS_PASSWORD=...           # Your Copernicus Marine password (set in Render)
AISSTREAM_KEY=...            # Your AISStream API key (set in Render)
SUEZCANAL_SIGNING_KEY=...    # Generate with: python -c "from nacl.signing import SigningKey; print(SigningKey.generate().encode().hex())"
```

### Frontend (Vercel env)
```bash
VITE_API_BASE=...            # Backend URL
VITE_PUBLIC_BASE=/           # Root path for Vercel
VITE_MAPTILER_KEY=...        # Satellite imagery
```

## Free Tier Limitations

| Service | Limitation | Workaround |
|---------|------------|------------|
| Render.com | Spins down after 15 min inactivity | First load ~30s delay |
| Vercel | 100GB bandwidth/month | Sufficient for demo |
| Open-Meteo | 10,000 calls/day | Plenty for demo |
| Copernicus Marine | Rate limited | Cached in demo |
| AISStream | Free tier limits | Mock mode fallback |

## Post-Deployment Checklist

- [ ] Backend health check: `https://your-api.onrender.com/health`
- [ ] Frontend loads: `https://your-demo.vercel.app`
- [ ] Weather data appears on map
- [ ] Can create test alert
- [ ] Drift simulation runs with real data
- [ ] Map tiles load (satellite view)

## Troubleshooting

**Backend spins down**: First request after inactivity takes ~30s (Render free tier)

**Weather not loading**: Check Open-Meteo API status (usually very reliable)

**Ocean data missing**: Verify CMEMS credentials in Render dashboard

**Map tiles 403**: MapTiler key may be expired - get new free key at maptiler.com

**CORS errors**: Ensure `VITE_API_BASE` matches backend URL exactly

## Demo Script (5-minute walkthrough)

1. **Intro** (30s): "SeaCommons is an open-source maritime SAR platform"
2. **Map Overview** (1m): Show satellite layer, weather overlay, vessel positions
3. **Create Alert** (1m): Click distress point → Show drift prediction with real weather
4. **Data Sources** (1m): Explain Open-Meteo weather, CMEMS currents, AISStream vessels
5. **Forensics** (1m): Show cryptographic signing of alerts
6. **Q&A** (1m): Address questions

## Support

- GitHub Issues: https://github.com/suezcanalxyz/seacommons/issues
- Documentation: `/docs` folder
- Live Demo: https://seacommons-demo.vercel.app

---

**Ready to deploy?** Follow Step 1 and Step 2 above!
