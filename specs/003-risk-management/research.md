# Research Notes: Risk Management Module

**Feature**: 003-risk-management
**Created**: 2026-05-16

---

## XAUUSD Contract Specifications (MT5)

```
Symbol:           XAUUSD
Contract Size:    100 oz (1 standard lot = 100 troy ounces)
Tick Size:        0.01 (minimum price move = $0.01 per oz)
Tick Value:       $1.00 per standard lot (0.01 * 100 oz * 1 USD/oz)
Pip Value:        $10.00 per standard lot (1 pip = 10 ticks = $10)

Lot Sizes:
  Micro lot:  0.01 = 1 oz exposure
  Mini lot:   0.10 = 10 oz exposure
  Standard:   1.00 = 100 oz exposure
```

**Why pip_value = $10.00**: Gold is quoted in USD per troy ounce. 1 standard lot covers 100 oz. A 1-pip move ($0.10 per oz) × 100 oz = $10.00. This is constant regardless of current gold price (unlike forex pairs where pip value changes).

---

## Lot Sizing Formula Derivation

```
Goal: Risk exactly risk_amount USD if SL is hit

risk_amount = balance × (risk_percent / 100)
loss_per_lot = sl_distance × pip_value_per_lot   # sl_distance in price units (same as D1_ATR)
lot_size = risk_amount / loss_per_lot

Example:
  balance = $10,000
  risk_percent = 1.0%
  risk_amount = $100
  sl_distance = 20   # price units (e.g. $20 ATR move)
  pip_value_per_lot = $10.00
  loss_per_lot = 20 × $10 = $200
  lot_size = $100 / $200 = 0.50 lots
```

---

## ATR-Based SL vs Fixed Pips

Fixed SL (e.g., always 30 pips) fails when:
- XAUUSD volatility expands (NFP/FOMC) → SL too tight, gets hit by noise
- XAUUSD volatility contracts (Asian session) → SL too wide, poor R:R

ATR-based SL (SL = D1_ATR × multiplier) adapts automatically:
- High ATR day (40 pips) → SL = 60 pips (gives room)
- Low ATR day (15 pips) → SL = 22.5 pips (tighter, better R:R)

Using D1 ATR (not H1) for SL placement is intentional: D1 captures daily range volatility which determines how far price can realistically move against a position during the day.

---

## Recovery Mode — SMC Context

In SMC trading, consecutive losses often indicate a regime shift (e.g., market became ranging, HTF bias changed). Recovery mode serves two purposes:
1. **Capital preservation**: Smaller lots limit further damage
2. **Signal quality gate**: Only high-confidence setups during recovery prevents further losses from marginal signals

Recovery exits on `recovery_profit_target` pips (not # of trades) because pip-based target is more meaningful — it represents actual P&L recovery, not just "survived N trades."

---

## 5% Hard Cap Rationale

Even if risk_percent is misconfigured to 10%, the 5% hard cap prevents a single trade from being catastrophic. With a max daily drawdown of 5%, a single trade hitting the hard cap would already trigger the drawdown guard. The hard cap is a redundant safety layer.

Formula application order (D-007):
1. Calculate raw lot from formula
2. Reduce if risk_amount > 5% of balance (hard cap)
3. Clamp to [min_lot, max_lot]

This order matters: min_lot floor must not override the 5% cap.

---

## Cooldown After SL

Psychological research on trading shows that the period immediately after a loss carries the highest risk of revenge trading. The cooldown period (2 hours default) enforces a mandatory pause. This is particularly relevant for algo systems where the strategy might detect another setup immediately after a loss in the same session.

---

## Session Tracking for Trade Limits

Tracking per-session trades (not just daily total) prevents concentrating all trades in one session. London/NY overlap is the highest-liquidity period — the system may take both its allowed trades there, then be blocked for the rest of the day even with daily_trades < max. This is intentional: overlap setups are the highest quality.
