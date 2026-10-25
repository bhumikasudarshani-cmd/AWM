"""Guards: a test run must never depend on a developer's .env or touch the real internet."""
import asyncio

import httpx
import pytest

from app.config import settings
from app.pipeline.stages import default_stages


def test_settings_are_neutral_even_if_the_environment_has_real_values():
    assert settings.llm_base_url == "" and settings.llm_model == "" and settings.llm_api_key == ""
    assert settings.dump_fixtures is False


def test_default_stages_never_include_the_paid_model_during_tests():
    assert [s.name for s in default_stages()] == ["rules"]


def test_a_real_network_call_in_a_test_fails_loudly():
    async def go():
        async with httpx.AsyncClient() as client:
            await client.get("https://example.com")

    with pytest.raises(RuntimeError, match="real network call"):
        asyncio.run(go())
