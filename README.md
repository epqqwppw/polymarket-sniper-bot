# 🎯 Polymarket Sniper Bot

A production-level **Polymarket crypto prediction market analysis and simulated trading bot**. The bot monitors Polymarket's 5-minute and 15-minute BTC/ETH/SOL up/down prediction markets, performs real-time technical analysis using multiple data feeds, and provides live trading signals through a clean web UI dashboard.

> **⚠️ IMPORTANT: All trade execution runs in DRY-RUN / SIMULATION mode. The bot logs what it *would* do but does NOT place real orders.**

---

## 📐 Architecture

```
Frontend (React + Tailwind CSS)
    ↕ WebSocket (Socket.IO)
Backend (Python FastAPI + asyncio)
    ↕
Redis (real-time data buffer + pub/sub)
    ↕
Data Feeds (Binance WS, Polymarket APIs, CoinGecko fallback)
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.11+, FastAPI, asyncio, websockets, aiohttp, Socket.IO |
| **Frontend** | React 18+, Tailwind CSS, Socket.IO client, Recharts |
| **Data Store** | Redis (pub/sub, caching, real-time streaming) |
| **Infrastructure** | Docker Compose, Uvicorn |

---

## 📂 Project Structure

```
polymarket-sniper-bot/
├── README.md                          # This file
├── docker-compose.yml                 # Redis + Backend + Frontend
├── .env.example                       # Environment variables template
├── backend/
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── main.py                        # FastAPI app entry point
│   ├── config.py                      # Configuration, constants, env vars
│   ├── core/
│   │   ├── market_discovery.py        # Auto-discover active 5m/15m markets
│   │   ├── data_feeds.py             # Binance WS, Polymarket CLOB/RTDS feeds
│   │   ├── signal_engine.py          # Technical indicators & signal calculation
│   │   ├── decision_engine.py        # Confidence scoring & trade decisions
│   │   ├── money_manager.py          # Kelly criterion, position sizing, bankroll
│   │   ├── execution_engine.py       # Simulated trade execution (DRY RUN)
│   │   ├── market_manager.py         # Lifecycle: track active markets, auto-roll
│   │   └── redis_manager.py          # Redis pub/sub, caching, data streaming
│   ├── models/
│   │   ├── market.py                 # Market data models
│   │   ├── signal.py                 # Signal/indicator models
│   │   └── trade.py                  # Trade/position models
│   ├── api/
│   │   ├── routes.py                 # REST endpoints for UI
│   │   └── websocket_handler.py      # Socket.IO server for real-time UI
│   └── utils/
│       ├── logger.py                 # Structured logging
│       └── helpers.py                # Utility functions
├── frontend/
│   ├── package.json
│   ├── Dockerfile
│   ├── tailwind.config.js
│   ├── public/
│   │   └── index.html
│   └── src/
│       ├── App.jsx                   # Main app with Socket.IO connection
│       ├── index.jsx
│       ├── index.css
│       ├── components/
│       │   ├── Dashboard.jsx         # Main dashboard layout
│       │   ├── MarketCard.jsx        # Individual market analysis card
│       │   ├── SignalPanel.jsx       # Live signal indicators display
│       │   ├── PriceChart.jsx        # Real-time price mini-chart
│       │   ├── OrderFlowPanel.jsx    # Order flow visualization
│       │   ├── TradeLog.jsx          # Simulated trade history log
│       │   ├── BankrollTracker.jsx   # $100 bankroll P&L tracker
│       │   ├── ControlPanel.jsx      # Start/Stop analysis controls
│       │   └── Header.jsx            # App header with status indicators
│       ├── hooks/
│       │   ├── useSocket.js          # Socket.IO connection hook
│       │   └── useMarketData.js      # Market data state management
│       └── utils/
│           └── formatters.js         # Number/time formatting helpers
└── scripts/
    └── start.sh                      # Script to start all services
```

---

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **Node.js 18+**
- **Redis** (running on port 6379)
- **Docker** (optional, for containerized setup)

### Option 1: Docker Compose (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/epqqwppw/polymarket-sniper-bot.git
cd polymarket-sniper-bot

# 2. Copy environment config
cp .env.example .env

# 3. Start all services
docker compose up --build
```

Open **http://localhost:3000** for the dashboard.

### Option 2: Manual Setup

```bash
# 1. Start Redis
redis-server --daemonize yes
# or: docker run -d -p 6379:6379 redis:7-alpine

# 2. Install and start the backend
cd backend
pip install -r requirements.txt
cd ..
python -m uvicorn backend.main:socket_app --host 0.0.0.0 --port 8000

# 3. In a new terminal — install and start the frontend
cd frontend
npm install
REACT_APP_BACKEND_URL=http://localhost:8000 npm start
```

### Option 3: Start Script

```bash
chmod +x scripts/start.sh
./scripts/start.sh
```

---

## ⚙️ Configuration

All settings are controlled via the `.env` file (copy from `.env.example`):

| Variable | Default | Description |
|----------|---------|-------------|
| `DRY_RUN` | `true` | **Must be true** — simulation mode. No real trades. |
| `INITIAL_BANKROLL` | `100.00` | Starting simulated bankroll in USD |
| `LOG_LEVEL` | `INFO` | Logging verbosity (DEBUG, INFO, WARNING, ERROR) |
| `REDIS_URL` | `redis://localhost:6379` | Redis connection URL |
| `ACTIVE_POOL_RATIO` | `0.70` | 70% of bankroll for active trading |
| `RESERVE_RATIO` | `0.30` | 30% safety reserve |
| `MAX_SIMULTANEOUS_POSITIONS` | `5` | Max concurrent market positions |
| `SPLIT_SIZE_5MIN` | `10` | $ per 5-minute market split |
| `SPLIT_SIZE_15MIN` | `13` | $ per 15-minute market split |
| `MIN_SELL_PRICE` | `0.15` | Don't sell below this — merge instead |
| `MIN_CONFIDENCE` | `5` | Minimum confidence score (0-10) to trade |
| `MAX_LOSS_PER_HOUR` | `15.00` | Hourly loss stop-loss |

---

## 📊 How to Use the Dashboard

1. **Header Bar** — Shows bot status (Running/Paused), bankroll, P&L, win rate, and connection indicators for Binance WS, Polymarket RTDS, and Redis.

2. **Market Cards** — One card per active market (up to 6: 3×5min + 3×15min). Each shows:
   - Market question & strike price
   - Live Chainlink & Binance prices with comparison
   - Above/Below strike indicator
   - Countdown timer with progress bar
   - Mini price chart (last 60 seconds)
   - All 15 technical signals
   - Decision output with confidence score and reasoning

3. **Control Panel** — Start/Pause analysis, view active positions and available capital.

4. **Bankroll Tracker** — Running P&L, win/loss/merge counts, win rate, average sell price.

5. **Trade Log** — Scrollable history of all simulated trades with timestamps and P&L.

---

## 📈 Signal Engine (15 Indicators)

### Tier 1 — Core Signals

| Signal | Calculation |
|--------|-------------|
| Price vs Strike (%) | `(chainlink_price - strike) / strike × 100` |
| Momentum 5s/15s/30s | Price change over rolling windows |
| Exchange Lead | `binance_price - chainlink_price` |
| Time Remaining | Seconds until market close |
| Implied Probability | YES token price from CLOB |
| Net Order Flow (30s) | Buy volume − sell volume |

### Tier 2 — Confirmation Signals

| Signal | Calculation |
|--------|-------------|
| RSI (14-period) | Standard RSI on 1-second candles |
| EMA Crossover (5/15) | EMA(5) − EMA(15) |
| VWAP Deviation | `(price − VWAP) / VWAP × 100` |
| Volatility (60s) | Rolling standard deviation |

### Tier 3 — Edge Amplifiers

| Signal | Source |
|--------|--------|
| Funding Rate | Binance Futures API |
| Open Interest Change | Binance Futures API (5-min % change) |
| Multi-Exchange Consensus | Binance + Chainlink agreement on direction |

---

## 🧠 Decision Engine

The decision engine uses a **confidence scoring system (0-10)** to determine trading actions:

- **WAIT** — Before the decision deadline (≤90s for 5min, ≤180s for 15min markets)
- **MERGE** — Skip the trade (coin flip, choppy market, low confidence, bad sell price)
- **SELL YES / SELL NO** — Trade the losing side when confidence ≥ 5

Position sizing uses **Quarter-Kelly Criterion** for conservative bankroll management.

---

## 🔒 Enabling Real Trading (Future)

> **⚠️ WARNING: Real trading involves significant financial risk. Only proceed if you fully understand the risks of prediction market trading on Polymarket.**

To enable real trading (future capability):

1. Set `DRY_RUN=false` in `.env`
2. Fill in your Polymarket API credentials:
   ```
   POLYMARKET_PRIVATE_KEY=your_wallet_private_key
   POLYMARKET_API_KEY=your_api_key
   POLYMARKET_API_SECRET=your_api_secret
   POLYMARKET_API_PASSPHRASE=your_passphrase
   ```
3. Install the `py-clob-client` package
4. Ensure your wallet has USDC on Polygon

**The real execution code structure exists in `execution_engine.py` but is disabled behind the `DRY_RUN` flag.**

---

## ⚖️ Disclaimer

This software is provided for **educational and research purposes only**.

- This bot does **NOT** constitute financial advice
- Prediction market trading involves **substantial risk of loss**
- Past simulated performance does **NOT** guarantee future results
- The authors are **NOT** responsible for any financial losses
- Always do your own research before trading
- By default, all execution is in **DRY-RUN (simulation) mode**

**Use at your own risk.**

---

## 📜 License

MIT License. See [LICENSE](LICENSE) for details.
