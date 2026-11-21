"""Keep every automated test independent of external HTTP services."""

import pytest
import requests


@pytest.fixture(autouse=True)
def block_external_http(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail accidental requests HTTP calls, including live pybaseball downloads.

    Retrieval tests mock the pitcher API; dashboard tests render locally through
    AppTest. Neither needs HTTP. Patch the shared requests entry point as a guard
    for both test modules, including future tests that forget to mock retrieval.
    """
    def reject_request(*args: object, **kwargs: object) -> None:
        raise AssertionError("HTTP access is disabled in automated tests; mock retrieval.")

    monkeypatch.setattr(requests.sessions.Session, "request", reject_request)


@pytest.fixture(autouse=True)
def isolated_login_limiter(monkeypatch):
    """Keep process-local throttling deterministic between unrelated test cases."""
    from authentication import LoginLimiter
    monkeypatch.setattr("authentication_ui.LOGIN_LIMITER", LoginLimiter())
