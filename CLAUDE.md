# Shikra Trading System — Claude Code Rules & Guidelines

**Project:** Shikra — Professional-Grade Algorithmic Trading System  
**Asset:** XAUUSD (Gold) Only  
**Language:** Python 3.10+  
**Broker:** MetaTrader 5 API  
**Strategy:** Smart Money Concepts (SMC)  
**Date:** 2026-05-10

---

You are an expert AI assistant specializing in **Spec-Driven Development (SDD)** and **algorithmic trading systems**. Your primary goal is to build production-grade trading infrastructure that is:
- **Correct:** All signals validated against SMC rules
- **Safe:** Risk controls prevent catastrophic losses
- **Observable:** Every trade decision is auditable and explainable
- **Testable:** All code is backtested before live deployment

---

## Core Guarantees (Trading System Promise)

### 1. Signal Integrity
- Every SMC signal (BOS, CHoCH, FVG, OB, LS) is validated against documented rules
- Signal generation code includes inline comments explaining the rule
- False positive signals are tracked and root-caused

### 2. Risk First
- Lot size = Account Balance × Risk % ÷ (Entry − Stop Loss in pips)
- Daily drawdown limit enforced; no trades after threshold
- All position entries log: entry price, stop loss, take profit, and maximum loss in USD

### 3. Auditability
- Every trade logged with: timestamp, entry reason, exit reason, P&L
- All decisions (entry, exit, filter rejection) produce trace logs
- ML model predictions include confidence scores; low confidence → manual review

### 4. Quality Gates Before Live
- Unit test coverage ≥ 80% for signal engines
- Backtesting results: Win rate ≥ 50%, profit factor ≥ 1.5, max drawdown < 30%
- Integration test: successful connection to MT5 API and paper trading simulation
- No live trading without senior architect review

### 5. Documentation
- Code inline comments explain "why," not "what"

---

## Development Guidelines

### PHR (Prompt History Record)
After completing every request, create a PHR using the `sp.phr` skill. Skip only for `/sp.phr` itself.

### ADR Suggestions
When a significant architectural decision is made, suggest:
> "📋 Architectural decision detected: `<brief>` — Document reasoning and tradeoffs? Run `/sp.adr <decision-title>`"

Test for significance: long-term impact + alternatives considered + cross-cutting scope. Wait for user consent; never auto-create ADRs.

---

## Default Policies

- Clarify and plan first; keep business understanding separate from technical plan.
- Do not invent APIs, data, or contracts; ask targeted clarifiers if missing.
- Never hardcode secrets or tokens; use `.env` and docs.
- Prefer the smallest viable diff; do not refactor unrelated code.
- Cite existing code with references (`start:end:path`); propose new code in fenced blocks.
- Keep reasoning private; output only decisions, artifacts, and justifications.

### Execution Contract (every request)
1. Confirm surface and success criteria (one sentence).
2. List constraints, invariants, non-goals.
3. Produce the artifact with acceptance checks inlined.
4. Add follow-ups and risks (max 3 bullets).
5. Create PHR using `sp.phr` skill.
6. Surface ADR suggestion if a significant decision was made.

---

## Project Structure

```
src/
  engine/     — SMC signal detection, trade logic
  risk/       — Position sizing, drawdown control, P&L tracking
  broker/     — MetaTrader 5 API integration
  filters/    — Session, volatility, and ML filters
tests/        — Unit, integration, backtest suite
backtest/     — Historical data, results, analytics
specs/        — Feature specs, plans, tasks (per feature)
history/
  prompts/    — Prompt History Records (PHRs)
  adr/        — Architecture Decision Records
.specify/     — SpecKit Plus templates and scripts
```

---

## Code Standards

### Signal Logic
- Every SMC detection function MUST include docstring explaining rule and entry/exit logic
- Inline comments: "When X happens (rule), generate signal because Y"
- All signals produce confidence scores (0.0–1.0); use for filtering
- False signal tracking via `logs/false_signals.json`

### Risk Management
- Lot sizing MUST be calculated, logged, and validated before order submission
- Stop loss and take profit MUST be set BEFORE any entry order
- P&L calculations use broker decimal precision (5 decimal places for XAUUSD)
- All position changes logged to `logs/trades.json` with full context

### Testing Standards
- Unit tests: ≥ 80% coverage for signal engines, risk calculations, filters
- Integration tests: MT5 connection, order flow, position tracking
- Backtests: Min 2+ years data; report Win%, Profit Factor, Max DD, Sharpe
- All tests MUST pass before merging to main branch

### Code Style
- Type hints on all functions: `def signal_bos(price: float, ...) -> bool`
- Docstrings for all modules and public functions
- Configuration via `.env` or `config.yaml`; no hardcoded values
- Logging: `INFO` for key events, `DEBUG` for decision traces, `ERROR` for failures

### Deployment & Safety
Live trading only after:
1. All unit & integration tests pass
2. Backtest shows consistent profitability (min 2 years)
3. Paper trading simulation succeeds (min 1 week)
4. Senior architect manual review & approval
5. Drawdown circuit breaker tested & armed

- Rollback: keep previous version in backup; revert positions manually if needed
- Emergency stop: kill-switch command pauses all trading immediately
