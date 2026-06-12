# Implementation Review Checklist: H4 Bias Engine

**Purpose**: Verify implementation correctness and completeness before merging to master
**Created**: 2026-06-12
**Feature**: [spec.md](../spec.md) | [tasks.md](../tasks.md)

---

## Phase 1 & 2: Config & Models

- [x] `config.yaml` has `analysis.h4_bias` block with `lookback_bars`, `fractal_n`, `bullish_strength_threshold`, `bearish_strength_threshold`
- [x] `config.yaml` has `smc_engine.weights.h4_alignment` and `smc_engine.weights.mtf_boost`
- [x] `Bias.RANGING = "RANGING"` added to `src/engine/models.py`
- [x] `EntrySignal` has `h4_bias: Bias` field with default `Bias.NEUTRAL` (at end of dataclass)
- [x] `EntrySignal` has `h4_bias_strength: float` field with default `0.0` (at end of dataclass)
- [x] `PipelineContext` has `h4_bias_result: Optional[H4BiasResult]` with default `None`
- [x] No positional-argument breakage in existing callers of `EntrySignal()`

---

## Phase 3: H4BiasService Core

- [x] `src/analysis/h4_bias.py` exists
- [x] `H4BiasResult` is a frozen dataclass with fields: `bias`, `strength`, `swing_count`, `timestamp`
- [x] `classify_bias()` separates swing points into HIGHs and LOWs
- [x] `classify_bias()` counts HH/HL pairs for bullish and LH/LL pairs for bearish
- [x] `classify_bias()` returns `(RANGING, 0.0)` when fewer than 2 swings of same type
- [x] `classify_bias()` strength score is clipped to `[0.0, 1.0]`
- [x] `H4BiasService.__init__()` raises `KeyError` if `config['analysis']['h4_bias']` is missing
- [x] `H4BiasService.refresh()` calls `detect_swing_points()` from `src/engine/swing.py` (no duplicate swing logic)
- [x] `H4BiasService.refresh()` converts `list[OHLCVBar]` to DataFrame before calling `detect_swing_points()`
- [x] `H4BiasService.refresh()` returns `H4BiasResult(bias=Bias.RANGING, strength=0.0, swing_count=0)` on cold start (< lookback bars)
- [x] `H4BiasService.refresh()` never raises — catches all exceptions, logs WARNING, returns last cached or RANGING
- [x] `H4BiasService.get_bias()` returns RANGING/0.0 before first successful `refresh()`
- [x] `H4BiasService.is_ready()` returns `True` only after at least one successful `refresh()`
- [x] `src/analysis/__init__.py` exports `H4BiasService` and `H4BiasResult`
- [x] `python -c "from src.analysis.h4_bias import H4BiasService, H4BiasResult; print('OK')"` runs without error

---

## Phase 3: RANGING Block in Scorer

- [x] `score_and_assemble()` in `src/engine/scorer.py` blocks on `Bias.RANGING` as the **first** check (before component scoring)
- [x] RANGING block calls `_log_and_discard()` with reason containing `"H4_RANGING"`
- [x] RANGING block returns `Direction.NONE` signal with `confidence == 0.0`
- [x] RANGING rejection is written to `logs/false_signals.json`

---

## Phase 4: Alignment Boost & MTF Multiplier

- [x] `generate_signal()` in `src/engine/smc_engine.py` has `htf_bias_strength: float = 0.0` parameter
- [x] `generate_signal()` passes `htf_bias_strength` through to `score_and_assemble()`
- [x] `score_and_assemble()` has `htf_bias_strength: float = 0.0` parameter (backward compatible)
- [x] H4 alignment boost fires when `(BULLISH + LONG)` or `(BEARISH + SHORT)`
- [x] Alignment boost adds `weights.get("h4_alignment", 0.20)` to confidence
- [x] `"H4_ALIGN"` appended to `components` list when alignment fires
- [x] MTF multiplier (`weights.get("mtf_boost", 1.30)`) applied to confidence after alignment boost
- [x] Confidence capped at `1.0` after multiplier
- [x] No boost fires for counter-trend signals (BULLISH + SHORT, BEARISH + LONG)
- [x] No boost fires for `Bias.NEUTRAL` signals
- [x] All return sites in `scorer.py` (accepted signal, `_none_signal`, `_log_and_discard`) embed `h4_bias` and `h4_bias_strength` in `EntrySignal`

---

## Phase 4: Pipeline Wiring

- [x] `run_pipeline()` in `src/orchestrator/pipeline.py` has `h4_bias_service` parameter
- [x] Stage 0 calls `h4_bias_service.refresh(ctx.bars.get(Timeframe.H4, []))` before Stage 1
- [x] `ctx.h4_bias_result` is populated with the `H4BiasResult` from Stage 0
- [x] Stage 2 passes `htf_bias=ctx.h4_bias_result.bias` and `htf_bias_strength=ctx.h4_bias_result.strength` to `generate_signal()`
- [x] `src/backtest/backtest_engine.py` instantiates `H4BiasService(config)` at startup
- [x] `src/backtest/backtest_engine.py` passes `h4_bias_service` to every `run_pipeline()` call
- [x] All other callers of `run_pipeline()` (strategy_orchestrator, tests) updated

---

## Phase 5: Audit Logging

- [x] `H4BiasService.refresh()` logs `INFO` when bias state changes: `"H4 bias transition: {} → {}"`
- [x] Every accepted `EntrySignal` has non-null `h4_bias` and `h4_bias_strength`
- [x] Rejected signals (RANGING block, counter-trend, threshold) also carry `h4_bias` field

---

## Tests

- [x] `tests/test_h4_bias.py` exists
- [x] `test_bullish_bias_hh_hl` passes
- [x] `test_bearish_bias_lh_ll` passes
- [x] `test_ranging_mixed_structure` passes
- [x] `test_cold_start_insufficient_bars` passes
- [x] `test_ranging_blocks_scorer` passes
- [x] `test_alignment_boost_added` passes
- [x] `test_mtf_multiplier_applied` passes
- [x] `test_pipeline_wires_h4_service` passes
- [x] `test_entry_signal_carries_bias` passes
- [x] `test_no_counter_trend_boost` passes
- [x] `test_neutral_bias_no_block_no_boost` passes
- [x] `pytest tests/test_h4_bias.py` — all pass
- [x] `pytest tests/` — zero regressions across spec002–spec006, spec009

---

## LSTM Replaceability Gate

- [x] `H4BiasService` interface is limited to: `refresh()`, `get_bias()`, `is_ready()`
- [x] Pipeline accesses only these 3 methods — no other `H4BiasService` attributes used
- [x] `H4BiasResult` return type is importable from `src.analysis.h4_bias` (shared with future LSTM service)

---

## Code Quality

- [x] No MT5 imports anywhere in `src/analysis/h4_bias.py`
- [x] No implementation comments explaining WHAT the code does — only WHY comments where non-obvious
- [x] Type hints on all public functions in `h4_bias.py`
- [x] Docstrings on `H4BiasService`, `classify_bias()`, `H4BiasResult`
- [x] `loguru` used for all logging (not `print` or stdlib `logging`)
- [x] No hardcoded threshold values — all read from `config`

---

## Notes

- All items must pass before `/sp.git.commit_pr`
- RANGING block position in scorer is critical — must be FIRST check or audit log misses early rejects
- `_none_signal()` and `_log_and_discard()` helpers in scorer must also embed h4_bias fields
