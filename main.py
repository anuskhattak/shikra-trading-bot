"""Shikra Trading Bot — live XAUUSD entry point (spec009 T012).

Usage:
    python main.py

Credentials are loaded from environment variables (set via .env or system env):
    MT5_ACCOUNT   — broker account number (int)
    MT5_PASSWORD  — broker account password
    MT5_SERVER    — broker server name (e.g. "MetaQuotes-Demo")

Config is loaded from config.yaml in the working directory.
Kill switch: write logs/kill_switch.json to halt new entries without stopping the bot.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv
from loguru import logger

from src.analysis.atr_service import ATRService
from src.broker.connection import BrokerConnection
from src.broker.order_manager import OrderManager
from src.execution.execution_engine import ExecutionEngine
from src.orchestrator.strategy_orchestrator import StrategyOrchestrator

load_dotenv()

_CONFIG_PATH = Path("config.yaml")
_KILL_SWITCH_PATH = Path("logs/kill_switch.json")


def _load_config() -> dict:
    if not _CONFIG_PATH.exists():
        logger.critical(f"config.yaml not found at {_CONFIG_PATH.resolve()}")
        sys.exit(1)
    with _CONFIG_PATH.open() as f:
        return yaml.safe_load(f)


def main() -> None:
    config = _load_config()

    account  = int(os.getenv("MT5_ACCOUNT", "0"))
    password = os.getenv("MT5_PASSWORD", "")
    server   = os.getenv("MT5_SERVER", "")

    if not account or not password or not server:
        logger.critical(
            "MT5 credentials missing — set MT5_ACCOUNT, MT5_PASSWORD, MT5_SERVER "
            "in .env or environment variables"
        )
        sys.exit(1)

    magic = config.get("execution", {}).get("magic_number", 202605)
    kill_switch_path = Path(
        config.get("execution", {}).get("kill_switch_path", str(_KILL_SWITCH_PATH))
    )

    broker        = BrokerConnection(account, password, server)
    order_manager = OrderManager(magic_number=magic)
    atr_service   = ATRService(config)
    exec_engine   = ExecutionEngine(order_manager, config, kill_switch_path=kill_switch_path)
    orchestrator  = StrategyOrchestrator(
        broker, order_manager, atr_service, exec_engine, config,
        kill_switch_path=kill_switch_path,
    )

    try:
        orchestrator.run()
    except KeyboardInterrupt:
        logger.info("Shikra stopped by user")
    except SystemExit as exc:
        logger.critical(f"Shikra halted: {exc}")
        sys.exit(int(str(exc)) if str(exc).isdigit() else 1)


if __name__ == "__main__":
    main()
