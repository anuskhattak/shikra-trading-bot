
---
description: Review config.yaml against Shikra project requirements defined in CLAUDE.md. Reports mismatches, missing values, and unsafe settings.
---

## Goal

Validate `config.yaml` against the Shikra trading system requirements in `CLAUDE.md`. This is a **read-only** review — no files are modified. Output a structured report with severity-rated findings and fix suggestions.

## Execution Steps

### 1. Load Files

Read both files from repo root:
- `config.yaml` — current configuration
- `CLAUDE.md` — project requirements and guarantees

### 2. Validate Each Section

#### A. Broker / Timeframes
- `htf` MUST be D1 (daily structure analysis for Gold)
- `mtf` MUST be H4 (confirmation timeframe)
- `ltf` MUST be H1 (entry precision)
- `magic_number` must be present and non-zero
- `max_spread_points` must be defined (Gold spread can spike — a limit is required)
- `slippage_points` must be defined

#### B. Risk Parameters
- `risk_per_trade_pct` MUST be between 0.5 and 2.0 (CLAUDE.md: "risk controls prevent catastrophic losses")
- `max_daily_drawdown_pct` MUST be ≤ 10.0 (CLAUDE.md: "daily drawdown limit enforced")
- `max_open_positions` MUST be ≥ 1 and ≤ 5
- `min_risk_reward` MUST be ≥ 2.0 (CLAUDE.md: minimum R:R for profitability)
- `decimal_precision` MUST be 5 (CLAUDE.md: "broker decimal precision 5 decimal places for XAUUSD")

#### C. SMC Parameters
- `bos_lookback_bars` must be present and > 0
- `fvg_min_gap_points` must be present and > 0
- `ob_lookback_bars` must be present and > 0
- `liquidity_sweep_buffer` must be present and > 0
- All values must be reasonable for XAUUSD Gold (not copied from forex pairs)

#### D. Sessions
- `london` session must be defined with `start`, `end`, `timezone`
- `new_york` session must be defined with `start`, `end`, `timezone`
- `timezone` MUST be `UTC` for both (broker time consistency)
- London hours: 08:00–12:00 UTC is valid range
- New York hours: 13:00–17:00 UTC is valid range

#### E. ML Settings
- `confidence_threshold` MUST be between 0.5 and 0.9 (CLAUDE.md: "low confidence → manual review")
- `model_path` must be defined

#### F. Logging
- `trades_log` MUST point to `logs/trades.json` (CLAUDE.md requirement)
- `signals_log` MUST point to `logs/false_signals.json` (CLAUDE.md requirement)
- Both paths must match what CLAUDE.md specifies exactly

### 3. Severity Assignment

- **CRITICAL** — Value violates a CLAUDE.md guarantee (e.g., risk > 2%, wrong log path, missing stop loss requirement)
- **HIGH** — Value is unsafe or outside recommended range (e.g., R:R < 2, spread limit too high)
- **MEDIUM** — Value is present but suboptimal for Gold/XAUUSD
- **LOW** — Style, naming, or minor completeness issue
- **OK** — Passes validation

### 4. Output Report

Produce a Markdown report in this format:

```
## Config Review Report — Shikra

| Section | Key | Current Value | Expected | Severity | Note |
|---------|-----|---------------|----------|----------|------|
```

Then:

**Summary:**
- Total checks run: N
- CRITICAL: N
- HIGH: N
- MEDIUM: N
- LOW: N
- OK: N

**Overall Status:** PASS / FAIL (FAIL if any CRITICAL or HIGH issue exists)

If PASS: "config.yaml is aligned with CLAUDE.md requirements. Safe to proceed."
If FAIL: List the must-fix items before implementation begins.

### 5. Fix Suggestions

For every CRITICAL and HIGH finding, provide the exact corrected YAML snippet:

```yaml
# Fix for <issue>
key: corrected_value
```

## Operating Principles

- **NEVER modify files** — read-only analysis only
- **NEVER assume** a missing key is fine — flag it as CRITICAL if it maps to a CLAUDE.md guarantee
- **Always cite CLAUDE.md** — every finding must reference which guarantee or rule it violates
- Report zero issues gracefully with a PASS status

## User Input

```text
$ARGUMENTS
```

If the user provides a specific section to focus on (e.g., `/review-config risk`), limit the review to that section only.
