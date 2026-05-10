# Shikra Trading System — Technical Documentation

**Version:** 1.0.0  
**Asset:** XAUUSD (Gold) only  
**Language:** Python 3.10+  
**Broker Interface:** MetaTrader 5 Python API  
**Strategy:** Smart Money Concepts (SMC)  
**Author:** Shikra Team  
**Last Updated:** 2026-05-10  

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [Module Breakdown](#3-module-breakdown)
4. [SMC Engine Specification](#4-smc-engine-specification)
5. [Dynamic Adaptation Engine](#5-dynamic-adaptation-engine)
6. [Risk Management Module](#6-risk-management-module)
7. [Session & Filter System](#7-session--filter-system)
8. [ML/DL Enhancement Layer](#8-mldl-enhancement-layer)
9. [Data Flow & Execution Pipeline](#9-data-flow--execution-pipeline)
10. [Configuration Reference](#10-configuration-reference)
11. [Tech Stack & Dependencies](#11-tech-stack--dependencies)
12. [Build Roadmap](#12-build-roadmap)
13. [Backtesting Framework](#13-backtesting-framework)
14. [Monitoring & Observability](#14-monitoring--observability)
15. [Error Handling & Safety](#15-error-handling--safety)
16. [Glossary](#16-glossary)

---

## 1. Project Overview

### 1.1 What is Shikra?

Shikra is a professional-grade algorithmic trading system built in Python, designed exclusively for **Gold (XAUUSD)** trading. It is a complete Python rewrite of the original **Shikra EA v10** (MQL5), preserving all core Smart Money Concepts logic while adding a modern data science and machine learning layer on top.

### 1.2 Core Philosophy

> "Trade with the institutions, not against them."

Shikra follows **Smart Money Concepts (SMC)** — a price action methodology that tracks how large institutional players (banks, hedge funds) move the market. The system identifies their footprints through:

- Break of Structure (BOS)
- Change of Character (CHoCH)
- Fair Value Gaps (FVG)
- Order Blocks (OB)
- Liquidity Sweeps

### 1.3 Key Differentiators from v10 (MQL5)

| Feature | MQL5 v10 | Python v1.0 |
|--------|----------|-------------|
| Language | MQL5 | Python 3.10+ |
| Pairs Supported | 5 pairs | XAUUSD only (focused) |
| Signal Validation | Rule-based only | Rule-based + ML Filter |
| Bias Prediction | ATR-based | ATR + LSTM (advanced) |
| Analytics | Basic dashboard | Full pandas analytics + charts |
| Backtesting | MT5 Strategy Tester | Custom vectorized backtester |
| Extensibility | Limited (MQL5) | Full Python ecosystem |

### 1.4 Scope

**In Scope:**
- XAUUSD live trading via MT5
- Full SMC signal detection engine
- Dynamic ATR-based calibration
- Risk management (lot sizing, drawdown limits, recovery)
- Session & volatility filters
- ML signal quality filter (Phase 2)
- LSTM H4 bias prediction (Phase 3)

**Out of Scope:**
- Other currency pairs or crypto
- Multi-broker support (MT5 only)
- Web-based UI (CLI only in v1.0)
- Social/copy trading features

---

## 2. System Architecture

### 2.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MetaTrader 5 Terminal                     │
│              (Running in background — Windows)               │
└────────────────────────┬────────────────────────────────────┘
                         │  MetaTrader5 Python API
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    DATA LAYER                                │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │ Tick Stream │  │  OHLCV Feed  │  │  Account Info     │  │
│  │  (Real-time)│  │  (H1, H4, D1)│  │  (Balance, Equity)│  │
│  └─────────────┘  └──────────────┘  └───────────────────┘  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                 ANALYSIS ENGINE                              │
│  ┌──────────────────┐   ┌───────────────────────────────┐   │
│  │ Dynamic Adapter  │   │       SMC Engine               │   │
│  │ (ATR Calibration)│   │  BOS │ CHoCH │ FVG │ OB │ LS  │   │
│  └──────────────────┘   └───────────────────────────────┘   │
│  ┌──────────────────┐   ┌───────────────────────────────┐   │
│  │   H4 Bias Engine │   │    Volatility Regime Detector  │   │
│  └──────────────────┘   └───────────────────────────────┘   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│               ML / DL LAYER  (Phase 2 & 3)                  │
│  ┌───────────────────────┐  ┌──────────────────────────┐    │
│  │  Signal Quality Filter│  │  LSTM H4 Bias Predictor  │    │
│  │  (XGBoost Classifier) │  │  (Keras Sequential)      │    │
│  └───────────────────────┘  └──────────────────────────┘    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│               RISK MANAGEMENT MODULE                         │
│  Lot Sizing │ Drawdown Guard │ Recovery Logic │ Basket PnL  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                  EXECUTION ENGINE                            │
│     Order Placement │ SL/TP │ Trailing Stop │ Partial Close │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│              MONITORING & LOGGING                            │
│     Trade Journal │ Equity Curve │ Drawdown Chart │ Alerts  │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Execution Timeframe Hierarchy

```
D1  →  ATR-based SL distance calibration
H4  →  Directional Bias (Bullish / Bearish / Ranging)
H1  →  SMC signal detection & entry trigger
M5  →  Entry refinement (optional, Phase 2)
```

---

## 3. Module Breakdown

### 3.1 Project Folder Structure

```
forex-trading-bot/
│
├── main.py                      # Entry point — starts the bot
├── config.py                    # All configurable parameters
├── requirements.txt             # Python dependencies
│
├── core/
│   ├── __init__.py
│   ├── mt5_connector.py         # MT5 connection & data fetching
│   ├── data_feed.py             # OHLCV + tick data management
│   └── scheduler.py             # H1/H4/D1 bar event scheduler
│
├── smc/
│   ├── __init__.py
│   ├── structure.py             # BOS & CHoCH detection
│   ├── fvg.py                   # Fair Value Gap detection
│   ├── order_blocks.py          # Order Block identification
│   ├── liquidity.py             # Liquidity Sweep detection
│   ├── supply_demand.py         # Supply & Demand zones
│   └── signal_generator.py     # Combines all SMC signals → EntrySignal
│
├── analysis/
│   ├── __init__.py
│   ├── h4_bias.py               # H4 directional bias engine
│   ├── volatility.py            # Volatility regime detector
│   └── dynamic_adapter.py      # ATR-based auto-calibration
│
├── risk/
│   ├── __init__.py
│   ├── lot_calculator.py        # Auto lot sizing from risk %
│   ├── drawdown_guard.py        # Daily drawdown limit enforcement
│   ├── recovery.py              # Recovery mode & basket recovery
│   └── position_manager.py     # SL/TP/trailing/partial close
│
├── filters/
│   ├── __init__.py
│   ├── session_filter.py        # Trading session management
│   ├── news_filter.py           # High-impact news avoidance
│   └── spread_filter.py         # Max spread enforcement
│
├── ml/                          # Phase 2
│   ├── __init__.py
│   ├── feature_engineering.py  # Feature extraction from SMC data
│   ├── signal_filter.py         # XGBoost signal quality classifier
│   └── model_trainer.py         # Train & evaluate ML model
│
├── dl/                          # Phase 3
│   ├── __init__.py
│   ├── lstm_bias.py             # LSTM H4 bias predictor
│   └── dl_trainer.py            # Train LSTM model
│
├── backtest/
│   ├── __init__.py
│   ├── engine.py                # Vectorized backtesting engine
│   ├── metrics.py               # Sharpe, Sortino, max DD, win rate
│   └── visualizer.py            # Equity curve, trade plots
│
├── monitoring/
│   ├── __init__.py
│   ├── logger.py                # Structured trade logging
│   ├── dashboard.py             # Real-time console dashboard
│   └── alerts.py                # Email/Telegram alerts
│
├── docs/
│   └── SHIKRA_DOCUMENTATION.md # This file
│
└── tests/
    ├── test_smc.py
    ├── test_risk.py
    └── test_backtest.py
```

---

## 4. SMC Engine Specification

### 4.1 Break of Structure (BOS)

**Definition:** Price breaks a previous swing high (bullish BOS) or swing low (bearish BOS), confirming trend continuation.

**Detection Logic:**
```
Bullish BOS:  close[i] > previous_swing_high  AND  prior trend = bullish
Bearish BOS:  close[i] < previous_swing_low   AND  prior trend = bearish
```

**Parameters:**
| Parameter | Default | Description |
|-----------|---------|-------------|
| `swing_lookback` | 20 | Bars to look back for swing points |
| `min_structure_size` | 1.5x ATR | Minimum size of structure to qualify |
| `confirmation_close` | True | Must close beyond level (not just wick) |

---

### 4.2 Change of Character (CHoCH)

**Definition:** Price breaks structure in the **opposite** direction of the current trend — signals potential reversal.

**Detection Logic:**
```
Bullish CHoCH:  downtrend active  AND  close[i] > last_swing_high
Bearish CHoCH:  uptrend active    AND  close[i] < last_swing_low
```

**Weight in Signal:** CHoCH carries higher signal weight than BOS — it indicates trend shift.

---

### 4.3 Fair Value Gap (FVG)

**Definition:** A 3-candle imbalance where candle[i-2] and candle[i] do not overlap — creating an inefficiency (gap) that price tends to return to fill.

**Detection Logic:**
```
Bullish FVG:  low[i] > high[i-2]    (gap between candle i and i-2)
Bearish FVG:  high[i] < low[i-2]    (gap between candle i and i-2)
Gap Size:     minimum 0.5x H1 ATR
```

**States:** `OPEN` → `PARTIALLY_FILLED` → `FILLED`  
**Expiry:** FVG expires after `fvg_expiry_bars` bars if not filled.

---

### 4.4 Order Blocks (OB)

**Definition:** The last bullish/bearish candle before a strong impulse move — represents institutional order accumulation zone.

**Detection Logic:**
```
Bullish OB:  last bearish candle before a strong bullish impulse
             impulse_size >= 2.0x ATR
Bearish OB:  last bullish candle before a strong bearish impulse
             impulse_size >= 2.0x ATR
```

**OB Zone:** `[low, high]` of the qualifying candle  
**Validity:** OB invalidated when price closes fully through it.

---

### 4.5 Liquidity Sweeps (LS)

**Definition:** Price briefly spikes beyond a swing high/low (equal highs/lows) to collect stop orders, then reverses — classic institutional manipulation.

**Detection Logic:**
```
Sweep High:  wick[i] > previous_swing_high  AND  close[i] < previous_swing_high
Sweep Low:   wick[i] < previous_swing_low   AND  close[i] > previous_swing_low
Wick Size:   minimum 1.0x H1 ATR
```

---

### 4.6 Signal Scoring System

Each detected SMC concept contributes a weight to the final signal score:

| Concept | Bullish Weight | Bearish Weight |
|---------|---------------|----------------|
| CHoCH   | +3.0          | -3.0           |
| BOS     | +2.0          | -2.0           |
| OB Touch| +2.5          | -2.5           |
| FVG Fill| +2.0          | -2.0           |
| Liq Sweep| +1.5         | -1.5           |
| H4 Bias Alignment | +2.0 | -2.0          |

**Entry Threshold:** Total score >= `min_signal_score` (default: 6.0)  
**MTF Boost:** If H4 + H1 align → score multiplied by 1.3x

---

## 5. Dynamic Adaptation Engine

### 5.1 Overview

Unlike static parameter systems, Shikra auto-calibrates all key thresholds using live market data. No manual tuning needed per market condition.

### 5.2 Calibration Schedule

| Event | Action |
|-------|--------|
| New H4 bar | Full recalibration of all parameters |
| New D1 bar | SL distance update from D1 ATR |
| Volatility regime change | Lot multiplier update |

### 5.3 Parameter Auto-Calculation

```python
# SL Distance (from D1 ATR)
sl_distance_pips = D1_ATR * sl_atr_multiplier      # default multiplier: 1.5

# Spread Filter (from H1 ATR)
max_spread = H1_ATR * spread_atr_multiplier         # default multiplier: 0.15

# FVG Minimum Size
min_fvg_size = H1_ATR * 0.5

# OB Impulse Threshold
min_ob_impulse = H1_ATR * 2.0

# Swing Significance
min_swing_size = H1_ATR * 1.5
```

### 5.4 Volatility Regime Detection

```
LOW     → 14-period ATR < 30th percentile of last 100 bars
NORMAL  → 14-period ATR between 30th and 70th percentile
HIGH    → 14-period ATR > 70th percentile
EXTREME → 14-period ATR > 90th percentile → skip trading
```

**Lot Multiplier by Regime:**
| Regime | Lot Multiplier |
|--------|---------------|
| LOW    | 1.2x          |
| NORMAL | 1.0x          |
| HIGH   | 0.7x          |
| EXTREME| 0.0x (skip)   |

---

## 6. Risk Management Module

### 6.1 Lot Size Calculation

```
Risk Amount  = Account Balance × (RiskPercent / 100)
Pip Value    = (Lot Size × Contract Size × Tick Value) / Tick Size
Lot Size     = Risk Amount / (SL_pips × Pip Value)
```

**Safety caps:**
- Minimum lot: `0.01`
- Maximum lot: `max_lot_size` (configurable)
- Max % of balance per trade: `5%` (hard cap)

### 6.2 Daily Drawdown Guard

```
Daily Drawdown % = (Day Start Equity - Current Equity) / Day Start Equity × 100

If Daily Drawdown % >= max_daily_drawdown (default 5%):
    → Close all open positions
    → Block new trades until next day reset (00:00 broker time)
```

### 6.3 Trade Limits

| Parameter | Default | Description |
|-----------|---------|-------------|
| `max_trades_per_day` | 5 | Max new entries per calendar day |
| `max_trades_per_session` | 2 | Max entries per session (London/NY/Asia) |
| `cooldown_after_sl` | 2 hours | No new trades after SL hit |
| `max_consecutive_losses` | 3 | Trigger recovery mode |

### 6.4 Position Management

**Stop Loss:** ATR-based, placed beyond OB or swing structure  
**Take Profit:** 
```
TP1 = SL × 1.5  (50% partial close)
TP2 = SL × 3.0  (remaining position)
```

**Trailing Stop:**
- Activates after TP1 hit
- Trails at `trailing_atr_multiplier × H1_ATR` below price (long) / above price (short)

### 6.5 Recovery Mode

**Triggered:** After `max_consecutive_losses` SL hits  

**Behavior:**
- Lot size reduced to `recovery_lot_multiplier × normal_lot` (default: 0.5x)
- Only highest-confidence signals taken (score >= `recovery_min_score`)
- Recovery exits when `recovery_profit_target` pips gained

### 6.6 Basket Recovery

Tracks combined PnL of all open positions as a basket:
```
If basket_pnl <= basket_drawdown_limit:
    → Activate basket recovery mode
    → Manage all positions toward combined breakeven
    → Close all when basket_pnl >= basket_recovery_target
```

---

## 7. Session & Filter System

### 7.1 Trading Sessions

| Session | UTC Time | Active |
|---------|----------|--------|
| Sydney  | 22:00 – 07:00 | Optional |
| Tokyo   | 00:00 – 09:00 | Optional |
| London  | 07:00 – 16:00 | **Primary** |
| New York| 12:00 – 21:00 | **Primary** |
| Overlap (London+NY) | 12:00 – 16:00 | **Highest priority** |

### 7.2 Session Filter Logic

```python
if current_session not in allowed_sessions:
    skip_entry()

if session_exposure[current_session] >= max_trades_per_session:
    skip_entry()
```

### 7.3 Spread Filter

```python
current_spread = mt5.symbol_info("XAUUSD").spread
max_allowed_spread = H1_ATR * spread_atr_multiplier

if current_spread > max_allowed_spread:
    skip_entry()  # Market too illiquid / high-cost
```

### 7.4 News Filter

High-impact economic events (NFP, FOMC, CPI, Gold-specific events):
```
Block window: news_time - 30 minutes  →  news_time + 60 minutes
Data source: ForexFactory calendar API (or manual schedule)
```

---

## 8. ML/DL Enhancement Layer

> **Phase 2 & 3 — Built after core bot is profitable**

### 8.1 ML Signal Quality Filter (Phase 2)

**Goal:** Classify each SMC signal as HIGH_QUALITY or LOW_QUALITY before entry.

**Model:** XGBoost Classifier (binary classification)

**Features (X):**
```python
features = [
    'signal_score',          # SMC composite score
    'h4_bias_strength',      # H4 directional bias score
    'volatility_regime',     # 0=LOW, 1=NORMAL, 2=HIGH
    'session_id',            # 0=London, 1=NY, 2=Overlap
    'atr_d1', 'atr_h1',      # Volatility context
    'spread_ratio',          # current_spread / max_spread
    'distance_to_ob',        # % distance price is from OB
    'fvg_fill_percent',      # How much of FVG is filled
    'bos_count_last_5',      # Recent structure breaks
    'liq_sweep_present',     # 1/0
    'hour_of_day',           # Time feature
    'day_of_week',           # Day feature
]
```

**Label (y):**
```
1 = Trade reached TP1 (profitable signal)
0 = Trade hit SL (losing signal)
```

**Training Data:** Historical trades logged by the bot itself (min 500 trades recommended)

**Performance Target:** Precision >= 0.65 on test set before deploying

---

### 8.2 LSTM H4 Bias Predictor (Phase 3)

**Goal:** Predict next H4 bar direction (UP / DOWN / NEUTRAL) using deep learning.

**Model:** LSTM (Long Short-Term Memory) — Sequential Keras model

**Input Sequence:**
```
Last 60 H4 bars × [open, high, low, close, volume, ATR, BOS_flag, CHoCH_flag]
Shape: (batch_size, 60, 8)
```

**Output:**
```
Softmax(3) → [P(UP), P(DOWN), P(NEUTRAL)]
```

**Architecture:**
```python
model = Sequential([
    LSTM(128, return_sequences=True, input_shape=(60, 8)),
    Dropout(0.2),
    LSTM(64, return_sequences=False),
    Dropout(0.2),
    Dense(32, activation='relu'),
    Dense(3, activation='softmax')
])
```

**Integration:** LSTM prediction replaces/augments ATR-based H4 bias in signal pipeline.

---

## 9. Data Flow & Execution Pipeline

### 9.1 OnTick Equivalent (Main Loop)

```
Every tick:
  1. Check MT5 connection alive
  2. Update real-time spread filter
  3. Manage open positions (SL, TP, trailing, partial close)
  4. Check basket recovery status

Every new H1 bar:
  5.  Daily reset check (if new day)
  6.  Equity/drawdown protection check
  7.  Update volatility regime
  8.  Session exposure check
  9.  Spread filter check
  10. News filter check
  11. Extreme volatility check (EXTREME regime → skip)
  12. H4 ranging check → skip if ranging
  13. Run SMC analysis → generate EntrySignal
  14. ML filter (Phase 2) → validate signal quality
  15. Calculate lot size (with regime multiplier)
  16. ProcessEntrySignal() → place order

Every new H4 bar:
  17. AutoCalibrate() → recalculate ATR-based parameters
  18. Update H4 directional bias (or LSTM prediction in Phase 3)

Every new D1 bar:
  19. Update D1 ATR for SL calculation
  20. Reset daily trade counters
```

### 9.2 EntrySignal Data Structure

```python
@dataclass
class EntrySignal:
    direction: str          # 'BUY' or 'SELL'
    score: float            # SMC composite score
    entry_price: float      # Suggested entry
    sl_price: float         # Stop Loss level
    tp1_price: float        # Take Profit 1
    tp2_price: float        # Take Profit 2
    lot_size: float         # Calculated lot
    signal_type: str        # 'BOS', 'CHoCH', 'OB', 'FVG', 'LS', 'COMBO'
    h4_bias: str            # 'BULLISH', 'BEARISH', 'RANGING'
    volatility_regime: str  # 'LOW', 'NORMAL', 'HIGH'
    session: str            # 'LONDON', 'NY', 'OVERLAP'
    timestamp: datetime
    ml_confidence: float    # Phase 2: 0.0–1.0 (default 1.0 before ML)
```

---

## 10. Configuration Reference

### 10.1 config.py — All Parameters

```python
# ─── MT5 Connection ───────────────────────────────────────
MT5_LOGIN     = 0           # Your MT5 account number
MT5_PASSWORD  = ""          # Account password (use .env)
MT5_SERVER    = ""          # Broker server name

# ─── Symbol ───────────────────────────────────────────────
SYMBOL        = "XAUUSD"
TIMEFRAME_H1  = mt5.TIMEFRAME_H1
TIMEFRAME_H4  = mt5.TIMEFRAME_H4
TIMEFRAME_D1  = mt5.TIMEFRAME_D1

# ─── Risk Management ──────────────────────────────────────
RISK_PERCENT          = 1.0    # % of balance per trade
MAX_LOT_SIZE          = 5.0    # Hard cap on lot size
MAX_DAILY_DRAWDOWN    = 5.0    # % — stops trading if hit
MAX_TRADES_PER_DAY    = 5
MAX_TRADES_PER_SESSION = 2
COOLDOWN_AFTER_SL_HOURS = 2
MAX_CONSECUTIVE_LOSSES  = 3

# ─── Dynamic Adaptation ───────────────────────────────────
SL_ATR_MULTIPLIER       = 1.5   # SL = D1_ATR × this
SPREAD_ATR_MULTIPLIER   = 0.15  # Max spread = H1_ATR × this
OB_IMPULSE_MULTIPLIER   = 2.0   # Min impulse for OB
FVG_MIN_SIZE_MULTIPLIER = 0.5   # Min FVG = H1_ATR × this
TRAILING_ATR_MULTIPLIER = 1.0   # Trailing distance

# ─── SMC Signal ───────────────────────────────────────────
MIN_SIGNAL_SCORE    = 6.0       # Minimum to enter
MTF_BOOST_FACTOR    = 1.3       # H4+H1 alignment boost
SWING_LOOKBACK      = 20        # Bars for swing detection
FVG_EXPIRY_BARS     = 50        # FVG invalid after N bars

# ─── Sessions ─────────────────────────────────────────────
ALLOWED_SESSIONS    = ["LONDON", "NEW_YORK", "OVERLAP"]
SESSION_TIMES_UTC   = {
    "LONDON":   ("07:00", "16:00"),
    "NEW_YORK":  ("12:00", "21:00"),
    "OVERLAP":  ("12:00", "16:00"),
}

# ─── Volatility Regimes ───────────────────────────────────
ATR_PERIOD              = 14
VOLATILITY_LOW_PCTILE   = 30
VOLATILITY_HIGH_PCTILE  = 70
VOLATILITY_EXTREME_PCTILE = 90
LOT_MULTIPLIER = {
    "LOW": 1.2, "NORMAL": 1.0, "HIGH": 0.7, "EXTREME": 0.0
}

# ─── TP Ratios ────────────────────────────────────────────
TP1_RR_RATIO    = 1.5   # TP1 = SL × 1.5
TP2_RR_RATIO    = 3.0   # TP2 = SL × 3.0
TP1_CLOSE_PCT   = 0.5   # Close 50% at TP1

# ─── Recovery ─────────────────────────────────────────────
RECOVERY_LOT_MULTIPLIER  = 0.5
RECOVERY_MIN_SCORE       = 8.0
RECOVERY_PROFIT_TARGET   = 50   # pips

# ─── ML/DL (Phase 2/3) ────────────────────────────────────
ML_MIN_CONFIDENCE       = 0.65  # Skip signal if below this
LSTM_SEQUENCE_LENGTH    = 60    # H4 bars for LSTM input
ML_ENABLED              = False # Toggle (Phase 2)
DL_ENABLED              = False # Toggle (Phase 3)
```

---

## 11. Tech Stack & Dependencies

### 11.1 Core Dependencies

```
MetaTrader5==5.0.45         # MT5 Python API
pandas==2.2.0               # Data manipulation
numpy==1.26.0               # Numerical computation
```

### 11.2 ML/DL Dependencies (Phase 2/3)

```
scikit-learn==1.4.0         # ML utilities & metrics
xgboost==2.0.0              # Signal quality classifier
tensorflow==2.15.0          # LSTM model (keras)
```

### 11.3 Visualization & Monitoring

```
matplotlib==3.8.0           # Charts & equity curve
seaborn==0.13.0             # Statistical visualizations
rich==13.7.0                # Beautiful console dashboard
```

### 11.4 Utilities

```
python-dotenv==1.0.0        # Secrets management (.env)
schedule==1.2.0             # Job scheduling
loguru==0.7.2               # Structured logging
pytest==8.0.0               # Testing framework
```

### 11.5 requirements.txt

```
MetaTrader5>=5.0.45
pandas>=2.2.0
numpy>=1.26.0
scikit-learn>=1.4.0
xgboost>=2.0.0
tensorflow>=2.15.0
matplotlib>=3.8.0
seaborn>=0.13.0
rich>=13.7.0
python-dotenv>=1.0.0
schedule>=1.2.0
loguru>=0.7.2
pytest>=8.0.0
```

---

## 12. Build Roadmap

### Phase 1 — Core Bot (Rule-Based)

```
[ ] 1.1  MT5 connector & data feed (OHLCV, tick)
[ ] 1.2  Dynamic ATR calibration engine
[ ] 1.3  H4 bias detector (ATR-based)
[ ] 1.4  SMC: BOS & CHoCH detection
[ ] 1.5  SMC: FVG detection
[ ] 1.6  SMC: Order Block detection
[ ] 1.7  SMC: Liquidity Sweep detection
[ ] 1.8  Signal scoring & EntrySignal generation
[ ] 1.9  Lot size calculator
[ ] 1.10 Order execution (entry, SL, TP1, TP2)
[ ] 1.11 Position manager (trailing, partial close)
[ ] 1.12 Session & spread filters
[ ] 1.13 Daily drawdown guard
[ ] 1.14 Recovery mode
[ ] 1.15 Console dashboard (rich)
[ ] 1.16 Trade logger (CSV + loguru)
[ ] 1.17 Basic backtester
[ ] 1.18 Unit tests (core SMC functions)
```

**Target:** Working, profitable bot on demo account

---

### Phase 2 — ML Signal Filter

```
[ ] 2.1  Feature engineering pipeline
[ ] 2.2  Historical trade data collection (500+ trades)
[ ] 2.3  XGBoost model training & evaluation
[ ] 2.4  Integration with signal pipeline
[ ] 2.5  A/B test: ML vs no-ML performance comparison
[ ] 2.6  Model persistence & versioning
```

**Target:** Precision >= 0.65, measurable improvement in win rate

---

### Phase 3 — LSTM H4 Bias Predictor

```
[ ] 3.1  H4 sequence dataset preparation
[ ] 3.2  LSTM architecture implementation (Keras)
[ ] 3.3  Model training, validation, hyperparameter tuning
[ ] 3.4  Integration replacing ATR-based H4 bias
[ ] 3.5  Live performance monitoring vs rule-based bias
```

**Target:** H4 bias accuracy >= 60% on live data

---

## 13. Backtesting Framework

### 13.1 Data Source

```python
# Fetch historical OHLCV from MT5
rates = mt5.copy_rates_from_pos("XAUUSD", mt5.TIMEFRAME_H1, 0, 50000)
df = pd.DataFrame(rates)
df['time'] = pd.to_datetime(df['time'], unit='s')
```

### 13.2 Metrics Computed

| Metric | Description |
|--------|-------------|
| Net Profit | Total PnL in USD |
| Win Rate | % of winning trades |
| Sharpe Ratio | Risk-adjusted return |
| Sortino Ratio | Downside risk-adjusted return |
| Max Drawdown | Peak-to-trough equity loss |
| Profit Factor | Gross profit / Gross loss |
| Avg RR | Average Risk:Reward achieved |
| Total Trades | Count |
| Avg Trade Duration | Hours |

### 13.3 Walk-Forward Validation

```
Train Period:  Jan 2020 – Dec 2022
Test Period:   Jan 2023 – Dec 2023
Live Period:   Jan 2024 – Present

Walk-Forward: 6-month train, 1-month test, sliding window
```

---

## 14. Monitoring & Observability

### 14.1 Trade Log Schema (CSV)

```
timestamp, direction, entry, sl, tp1, tp2, lot,
signal_type, score, h4_bias, session, regime,
exit_price, exit_reason, pnl_usd, pnl_pips,
duration_hours, ml_confidence
```

### 14.2 Console Dashboard (rich)

```
┌─── Shikra Gold Bot ──────────────────────────────┐
│ Status: RUNNING    Session: LONDON OVERLAP        │
│ Balance: $10,000   Equity: $10,245                │
│ Daily PnL: +$245   Drawdown: 0.8%                 │
│ Trades Today: 2/5  Regime: NORMAL                 │
├──────────────────────────────────────────────────┤
│ Open Positions:                                    │
│  #1  BUY  XAUUSD  0.02  Entry:2345.5  PnL:+$120  │
├──────────────────────────────────────────────────┤
│ Last Signal: CHoCH+OB+FVG  Score:8.5  BULLISH     │
└──────────────────────────────────────────────────┘
```

### 14.3 Alerts

- Telegram bot message on: trade entry, trade close, SL hit, drawdown limit approach, MT5 disconnection
- Email on: daily summary, drawdown limit breach, critical errors

---

## 15. Error Handling & Safety

### 15.1 MT5 Connection

```python
# Auto-reconnect on disconnect
if not mt5.terminal_info():
    reconnect_with_backoff(max_attempts=5)
```

### 15.2 Order Execution Safety

```python
# Pre-order validation
assert current_spread <= max_spread
assert lot_size >= min_lot and lot_size <= max_lot
assert sl_distance >= min_sl_pips
assert daily_drawdown < max_daily_drawdown

# Post-order validation
if order_result.retcode != mt5.TRADE_RETCODE_DONE:
    log_error(order_result)
    alert("Order failed")
```

### 15.3 Emergency Shutdown

Triggers on:
- MT5 disconnection > 5 minutes
- Daily drawdown >= hard limit
- 3 failed order placements in a row
- System exception (unhandled)

Action: Close all positions → send alert → graceful shutdown

---

## 16. Glossary

| Term | Definition |
|------|-----------|
| **BOS** | Break of Structure — price breaks previous swing high/low, confirms trend |
| **CHoCH** | Change of Character — BOS in opposite direction, signals reversal |
| **FVG** | Fair Value Gap — price imbalance between 3 candles, tends to get filled |
| **OB** | Order Block — last opposing candle before impulse, institutional zone |
| **LS** | Liquidity Sweep — wick beyond swing point collecting stops, then reversal |
| **H4 Bias** | Overall directional trend determined on H4 timeframe |
| **SMC** | Smart Money Concepts — institutional trading methodology |
| **ATR** | Average True Range — measures volatility over N periods |
| **RR** | Risk:Reward ratio |
| **DD** | Drawdown — peak-to-trough equity loss |
| **Regime** | Volatility classification: LOW / NORMAL / HIGH / EXTREME |
| **MTF** | Multi-Timeframe — using multiple timeframes for confluence |
| **PnL** | Profit and Loss |
| **SL** | Stop Loss |
| **TP** | Take Profit |

---

*Documentation maintained by Shikra Team. Update on every major version release.*
