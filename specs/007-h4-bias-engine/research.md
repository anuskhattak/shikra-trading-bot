# Research: H4 Bias Engine

**Feature**: 007-h4-bias-engine  
**Date**: 2026-06-12  
**Phase**: Phase 0 — Research & Decision Resolution

---

## RES-001: Bias Classification Algorithm

**Decision**: Use fractal swing-point sequences (HH/HL for bullish, LH/LL for bearish) detected via the existing `detect_swing_points()` fractal detector.

**Rationale**: The codebase already has a tested, fractal-confirmed swing detector in `src/engine/swing.py`. Reusing it ensures consistency between the SMC Engine (spec002) and the H4 Bias Engine. Fractal confirmation requires N candles on each side, which prevents false pivots from unconfirmed wicks.

**Alternatives considered**:
- EMA crossover (200/50 EMA): Lagging indicator, conflicts with SMC price-action philosophy
- Consecutive close direction: Too noisy; whipsaw on H4 without structure confirmation
- Linear regression slope: Requires scipy dependency; over-engineered for binary bias

---

## RES-002: Bias Enum Location

**Decision**: Extend the existing `Bias` enum in `src/engine/models.py` by adding `RANGING = "RANGING"`. Keep `NEUTRAL` for callers that have no H4 data.

**Rationale**: `scorer.py` already imports `Bias` and uses it in `htf_bias` parameter. Adding `RANGING` to the same enum is the least disruptive change — no new imports needed in scorer, pipeline, or engine.

**Semantic distinction**:
- `NEUTRAL`: Caller has no H4 bias information (default, pre-module-init)
- `RANGING`: H4 analysis was performed and confirmed consolidation → trades blocked

**Alternatives considered**:
- Separate `H4Bias` enum in `src/analysis/h4_bias.py` with mapping function: Adds an indirection layer and a mapping function that serves no purpose other than bridging two identical enum sets.

---

## RES-003: RANGING Trade Block Placement

**Decision**: Block in `score_and_assemble()` as the first check, before scoring. Log to `false_signals.json` with reason `H4_RANGING`.

**Rationale**: Blocking in the scorer ensures the false_signals audit trail captures RANGING rejections with the same schema as other rejections. The pipeline could block earlier, but that bypasses the audit log.

**Alternatives considered**:
- Block in `pipeline.py` before calling `generate_signal()`: Faster but skips audit logging. Audit trail is a project requirement (Core Guarantee #3).
- Block in `trade_gate.py` filter: Filters are for session/spread/news/volatility — adding H4 structural state there blurs responsibilities.

---

## RES-004: H4 Alignment Boost in Scorer

**Decision**: Add `h4_alignment: 0.20` weight to `weights` dict; apply before the threshold check. Then apply `mtf_boost: 1.30` multiplier when alignment is present.

**Rationale**: The documentation specifies +2.0 points in a 0–10+ scoring system. The implementation uses normalized 0–1 confidence. The existing weights sum to ~1.0 (0.40 + 0.30 + 0.20 + 0.10). Adding 0.20 for H4 alignment reflects the relative importance documented in section 4.6 of SHIKRA_DOCUMENTATION.md. The 1.3x MTF multiplier is applied after alignment boost so the boost itself also benefits from the multiplier.

**Weight accounting**: Maximum confidence with full alignment: `min(1.0, (0.40 + 0.30 + 0.20 + 0.10 + 0.20) * 1.30) = min(1.0, 1.56) = 1.0` — naturally clipped to 1.0.

---

## RES-005: EntrySignal Field Placement

**Decision**: Add `h4_bias` and `h4_bias_strength` as the last two fields of `EntrySignal` with default values (`Bias.NEUTRAL`, `0.0`).

**Rationale**: Python dataclasses require fields with defaults to come after fields without defaults. Adding at the end avoids any positional argument breakage in existing callers (backtest engine, execution engine tests).

---

## RES-006: smc_engine.py Audit

**Finding**: `generate_signal()` in `src/engine/smc_engine.py` accepts `htf_bias: Bias` and passes it to `score_and_assemble()`. The `htf_bias_strength` parameter does not currently exist there — it must be threaded through `smc_engine.py` as well.

**Decision**: Add `htf_bias_strength: float = 0.0` parameter to `generate_signal()` in `smc_engine.py`, pass through to `score_and_assemble()`.

---

## RES-007: LSTM Replaceability Interface

**Decision**: The interface contract is `refresh(h4_bars: list[OHLCVBar]) -> H4BiasResult`. In spec012, `LSTMBiasService` will implement the same `refresh()` method and return the same `H4BiasResult` type. The pipeline accepts any object with that interface.

**Rationale**: Structural subtyping (duck typing) is sufficient in Python. No abstract base class needed at this stage — the pipeline calls `h4_bias_service.refresh(h4_bars)` and `h4_bias_service.get_bias()`. If spec012 produces the same H4BiasResult, it's a drop-in replacement.

---

## RES-008: Backtest Engine Compatibility

**Finding**: `src/backtest/backtest_engine.py` calls `run_pipeline()` — it must be updated to pass a `H4BiasService` instance (or a mock). No breaking change to backtest logic; just a new dependency injection.

**Decision**: Backtest engine instantiates `H4BiasService(config)` once at startup and passes it to `run_pipeline()` on each bar. Same pattern as `ATRService`.
