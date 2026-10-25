"""Applied to every test: results must not depend on .env, and nothing may reach the real internet."""
import httpx
import pytest

from app.config import settings


@pytest.fixture(autouse=True)
def hermetic(monkeypatch):
    # A developer's .env (model key, fixture dumping) must never change what a test does or costs.
    for name, neutral in {"llm_base_url": "", "llm_model": "", "llm_api_key": "", "dump_fixtures": False}.items():
        monkeypatch.setattr(settings, name, neutral)

    async def no_network(self, request):
        raise RuntimeError(f"real network call attempted in a test: {request.url.host}")

    # httpx.MockTransport is unaffected; only a real network transport is blocked.
    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", no_network)
