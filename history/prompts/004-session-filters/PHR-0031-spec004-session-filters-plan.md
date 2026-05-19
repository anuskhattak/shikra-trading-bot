---
id: PHR-0031
title: spec004-session-filters-plan
stage: plan
date: 2026-05-19
surface: claude-code-cli
model: claude-sonnet-4-6
feature: 004-session-filters
branch: 004-session-filters
user: anaskhattak
command: /sp.plan
labels: [plan, session-filters, filters, zoneinfo, holidays, atr, news-calendar]
links:
  spec: specs/004-session-filters/spec.md
  ticket: ""
  adr: ""
  pr: ""
files:
  - specs/004-session-filters/plan.md
  - specs/004-session-filters/research.md
  - specs/004-session-filters/data-model.md
  - specs/004-session-filters/quickstart.md
tests:
  - tests/unit/test_filters_session.py
  - tests/unit/test_filters_spread.py
  - tests/unit/test_filters_news.py
  - tests/unit/test_filters_volatility.py
  - tests/unit/test_filters_trade_gate.py
  - tests/integration/test_filters_pipeline.py
---

## Prompt

User invoked `/sp.plan` for Spec 004 — Session & Pre-Trade Filters.

Context: Spec 004 spec.md fully written and all gaps fixed in prior session. Clarification session ran (Q1 answered: hybrid news calendar) then reverted at user request. Plan proceeding from clean spec.

## Response snapshot

**Phase 0 (Research)** resolved all unknowns:
- DST handling: `zoneinfo` stdlib (Python 3.9+), not `pytz` — no external dependency
- Holiday detection: `holidays.country_holidays("GB")` covers all 5 spec holidays including Good Friday/Easter
- Session design: local market hours + named IANA timezone in config (auto-DST)
- Spread: `ask - bid` directly in USD for XAUUSD (no conversion needed)
- ATR reference: ATR(14) H1 current vs 50-bar rolling mean as reference
- News calendar v1: local JSON file `data/news_calendar.json` — no network dep in filter module

**Phase 1 (Design)** produced:
- 9 key design decisions (D-001 through D-009)
- 6 modules designed: models.py, session_filter.py, spread_filter.py, news_filter.py, volatility_filter.py, trade_gate.py
- Complete data model: 4 enums, 4 dataclasses, all reason codes, log format
- config.yaml additions: sessions (local_open/close/timezone), filters (spread/news/volatility)
- 7-phase delivery plan

**Architecture**: Broker-agnostic module; all values (spread_usd, current_atr, reference_atr, news_events) passed by caller. Same pattern as spec003 (ATR passed by caller). Short-circuit on first BLOCKED filter (Session→Spread→News→Volatility order).

## Outcome

- ✅ Impact: Implementation-ready plan; `src/filters/` can be built directly from plan.md + data-model.md
- 🧪 Tests: 6 test files mapped to FRs; unit tests per filter + integration pipeline test
- 📁 Files: plan.md, research.md, data-model.md, quickstart.md created in specs/004-session-filters/
- 🔁 Next prompts: `/sp.tasks` to generate tasks.md; then `/sp.implement` to build src/filters/
- 🧠 Reflection: D-002 (zoneinfo + local time config) and D-006 (JSON file v1) are the highest-impact decisions — they keep the module testable and dependency-free

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run and results (PASS/FAIL): N/A
- Prompt variant (if applicable): N/A
- Next experiment: Verify `holidays` lib covers all 5 spec holidays with a quick unit test at implementation time
