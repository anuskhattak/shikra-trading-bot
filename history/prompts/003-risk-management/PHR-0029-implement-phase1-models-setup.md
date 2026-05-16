---
id: PHR-0029
title: implement-phase1-models-setup
stage: green
date: 2026-05-16
surface: claude-code-cli
model: claude-sonnet-4-6
feature: 003-risk-management
branch: 003-risk-management
user: anaskhattak
command: /sp.implement specs/003-risk-management phase1
labels: [implement, phase1, models, setup, green]
links:
  spec: specs/003-risk-management/spec.md
  ticket: —
  adr: —
  pr: —
files:
  - src/risk/models.py
  - config.yaml
  - .gitignore
  - logs/risk_events.json
  - specs/003-risk-management/tasks.md
  - specs/003-risk-management/checklists/implementation-review.md
tests:
  - checkpoint: python -c "from src.risk.models import RiskCalculation, RiskState, TradeAllowedResult" → PASS
---

## Prompt

/sp.implement specs/003-risk-management phase1

## Response snapshot

Executed Phase 1 (Setup & Models) — all 4 tasks complete. Checkpoint PASS.

**Pre-implementation state:**
- `src/risk/__init__.py`: existed (empty, T001 already done)
- `config.yaml` risk section: existed but with stale fields from spec001 era (risk_per_trade_pct, max_open_positions, etc.)
- `logs/risk_events.json`: missing
- `src/risk/models.py`: missing

**T001 (pre-existing):** `src/risk/__init__.py` empty placeholder already in place.

**T002 — config.yaml risk section replaced:**
Old fields (risk_per_trade_pct, max_daily_drawdown_pct, max_open_positions, min_risk_reward, decimal_precision) replaced with full spec003 schema:
risk_percent, max_lot_size, min_lot_size, pip_value_per_lot, sl_atr_multiplier, tp1_rr_ratio, tp2_rr_ratio, max_daily_drawdown, max_trades_per_day, max_trades_per_session, cooldown_after_sl_hours, max_consecutive_losses, recovery_lot_multiplier, recovery_min_confidence, recovery_profit_target_pips

**T003 — logs/risk_events.json:**
- Created as empty JSON array `[]` placeholder
- Added `logs/risk_events.json` to `.gitignore` (alongside existing specific log entries)

**T004 — src/risk/models.py:**
- `RecoveryReason` enum: CONSECUTIVE_LOSSES
- `BlockReason` enum: DRAWDOWN_LIMIT, DAILY_TRADE_LIMIT, SESSION_TRADE_LIMIT, COOLDOWN_ACTIVE, NOT_BLOCKED
- `RiskCalculation` dataclass: 8 fields; invariant comments documenting LONG/SHORT price ordering and lot/risk caps
- `RiskState` dataclass: 7 fields; day_start_equity required; all others defaulted for clean initialization
- `TradeAllowedResult` dataclass: allowed + reason

**Checkpoint:** `from src.risk.models import RiskCalculation, RiskState, TradeAllowedResult` + all fields verified → PASS

**CHK items marked done:** CHK001, CHK002 (Models), CHK049, CHK050 (Infrastructure) = 4/57

## Outcome

- ✅ Impact: Phase 1 foundation complete. All downstream phases (lot_calculator, drawdown_guard, trade_limits, recovery_mode) can now import from models.py.
- 🧪 Tests: Checkpoint import test PASS. Unit tests come in Phase 2+.
- 📁 Files: src/risk/models.py (created), config.yaml (risk section replaced), .gitignore (1 entry added), logs/risk_events.json (created)
- 🔁 Next prompts: /sp.implement specs/003-risk-management phase2
- 🧠 Reflection: config.yaml had stale risk fields from spec001 that needed REPLACEMENT, not additive update. T002 would fail silently if we only checked for existence of the risk: key — checking field names was essential.

## Evaluation notes (flywheel)

- Failure modes observed: Prerequisites script detected wrong feature (002 not 003). Worked around by using FEATURE_DIR manually — a known limitation of the script for non-active features.
- Graders run and results (PASS/FAIL): Checkpoint import PASS; all 5 dataclass field sets match data-model.md.
- Prompt variant (if applicable): —
- Next experiment: Add --feature-dir override flag to check-prerequisites.ps1 to avoid manual workaround.
