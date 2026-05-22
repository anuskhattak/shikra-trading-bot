---
id: PHR-0042
title: Spec005 Critical Issues C1 C2 C3 Fixed
stage: misc
date: 2026-05-20
surface: agent
model: claude-sonnet-4-6
feature: 005-execution-engine
branch: 005-execution-engine
user: anaskhattak
command: /sp.analyze → manual fix
labels: [fr-017, tradeauditentry, constitution, max-loss-usd, entry-reason, exit-reason, c3-conflict]
links:
  spec: specs/005-execution-engine/spec.md
  ticket: null
  adr: history/adr/
  pr: null
files:
  - specs/005-execution-engine/spec.md
  - specs/005-execution-engine/data-model.md
  - specs/005-execution-engine/contracts/execution_engine.md
  - specs/005-execution-engine/tasks.md
tests:
  - none
---

## Prompt

inhain fix karo (referring to 3 CRITICAL issues from PHR-0041 /sp.analyze report)

## Response snapshot

All 3 CRITICAL issues resolved across 4 spec artifacts. C1+C2: added `max_loss_usd`, `entry_reason`, `exit_reason` to FR-017 (spec.md), TradeAuditEntry dataclass (data-model.md, contracts/execution_engine.md), and updated T002/T006 task descriptions. C3: inspected pre-existing order_manager.py changes (timeout guard + margin-level check — _log_trade() untouched), confirmed T008 not blocked, added C3 warning note to T008 in tasks.md.

## Outcome

- ✅ Impact: spec005 artifacts now fully constitution-compliant. TradeAuditEntry has 19 fields (was 16). FR-017 field list matches CLAUDE.md guarantees. T008 annotated with pre-existing conflict context so implementer doesn't blindly overwrite existing work.
- 🧪 Tests: T003 (models tests) and T007 (audit_logger tests) must also be updated during implementation to assert new fields — noted in T002/T006 descriptions
- 📁 Files: 4 spec artifacts updated; 0 source files touched
- 🔁 Next prompts: `/sp.implement` — start with T001 (package skeleton), T002 will now implement 19-field TradeAuditEntry
- 🧠 Reflection: C3 turned out to be a non-blocker — the pre-existing modifications only added broker-layer safety features (_call_with_timeout, margin-level check) without touching the logging path that T008 targets. Noting it in T008 is the right minimal fix rather than reverting or restructuring.

## Evaluation notes (flywheel)

- Failure modes observed: data-model.md Edit failed on first attempt due to invisible whitespace difference — required Read to see exact characters before retrying
- Graders run and results (PASS/FAIL): PASS — all 4 files updated, no placeholders remaining, constitution compliance restored
- Prompt variant (if applicable): "inhain fix karo" — Hindustani imperative referring to analysis findings
- Next experiment (smallest change to try): Add constitution field checklist to spec template so FR-017-equivalent sections always include the CLAUDE.md-mandated fields by default
