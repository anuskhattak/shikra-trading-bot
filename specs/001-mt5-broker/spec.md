# Feature Specification: MT5 Broker Connection

**Feature Branch**: `001-mt5-broker`
**Created**: 2026-05-11
**Status**: Draft
**Input**: MT5 broker connection — connect to MetaTrader 5, authenticate, fetch XAUUSD market data, and place orders

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 — Broker Connection & Authentication (Priority: P1)

When the trader starts the system, Shikra automatically connects to the MT5 terminal and authenticates with the broker account. If the connection fails, a clear error message is shown and the system does not proceed to trading.

**Why this priority**: This is the foundation of the entire trading system. No other feature can function without an established connection.

**Independent Test**: Start the system — if "Connected: XAUUSD ready" status appears, P1 passes. Start with invalid credentials — system must show "Authentication Failed" error and shut down without trading.

**Acceptance Scenarios**:

1. **Given** valid credentials and MT5 terminal is running, **When** the system starts, **Then** connection is established within 10 seconds and account details are confirmed
2. **Given** incorrect password, **When** the system attempts to connect, **Then** system logs "Authentication Failed" and does not place any trades
3. **Given** MT5 terminal is not running, **When** the system attempts to connect, **Then** system returns "Terminal Unavailable" error and does not retry

---

### User Story 2 — XAUUSD Market Data Fetch (Priority: P2)

After a successful connection, the system automatically fetches the current XAUUSD price and historical OHLCV data for all three timeframes (D1, H4, H1). This data is delivered to the SMC signal engine for analysis.

**Why this priority**: The signal engine cannot operate without market data. This must be available immediately after connection.

**Independent Test**: After connection, verify current bid/ask price and bars for all three timeframes — all data must be present with no missing timeframes.

**Acceptance Scenarios**:

1. **Given** an active connection, **When** market data is requested, **Then** current XAUUSD bid price, ask price, and spread are returned within 2 seconds
2. **Given** an active connection, **When** historical data is requested, **Then** a minimum of 200 bars for D1, H4, and H1 timeframes are returned with no gaps
3. **Given** the market is closed (weekend), **When** data is requested, **Then** system returns "Market Closed" status and halts signal generation

---

### User Story 3 — Order Placement (Priority: P3)

When an SMC signal is generated, the system places a buy or sell order on XAUUSD via MT5 — with mandatory stop loss and take profit. A complete log entry is recorded before and after every order attempt.

**Why this priority**: This is the final step of actual trading execution. It is only meaningful after P1 and P2 are complete.

**Independent Test**: Place a buy order in paper trading mode with valid SL and TP — the order must be confirmed and a log entry must appear in `logs/trades.json`.

**Acceptance Scenarios**:

1. **Given** an active connection and a valid signal, **When** a buy order with SL and TP is submitted, **Then** broker confirmation is received within 5 seconds
2. **Given** any order attempt, **When** any result occurs (success or failure), **Then** entry price, stop loss, take profit, volume, and result are recorded in `logs/trades.json`
3. **Given** stop loss or take profit is missing, **When** an order submission is attempted, **Then** system rejects the order and logs "Missing SL/TP — Order Rejected" error
4. **Given** insufficient account margin, **When** an order is submitted, **Then** system logs "Insufficient Margin" and does not place the trade

---

### User Story 4 — Connection Health Monitoring & Recovery (Priority: P4)

The system continuously monitors connection health. If the connection drops, the system automatically attempts to reconnect without requiring manual intervention from the trader.

**Why this priority**: Connection drops are common in live trading. Without auto-recovery, open positions can become unmanaged and expose the account to uncontrolled risk.

**Independent Test**: Manually disconnect the network — system must reconnect within 30 seconds and a "Reconnected" log entry must appear.

**Acceptance Scenarios**:

1. **Given** an active trading session, **When** the connection drops, **Then** system immediately halts trading and begins reconnection attempts
2. **Given** a connection loss, **When** a reconnection attempt is made, **Then** system reconnects within 30 seconds
3. **Given** 3 consecutive reconnection failures, **When** all attempts are exhausted, **Then** system enters emergency stop mode and logs a critical alert

---

### Edge Cases

| Scenario | Expected System Behavior |
|---|---|
| MT5 terminal is running but broker server is unreachable | Log "Broker Server Unreachable", halt trading, begin reconnection cycle |
| Partial market data returned — some bars missing | Log "Incomplete Data Warning", discard partial dataset, retry fetch once; halt signal generation if retry fails |
| Network drops while an order is in-flight | Log "Order Status Unknown", flag order for manual review, halt further order placement until connection restored |
| System started during weekend when market is closed | Log "Market Closed — Weekend", enter standby mode, resume automatically on market open |
| Spread exceeds maximum allowed threshold (config: `max_spread_points`) | Log "High Spread — Trade Skipped", skip trade, re-evaluate on next signal |
| Account margin level is critically low | Log "Low Margin Warning", halt all new order placement, alert operator |
| XAUUSD symbol temporarily unavailable on broker | Log "Symbol Unavailable", halt signal generation, retry symbol check every 60 seconds |

---

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST establish a connection to the broker terminal using credentials from secure configuration
- **FR-002**: System MUST authenticate using account number, password, and broker server name
- **FR-003**: System MUST verify and confirm successful authentication before performing any market data or order operations
- **FR-004**: System MUST fetch current XAUUSD bid price, ask price, and spread on demand
- **FR-005**: System MUST fetch historical OHLCV bar data for D1, H4, and H1 timeframes — minimum 200 bars each
- **FR-006**: System MUST place market orders with both stop loss AND take profit — both fields are mandatory
- **FR-007**: System MUST reject any order where stop loss OR take profit is absent or set to an invalid value
- **FR-008**: System MUST log every connection event (connect, disconnect, reconnect attempt, failure) with a timestamp
- **FR-009**: System MUST log every order attempt including: entry price, stop loss, take profit, volume, and final result
- **FR-010**: System MUST detect a connection loss within 10 seconds of it occurring
- **FR-011**: System MUST attempt automatic reconnection after any connection loss
- **FR-012**: System MUST halt all trading activity during connection loss and reconnection
- **FR-013**: System MUST disconnect cleanly on shutdown — no orphaned connections left open
- **FR-014**: System MUST expose current connection status at all times (Connected / Disconnected / Reconnecting)
- **FR-015**: System MUST skip order placement when spread exceeds the configured maximum threshold
- **FR-016**: System MUST halt order placement when account margin falls below a safe operating level

### Non-Functional Requirements

- **NFR-001**: Broker credentials (account number, password) MUST never appear in any log file, console output, or error message — masked at all times
- **NFR-002**: System MUST achieve connection uptime ≥ 99% during active trading sessions (Asia, London, New York)
- **NFR-003**: All connection and order operations MUST be non-blocking — system responsiveness must not degrade during data fetch or order submission
- **NFR-004**: System MUST operate correctly on Windows 10+ with MT5 terminal installed on the same machine
- **NFR-005**: Log entries MUST be written atomically — no partial or corrupted entries in `logs/trades.json` or event logs

### Key Entities

- **BrokerConnection**: Connection status, broker server, account number, connection timestamp, last health check time
- **MarketData**: Symbol (XAUUSD), timeframe, OHLCV bar collection, current bid/ask/spread, data freshness timestamp
- **TradeOrder**: Order type (buy/sell), entry price, stop loss, take profit, volume, magic number, submission timestamp, broker confirmation status
- **ConnectionEvent**: Event type (connected / disconnected / reconnected / failed), timestamp, error message if applicable

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Broker connection established and authenticated within 10 seconds of system start
- **SC-002**: Current XAUUSD price data (bid/ask/spread) available within 2 seconds of connection
- **SC-003**: Historical bar data for all 3 timeframes (D1, H4, H1) fetched with zero missing bars across a 200-bar lookback
- **SC-004**: Market orders acknowledged by broker within 5 seconds of submission
- **SC-005**: System automatically recovers from connection loss within 30 seconds without manual intervention
- **SC-006**: 100% of connection events and order attempts are logged with timestamps — zero silent failures
- **SC-007**: Zero orders placed without a valid stop loss AND take profit — system enforces this with 100% reliability
- **SC-008**: System correctly enters emergency stop after 3 consecutive failed reconnection attempts
- **SC-009**: Broker credentials are absent from all log files — verified across 100% of log output
- **SC-010**: System correctly skips trades when spread exceeds configured maximum — zero exceptions

---

## Assumptions

- MT5 terminal is installed and running on the same machine as Shikra
- Broker credentials (account number, password, server) are stored in `.env` — never hardcoded
- Only XAUUSD is traded — no other symbols are in scope for this feature
- Magic number `202605` (from `config.yaml`) is used to identify Shikra's orders on the broker side
- Paper trading and live trading use the same connection interface — only the account type differs

**Threshold Justifications**:
- **10 seconds** (connection timeout): Based on standard MT5 terminal initialization time on Windows 10 under normal network conditions
- **2 seconds** (market data): Reflects acceptable latency for real-time price feeds; longer delays indicate a degraded connection
- **5 seconds** (order acknowledgment): Standard broker round-trip time for market orders under normal server load; aligns with MT5 execution benchmarks
- **200 bars** (historical data): Minimum lookback required for D1 structure analysis in SMC methodology — covers approximately 40 weeks of daily data
- **30 seconds** (reconnection): Balances recovery speed with avoiding broker-side rate limiting on repeated connection attempts
- **3 attempts** (emergency stop): Industry-standard retry count before escalating to a human-intervention state

## Out of Scope

- Pending order types (limit orders, stop orders) — market orders only in this feature
- Multiple symbol support — XAUUSD only
- Order modification or partial close — separate feature
- Position tracking and P&L calculation — separate feature (Risk Management)
- Any signal generation logic — handled by SMC Engine feature
