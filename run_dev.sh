#!/usr/bin/env bash
# SuezCanal — local development launcher
# Starts backend API + watch frontend in parallel with live reload
# AGPL-3.0-or-later

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Colour output ──────────────────────────────────────────────────────────────
RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[0;33m'; BLU='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLU}[seacommons]${NC} $*"; }
ok()    { echo -e "${GRN}[seacommons]${NC} $*"; }
warn()  { echo -e "${YLW}[seacommons]${NC} $*"; }
error() { echo -e "${RED}[seacommons]${NC} $*" >&2; }

# ── Load .env if present ───────────────────────────────────────────────────────
if [[ -f "${ROOT}/.env" ]]; then
  set -a; source "${ROOT}/.env"; set +a
  ok ".env loaded"
else
  warn ".env not found — using defaults (MOCK=true, no MapTiler key)"
fi

export MOCK="${MOCK:-true}"
export DATABASE_URL="${DATABASE_URL:-sqlite+aiosqlite:///./suezcanal.db}"
export REDIS_URL="${REDIS_URL:-}"
export LOG_LEVEL="${LOG_LEVEL:-info}"

# ── Backend: FastAPI via uvicorn ───────────────────────────────────────────────
start_backend() {
  info "Starting backend on http://localhost:8000 (MOCK=${MOCK})"
  cd "${ROOT}"
  if ! command -v uvicorn &>/dev/null; then
    error "uvicorn not found. Run: pip install -e '.[dev]'"
    exit 1
  fi
  uvicorn core.api.main:app \
    --host 0.0.0.0 --port 8000 \
    --reload --reload-dir core \
    --log-level "${LOG_LEVEL}" &
  BACKEND_PID=$!
  ok "Backend PID=${BACKEND_PID}"
}

# ── Frontend: Vite dev server ──────────────────────────────────────────────────
start_frontend() {
  info "Starting Seacommons dashboard on http://localhost:5173"
  cd "${ROOT}"
  if ! command -v npm &>/dev/null; then
    error "npm not found. Install Node.js >= 20"
    exit 1
  fi
  if [[ ! -d node_modules ]]; then
    info "Installing frontend deps..."
    npm install
  fi
  npm run dev &
  FRONTEND_PID=$!
  ok "Frontend PID=${FRONTEND_PID}"
}

# ── Cleanup on exit ────────────────────────────────────────────────────────────
cleanup() {
  info "Shutting down..."
  [[ -n "${BACKEND_PID:-}" ]]  && kill "${BACKEND_PID}"  2>/dev/null || true
  [[ -n "${FRONTEND_PID:-}" ]] && kill "${FRONTEND_PID}" 2>/dev/null || true
  ok "Done."
}
trap cleanup EXIT INT TERM

# ── Parse args ────────────────────────────────────────────────────────────────
MODE="${1:-all}"

case "${MODE}" in
  backend)  start_backend; wait "${BACKEND_PID}" ;;
  frontend) start_frontend; wait "${FRONTEND_PID}" ;;
  all)
    start_backend
    sleep 1
    start_frontend
    echo ""
    ok "Seacommons dev stack running:"
    echo -e "  API:      ${GRN}http://localhost:8000${NC}"
    echo -e "  Frontend: ${GRN}http://localhost:5173${NC}"
    echo -e "  API docs: ${GRN}http://localhost:8000/docs${NC}"
    echo ""
    wait
    ;;
  *)
    echo "Usage: $0 [all|backend|frontend]"
    exit 1
    ;;
esac
