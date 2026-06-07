"""Shared pytest fixtures.

The Settings model requires several env vars to instantiate. Tests
that don't actually exercise those values get a fixture-built Settings
with safe placeholders so they don't depend on the user's real .env.
"""

from unittest.mock import patch

import pytest

from serenity.config import Settings


@pytest.fixture
def settings() -> Settings:
    """A Settings instance with safe placeholder values for required fields.

    Bypasses .env loading entirely. Tests that need to flex a particular
    field can build their own Settings instance via Settings.model_copy().
    """
    with patch.dict(
        "os.environ",
        {
            "OPENROUTER_API_KEY": "test-openrouter-key",
            "TRACKED_X_ACCOUNT": "https://x.com/test",
            "X_BEARER_TOKEN": "test-bearer",
        },
        clear=False,
    ):
        return Settings(_env_file=None)
