# ADR-0001: Kill-Switch Safety Mechanism

- **Status:** Accepted
- **Date:** 2026-05-20
- **Feature:** 005-execution-engine
- **Context:** The execution engine requires a way for an operator to immediately halt all new order placement without restarting the bot process (FR-014). The kill-switch must take effect within one evaluation cycle (≤60 seconds) of activation (FR-015). It must survive process restarts (the bot may restart mid-session), and it must be activatable from a terminal, monitoring script, or external dashboard. The existing positions must continue to be managed normally while new entries are blocked.

## Decision

**Kill-switch state is persisted to `logs/kill_switch.json`** with the following integrated design:

- **Storage**: `logs/kill_switch.json` — `{"active": bool, "activated_at": ISO-UTC, "activated_by": str}`
- **Write pattern**: Atomic write via temp-file + rename (`Path.replace()`) — prevents corrupt reads during write
- **Read pattern**: Read on every pre-flight check; in-memory bool cached per evaluation cycle (avoids repeated disk I/O on the hot path)
- **Default state**: File absent = inactive (safe default — no action needed to keep bot running normally)
- **Public API**: `activate_kill_switch(path, reason)`, `deactivate_kill_switch(path)`, `is_kill_switch_active(path)` in `src/execution/kill_switch.py`
- **Effect boundary**: Blocks `execute_signal()` only — `manage_open_positions()` continues normally (FR-014 intent)

## Consequences

### Positive

- Operator can activate from any shell without bot code knowledge: `echo '{"active":true}' > logs/kill_switch.json`
- No IPC, socket, or network dependency — works on an isolated Windows trading machine
- Survives process restart: bot reads file on startup and respects the flag
- Activatable from external monitoring scripts, Telegram bots, or dashboards by writing the JSON file
- Zero-latency check (file read + in-memory bool) on the hot pre-flight path

### Negative

- File write by operator must be valid JSON — malformed write causes `is_kill_switch_active()` to return False (safe but silent; kill intent could be missed)
- Mitigation: Public API `activate_kill_switch()` always writes valid JSON; only raw file edits bypass this

## Alternatives Considered

**Alternative A: Pure in-memory flag**
- `ExecutionEngine._kill_switch: bool` toggled by method call
- Rejected: Lost on process restart; no way to activate without attaching to the running process (no IPC on Windows without additional infrastructure)

**Alternative B: Database row (SQLite or Redis)**
- `kill_switch` table with a boolean column, polled each cycle
- Rejected: Requires a database process; overkill for a single binary flag with at most one writer and one reader; adds a dependency failure mode (bot can't trade if DB is down)

**Alternative C: OS process signal (SIGUSR1)**
- `signal.signal(signal.SIGUSR1, handler)` to toggle the flag
- Rejected: `SIGUSR1` is not reliably available on Windows (only partial support in Python's `signal` module on Windows); would require platform-specific code

**Alternative D: Environment variable**
- `KILL_SWITCH=1` set in the running process environment
- Rejected: Environment variables cannot be changed for a running process from outside on Windows without attaching a debugger; does not survive restarts in the intended way

## References

- Feature Spec: specs/005-execution-engine/spec.md (FR-014, FR-015, US4)
- Implementation Plan: specs/005-execution-engine/plan.md (D-001)
- Research: specs/005-execution-engine/research.md (D-001)
- Related ADRs: None
- Evaluator Evidence: history/prompts/005-execution-engine/PHR-0037-execution-engine-plan-generated.md
