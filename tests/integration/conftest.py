"""
Integration conftest — replaces the session-wide MT5 mock with the real library.

Unit tests (tests/unit/) use a MagicMock for MT5 injected by the root conftest.
Integration tests need the actual MetaTrader5 terminal, so this conftest:
  1. Removes the mock from sys.modules before any integration test runs.
  2. Clears cached broker module imports that were compiled against the mock.
  3. Allows broker modules to re-import with the real MT5 library.

Run integration tests separately from unit tests:
    pytest tests/integration/ -v
"""
import sys

import pytest
from dotenv import load_dotenv

load_dotenv()


@pytest.fixture(scope="session", autouse=True)
def _use_real_mt5():
    """Swap mock MT5 for the real library before integration tests execute."""
    sys.modules.pop("MetaTrader5", None)

    # Clear any broker modules already compiled against the mock
    for key in list(sys.modules.keys()):
        if key.startswith("src.broker") or key == "src.broker":
            sys.modules.pop(key, None)

    yield
