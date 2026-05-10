# Shikra — Algorithmic Gold Trading System

> **"Trade with the institutions, not against them."**

Shikra is a professional-grade algorithmic trading system built in Python for **XAUUSD (Gold)** trading via the MetaTrader 5 API. It is a complete rewrite of the original Shikra EA v10 (MQL5), preserving all core Smart Money Concepts (SMC) logic while adding a modern ML/DL layer on top.

---

## What is Shikra?

Shikra follows **Smart Money Concepts (SMC)** — a price action methodology that tracks how large institutional players (banks, hedge funds) move the market. The system identifies their footprints through five core signals:

| Signal | Description |
|--------|-------------|
| **BOS** — Break of Structure | Price breaks previous swing high/low, confirms trend continuation |
| **CHoCH** — Change of Character | BOS in opposite direction — signals potential reversal |
| **FVG** — Fair Value Gap | 3-candle price imbalance that tends to get filled |
| **OB** — Order Block | Last opposing candle before impulse move — institutional zone |
| **LS** — Liquidity Sweep | Wick beyond swing point collecting stops, then reversal |

---

## Architecture

```
MetaTrader 5 Terminal
        │
        ▼
   DATA LAYER          →  Tick stream, OHLCV (H1/H4/D1), Account info
        │
        ▼
 ANALYSIS ENGINE       →  Dynamic ATR Calibration + SMC Signal Detection
        │
        ▼
  ML / DL LAYER        →  XGBoost Signal Filter (Phase 2) + LSTM Bias (Phase 3)
        │
        ▼
RISK MANAGEMENT        →  Lot Sizing, Drawdown Guard, Recovery Logic
        │
        ▼
EXECUTION ENGINE       →  Order Placement, SL/TP, Trailing Stop, Partial Close
        │
        ▼
 MONITORING            →  Trade Journal, Console Dashboard, Alerts
```

**Timeframe Hierarchy:**
```
D1  →  ATR-based SL distance calibration
H4  →  Directional Bias (Bullish / Bearish / Ranging)
H1  →  SMC signal detection & entry trigger
```

---

## Key Features

- **SMC Signal Engine** — BOS, CHoCH, FVG, Order Blocks, Liquidity Sweeps with composite scoring
- **Dynamic ATR Calibration** — All thresholds auto-calibrate from live market data; no manual tuning
- **Volatility Regime Detection** — LOW / NORMAL / HIGH / EXTREME regimes with adaptive lot sizing
- **Risk-First Design** — ATR-based SL, dual TP with 50% partial close, daily drawdown circuit breaker
- **Session & Spread Filters** — London/NY/Overlap session awareness, dynamic spread enforcement
- **Recovery Mode** — Reduced sizing + high-confidence-only signals after consecutive losses
- **ML Signal Filter** *(Phase 2)* — XGBoost classifier validates signal quality before entry
- **LSTM H4 Bias** *(Phase 3)* — Deep learning directional bias prediction on H4 timeframe
- **Full Observability** — Structured trade logs, console dashboard, Telegram/email alerts

---

## Project Structure

```
shikra-trading-bot/
├── src/
│   ├── engine/         # SMC signal detection (BOS, CHoCH, FVG, OB, LS)
│   ├── broker/         # MetaTrader 5 API integration & data feed
│   ├── risk/           # Lot sizing, drawdown guard, recovery, position manager
│   └── filters/        # Session, spread, news, volatility filters
├── tests/
│   ├── unit/           # Unit tests (≥80% coverage target)
│   ├── integration/    # MT5 connection, order flow tests
│   └── backtest/       # Backtesting suite
├── backtest/           # Historical data, results, analytics
├── specs/              # Feature specs, plans, tasks (SDD artifacts)
├── history/
│   ├── prompts/        # Prompt History Records (PHRs)
│   └── adr/            # Architecture Decision Records
├── docs/
│   └── SHIKRA_DOCUMENTATION.md   # Full technical documentation
├── config.yaml         # All system parameters
├── .env.example        # Environment variable template
└── requirements.txt    # Python dependencies
```

---

## Tech Stack

| Category | Library |
|----------|---------|
| Broker API | `MetaTrader5 >= 5.0.45` |
| Data | `pandas >= 2.0`, `numpy >= 1.24` |
| Technical Analysis | `pandas-ta >= 0.3.14b` |
| ML | `xgboost >= 2.0`, `scikit-learn >= 1.3` |
| Config | `PyYAML >= 6.0`, `python-dotenv >= 1.0` |
| Logging | `loguru >= 0.7` |
| Testing | `pytest >= 7.4`, `pytest-cov >= 4.1` |

---

## Quick Start

### Prerequisites

- Python 3.10+
- MetaTrader 5 terminal installed and running (Windows)
- MT5 account (demo or live)

### Installation

```bash
# Clone the repo
git clone https://github.com/anuskhattak/shikra-trading-bot.git
cd shikra-trading-bot

# Create virtual environment
python -m venv venv
venv\Scripts\activate   # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env
# Edit .env with your MT5 credentials
```

### Configuration

Set your MT5 credentials in `.env`:

```env
MT5_LOGIN=your_account_number
MT5_PASSWORD=your_password
MT5_SERVER=your_broker_server
```

Adjust trading parameters in `config.yaml`:

```yaml
risk:
  risk_per_trade_pct: 1.0        # % of balance risked per trade
  max_daily_drawdown_pct: 5.0    # Daily loss limit
  min_risk_reward: 2.0           # Minimum RR required

smc:
  bos_lookback_bars: 20          # Swing point lookback
  fvg_min_gap_points: 10         # Minimum FVG size
```

---

## Signal Scoring System

Each SMC concept contributes a weight to the final composite score:

| Concept | Bullish | Bearish |
|---------|---------|---------|
| CHoCH | +3.0 | -3.0 |
| Order Block Touch | +2.5 | -2.5 |
| BOS | +2.0 | -2.0 |
| FVG Fill | +2.0 | -2.0 |
| H4 Bias Alignment | +2.0 | -2.0 |
| Liquidity Sweep | +1.5 | -1.5 |

**Entry threshold:** Score ≥ 6.0 (configurable)  
**MTF Boost:** H4 + H1 alignment → score × 1.3x

---

## Risk Management

```
Lot Size = Account Balance × Risk% ÷ (SL Distance in pips × Pip Value)
```

- **TP1** = SL × 1.5 → 50% position closed
- **TP2** = SL × 3.0 → remaining position
- **Trailing Stop** activates after TP1 hit
- **Daily drawdown ≥ 5%** → all positions closed, no new trades until next day
- **3 consecutive losses** → Recovery Mode (0.5x lot, score ≥ 8.0 required)

---

## Build Roadmap

### Phase 1 — Core Bot (Rule-Based)
- [ ] MT5 connector & OHLCV data feed
- [ ] Dynamic ATR calibration engine
- [ ] SMC signal detection (BOS, CHoCH, FVG, OB, LS)
- [ ] Signal scoring & entry signal generation
- [ ] Risk management (lot sizing, drawdown guard, recovery)
- [ ] Order execution (entry, SL, TP1, TP2, trailing)
- [ ] Session, spread & news filters
- [ ] Console dashboard + structured trade logging
- [ ] Backtesting engine + metrics (Win%, PF, Sharpe, MaxDD)
- [ ] Unit tests (≥80% coverage)

**Target:** Profitable bot on demo — Win% ≥ 50%, Profit Factor ≥ 1.5, Max DD < 30%

### Phase 2 — ML Signal Filter
- [ ] Feature engineering from SMC signals
- [ ] XGBoost signal quality classifier (Precision ≥ 0.65)
- [ ] A/B test: ML vs rule-based performance

### Phase 3 — LSTM H4 Bias Predictor
- [ ] LSTM model on H4 sequence data (60 bars × 8 features)
- [ ] Replace ATR-based H4 bias with DL prediction
- [ ] Target: H4 bias accuracy ≥ 60% on live data

---

## Quality Gates Before Live Trading

No live capital deployed until all gates pass:

1. Unit & integration tests passing (≥80% coverage)
2. Backtest: Win% ≥ 50%, Profit Factor ≥ 1.5, Max Drawdown < 30% (min 2 years data)
3. Paper trading: minimum 1 week successful simulation
4. Senior architect review & approval
5. Drawdown circuit breaker tested & armed

---

## Safety Features

- **Emergency Stop** — kill-switch pauses all trading immediately
- **Auto-Reconnect** — reconnects to MT5 with exponential backoff on disconnect
- **Pre-Order Validation** — spread, lot size, SL distance, drawdown all checked before every order
- **Post-Order Validation** — failed orders logged and alerted immediately
- **Extreme Volatility Guard** — no trades when ATR > 90th percentile

---

## Documentation

Full technical documentation: [`docs/SHIKRA_DOCUMENTATION.md`](docs/SHIKRA_DOCUMENTATION.md)

Covers: SMC engine spec, dynamic adaptation, risk management, ML/DL architecture, backtesting framework, monitoring, and full configuration reference.

---

## Development Methodology

This project follows **Spec-Driven Development (SDD)**:
- Feature specs in `specs/`
- Architecture decisions in `history/adr/`
- Prompt history records in `history/prompts/`

---

*Asset: XAUUSD only | Broker: MetaTrader 5 | Strategy: Smart Money Concepts*
