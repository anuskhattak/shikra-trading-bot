import pytest
import numpy as np
import pandas as pd
from datetime import datetime, timedelta


@pytest.fixture
def make_ohlcv():
    """Factory fixture shared by all engine unit tests.

    Returns a callable: make_ohlcv(n, seed=42) -> pd.DataFrame
    with columns [time, open, high, low, close, tick_volume] and
    valid OHLCV invariants (high >= open/close >= low).
    Prices are realistic XAUUSD levels (~1900 USD).
    """
    def _factory(n: int, seed: int = 42) -> pd.DataFrame:
        rng = np.random.default_rng(seed)
        base_price = 1900.0

        # Simulate price walk: each close is the previous close ± small move
        moves = rng.normal(0, 0.5, n)          # ~$0.50 per candle noise
        closes = np.cumsum(moves) + base_price

        # Open = previous close (gap-free for simplicity)
        opens = np.empty(n)
        opens[0] = base_price
        opens[1:] = closes[:-1]

        body_high = np.maximum(opens, closes)
        body_low = np.minimum(opens, closes)

        # Wicks extend up to 1.5× the body size beyond each side
        body_size = np.abs(closes - opens) + 0.10   # floor prevents zero-width
        highs = body_high + rng.uniform(0.0, body_size * 1.5, n)
        lows = body_low - rng.uniform(0.0, body_size * 1.5, n)

        times = [datetime(2024, 1, 1) + timedelta(hours=i) for i in range(n)]

        return pd.DataFrame({
            "time": times,
            "open": np.round(opens, 5),
            "high": np.round(highs, 5),
            "low": np.round(lows, 5),
            "close": np.round(closes, 5),
            "tick_volume": rng.integers(100, 1000, n).astype(int),
        })

    return _factory
