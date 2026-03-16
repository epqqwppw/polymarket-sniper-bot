#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────
# Polymarket Sniper Bot — Quick Start Script
# ─────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🎯 Polymarket Sniper Bot — Starting all services …"
echo ""

# ── 1. Check dependencies ────────────────────────────────────
command -v python3 >/dev/null 2>&1 || { echo "❌ Python 3 is required"; exit 1; }
command -v node    >/dev/null 2>&1 || { echo "❌ Node.js is required"; exit 1; }
command -v redis-cli >/dev/null 2>&1 || echo "⚠️  Redis CLI not found — make sure Redis is running on port 6379"

# ── 2. Copy .env if needed ───────────────────────────────────
if [ ! -f "$ROOT_DIR/.env" ]; then
    cp "$ROOT_DIR/.env.example" "$ROOT_DIR/.env"
    echo "📝 Created .env from .env.example — edit as needed"
fi

# ── 3. Install backend dependencies ──────────────────────────
echo "📦 Installing backend dependencies …"
cd "$ROOT_DIR/backend"
pip install -q -r requirements.txt

# ── 4. Install frontend dependencies ─────────────────────────
echo "📦 Installing frontend dependencies …"
cd "$ROOT_DIR/frontend"
npm install --silent

# ── 5. Start Redis (if not running) ──────────────────────────
if ! redis-cli ping > /dev/null 2>&1; then
    echo "🔴 Redis is not running. Please start Redis first:"
    echo "   docker run -d -p 6379:6379 redis:7-alpine"
    echo "   — or —"
    echo "   redis-server --daemonize yes"
    exit 1
fi
echo "✅ Redis is running"

# ── 6. Start backend ─────────────────────────────────────────
echo "🚀 Starting backend (FastAPI + Socket.IO) on port 8000 …"
cd "$ROOT_DIR"
python3 -m uvicorn backend.main:socket_app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# ── 7. Start frontend ────────────────────────────────────────
echo "🚀 Starting frontend (React) on port 3000 …"
cd "$ROOT_DIR/frontend"
REACT_APP_BACKEND_URL=http://localhost:8000 npm start &
FRONTEND_PID=$!

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  🎯 Polymarket Sniper Bot is running!"
echo "  📊 Dashboard:  http://localhost:3000"
echo "  🔌 API:        http://localhost:8000/api/status"
echo "  🔌 Docs:       http://localhost:8000/docs"
echo "═══════════════════════════════════════════════════════════"
echo ""
echo "Press Ctrl+C to stop all services"

# Trap to clean up background processes
cleanup() {
    echo ""
    echo "🛑 Shutting down …"
    kill $BACKEND_PID 2>/dev/null || true
    kill $FRONTEND_PID 2>/dev/null || true
    echo "✅ All services stopped"
}
trap cleanup EXIT INT TERM

wait
