"""SMC Signal Detection Engine — public API.

Single import point for downstream modules (risk manager, order executor).
All callers should import generate_signal from here, not from smc_engine directly.
"""

from src.engine.models import Bias, Direction, EntrySignal
from src.engine.smc_engine import generate_signal

__all__ = ["generate_signal", "EntrySignal", "Bias", "Direction"]
