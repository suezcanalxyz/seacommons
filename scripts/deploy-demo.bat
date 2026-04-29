@echo off
REM ==============================================================================
REM SeaCommons Demo Deployment Script (Windows)
REM ==============================================================================
REM Deploys to Vercel (frontend) + Render.com (backend) - FREE
REM ==============================================================================

echo.
echo ╔════════════════════════════════════════════════════════════════╗
echo ║                                                                ║
echo ║         🌊 SEACOMMONS DEMO DEPLOYMENT 🌊                     ║
echo ║                                                                ║
echo ║         Free hosting: Vercel + Render.com                    ║
echo ║                                                                ║
echo ╚════════════════════════════════════════════════════════════════╝
echo.

echo [PREREQUISITES CHECK]
echo.
where git >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ Git not found. Install from: https://git-scm.com/
    pause
    exit /b 1
)
echo ✅ Git found

where npm >nul 2>&1
if %errorlevel% neq 0 (
    echo ❌ npm not found. Install Node.js from: https://nodejs.org/
    pause
    exit /b 1
)
echo ✅ npm found

echo.
echo [STEP 1/3] Backend Preparation
echo ─────────────────────────────────
echo.
echo 📋 Render.com Backend Deployment:
echo    1. Go to https://render.com
echo    2. Click "New +" → "Blueprint"
echo    3. Connect your GitHub repository
echo    4. Render will detect: deploy/render-demo.yaml
echo    5. Add CMEMS_PASSWORD in environment variables
echo    6. Click "Apply Blueprint"
echo.
echo ⏳ Expected URL: https://seacommons-api-demo.onrender.com
echo.
pause

echo.
echo [STEP 2/3] Frontend Deployment
echo ─────────────────────────────────
echo.
echo 📋 Vercel Frontend Deployment:
echo    1. Go to https://vercel.com
echo    2. Click "Add New..." → "Project"
echo    3. Import your GitHub repository
echo    4. Configure:
echo       - Root Directory: apps/web
echo       - Build Command: npm run build
echo       - Output Directory: dist
echo    5. Add Environment Variables:
echo       - VITE_API_BASE: https://seacommons-api-demo.onrender.com
echo       - VITE_PUBLIC_BASE: /
echo       - VITE_MAPTILER_KEY: 6jaqasGIOmmn1nyMIvPo
echo    6. Click "Deploy"
echo.
echo ⏳ Expected URL: https://seacommons-demo.vercel.app
echo.
pause

echo.
echo [STEP 3/3] Verification
echo ─────────────────────────────────
echo.
echo 🧪 Test your deployment:
echo.
echo    1. Backend Health Check:
echo       curl https://seacommons-api-demo.onrender.com/health
echo.
echo    2. Frontend Loads:
echo       Open https://seacommons-demo.vercel.app
echo.
echo    3. Check Features:
echo       ✓ Weather overlay (real Open-Meteo data)
echo       ✓ Vessel tracking (AISStream)
echo       ✓ Create test alert
echo       ✓ Drift simulation with real weather
echo.
echo ✅ Demo deployment complete!
echo.
echo 📖 Full documentation: DEMO_DEPLOY.md
echo.
pause
