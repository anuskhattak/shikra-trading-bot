---
id: PHR-0035
title: spec004-phase1-implement
stage: green
date: 2026-05-19
surface: claude-code-cli
model: claude-sonnet-4-6
feature: 004-session-filters
branch: 004-session-filters
user: anaskhattak
command: /sp.implement (phase1)
labels: [implement, session-filters, phase1, models]
links:
  spec: specs/004-session-filters/spec.md
  ticket: ""
  adr: ""
  pr: ""
files:
  - src/filters/__init__.py
  - src/filters/models.py
  - config.yaml
  - data/news_calendar.json
tests: []
---

## Prompt

User said "phase1 implement karo" — implement Phase 1 (Setup & Models) tasks T001–T004 for spec004 session-filters.

## Response snapshot

Phase 1 (4 tasks) completed:

**T001** — `src/filters/__init__.py` already existed (empty placeholder). No action needed.

**T002** — `config.yaml` updated:
- `sessions:` block replaced (old UTC-based asia/london/new_york → new local-time format london/new_york with local_open="08:00", local_close="17:00", IANA timezone, enabled)
- `filters:` section added (spread/news/volatility config)
- `logging.filters_log: logs/filter_decisions.json` added

**T003** — `data/news_calendar.json` created with 3 HIGH-impact stubs (NFP, FOMC, CPI); `.gitignore` already contains `logs/` entry covering `logs/filter_decisions.json`.

**T004** — `src/filters/models.py` implemented: 4 enums (`FilterResult`, `SessionLabel`, `VolatilityRegime`, `NewsImpact`) + 5 dataclasses (`SessionWindow`, `FilterDecision`, `TradeGateResult`, `NewsEvent`, `VolatilityReading`) — all fields from data-model.md.

**Checkpoint**: `from src.filters.models import FilterResult, TradeGateResult, NewsEvent` → "All imports OK" ✅

## Outcome

- ✅ Impact: Phase 1 complete; all 4 tasks done; checkpoint passed
- 🧪 Tests: No tests in Phase 1 (models only)
- 📁 Files: src/filters/models.py (created), config.yaml (updated), data/news_calendar.json (created)
- 🔁 Next prompts: Phase 2 (session_filter) + Phase 3 (spread_filter) in parallel

## Evaluation notes (flywheel)

- Failure modes observed: None
- Graders run: Checkpoint import test passed
