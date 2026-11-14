import sys
from pathlib import Path

# Make the project root importable no matter where pytest is started from or whether pytest.ini is present.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest

from app import storage


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("ANTHROPIC_API_KEY", "DDB_TABLE", "AUTH_DISABLED"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("APP_API_KEY", "test-key")
    storage.reset_store()
    yield
    storage.reset_store()
