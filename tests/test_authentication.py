"""Offline security regressions; all credentials and pitch rows are synthetic."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from unittest.mock import Mock

import pandas as pd
import pytest
from argon2.exceptions import VerifyMismatchError

import authentication as auth
from auth_helpers import (
    authenticated_app, login, new_app, test_credentials as credentials,
    TEST_PASSWORD, TEST_USERNAME,
)


def accounts():
    return auth.load_accounts(credentials()["credentials"])


def assert_locked(app):
    assert not app.exception
    assert [h.value for h in app.header] == ["Sign in"]
    assert not app.tabs and not app.sidebar.text_input
    assert not app.dataframe and not app.metric and not app.table
    assert not app.get("plotly_chart") and not app.get("download_button")
    assert not any(b.key in {"request_data", "search_players", "generate_report", "logout"} for b in app.button)


def test_direct_access_requires_login_and_cannot_fetch(monkeypatch):
    fetch = Mock(side_effect=AssertionError("Unauthenticated retrieval"))
    search = Mock(side_effect=AssertionError("Unauthenticated search"))
    monkeypatch.setattr("statcast_service.get_pitcher_statcast", fetch)
    monkeypatch.setattr("pitcher_search.fetch_candidates", search)
    app = new_app()
    app.query_params.update({"_pap_identity": TEST_USERNAME, "analysis_section": "Scouting Report"})
    app.session_state["statcast_result"] = "stale data"
    app.session_state["scouting_report"] = "stale report"
    app.run()
    assert_locked(app)
    assert app.text_input(key="login_username").label == "Username"
    assert app.text_input(key="login_password").label == "Password"
    assert app.text_input(key="login_password").proto.type == app.text_input(key="login_password").proto.PASSWORD
    assert "statcast_result" not in app.session_state
    assert "scouting_report" not in app.session_state
    fetch.assert_not_called()
    search.assert_not_called()


@pytest.mark.parametrize("username,password", [
    (TEST_USERNAME, TEST_PASSWORD), ("synthetic-second", "second-test-password"),
])
def test_valid_accounts_and_reruns(username, password):
    app = login(new_app().run(), username, password)
    assert not app.exception
    assert len(app.tabs) == 4
    assert app.sidebar.button(key="logout").label == "Logout"
    assert not app.text_input(key="pitcher_query").value
    assert "login_password" not in app.session_state
    app.run()
    assert len(app.tabs) == 4
    assert not app.exception
    assert not app.query_params


@pytest.mark.parametrize("username,password", [
    ("unknown-test-user", TEST_PASSWORD), (TEST_USERNAME, "incorrect-test-password"),
    (TEST_USERNAME.upper(), TEST_PASSWORD), ("", ""),
])
def test_invalid_credentials_have_identical_generic_errors(username, password):
    app = login(new_app().run(), username, password)
    assert_locked(app)
    assert [e.value for e in app.error] == [auth.FAILURE_MESSAGE]
    if password:
        assert password not in str(app.error)
    assert app.session_state.get("login_password", "") == ""
    assert "_pap_identity" not in app.session_state


@pytest.mark.parametrize("config", [
    None, {}, {"users": {}}, {"users": []}, {"users": {"bad": "plaintext"}},
    {"users": {"bad": {"password_hash": "plaintext", "enabled": True}}},
    {"users": {"bad": {"password_hash": "REPLACE_WITH_GENERATED_ARGON2ID_HASH", "enabled": True}}},
])
def test_invalid_configuration_fails_closed(config):
    app = new_app()
    app.secrets["credentials"] = config
    app.session_state["scouting_report"] = "stale report"
    app.run()
    assert not app.exception and not app.tabs and not app.button
    assert "Sign in is unavailable" in app.error[0].value
    assert "scouting_report" not in app.session_state
    with pytest.raises(auth.AuthenticationConfigError, match="configuration unavailable"):
        auth.load_accounts(config)


def test_missing_secrets_fail_closed():
    app = new_app()
    app.secrets.clear()
    app.run()
    assert not app.exception and not app.tabs and not app.button
    assert "Sign in is unavailable" in app.error[0].value


@pytest.mark.parametrize("mutation", ["disabled", "removed", "replaced", "malformed"])
def test_changed_credentials_revoke_loaded_session(mutation):
    app = authenticated_app()
    config = deepcopy(credentials())
    user = config["credentials"]["users"][TEST_USERNAME]
    if mutation == "disabled":
        user["enabled"] = False
    elif mutation == "removed":
        del config["credentials"]["users"][TEST_USERNAME]
    elif mutation == "replaced":
        user["password_hash"] = auth.PASSWORD_HASHER.hash("replacement-test-password")
    else:
        user["password_hash"] = "broken"
    app.secrets.update(config)
    app.session_state["statcast_result"] = "stale data"
    app.session_state["scouting_report"] = "stale report"
    app.run()
    assert not app.exception and not app.tabs
    assert "_pap_identity" not in app.session_state
    assert "statcast_result" not in app.session_state
    assert "scouting_report" not in app.session_state


def test_logout_clears_loaded_reports_and_requires_fresh_analysis(monkeypatch):
    fetch = Mock(return_value=pd.DataFrame({"pitch_type": ["FF"], "release_speed": [94.]}))
    monkeypatch.setattr("statcast_service.get_pitcher_statcast", fetch)
    app = authenticated_app()
    app.sidebar.radio(key="selection_source").set_value("Manual ID").run()
    app.sidebar.text_input(key="pitcher_id").set_value("123")
    app.sidebar.button(key="request_data").click().run()
    app.button(key="generate_report").click().run()
    assert not app.exception
    assert app.get("download_button") and "scouting_report" in app.session_state
    app.sidebar.button(key="logout").click().run()
    assert_locked(app)
    for key in ["_pap_identity", "statcast_result", "scouting_report", "pitcher_id",
                "analysis_pitch_types", "resolved_player_id", "analysis_section"]:
        assert key not in app.session_state
    app.run()
    assert_locked(app)
    login(app)
    assert not app.exception and len(app.tabs) == 4
    assert not app.dataframe and not app.get("download_button")
    fetch.assert_called_once()


def test_separate_sessions_do_not_share_authentication():
    first = authenticated_app()
    second = new_app().run()
    assert_locked(second)
    first.run()
    assert len(first.tabs) == 4
    login(second, "synthetic-second", "second-test-password")
    first.sidebar.button(key="logout").click().run()
    assert_locked(first)
    second.run()
    assert len(second.tabs) == 4


def test_disabled_account_cannot_login():
    app = new_app()
    config = deepcopy(credentials())
    config["credentials"]["users"][TEST_USERNAME]["enabled"] = False
    app.secrets.update(config)
    login(app.run())
    assert_locked(app)
    assert app.error[0].value == auth.FAILURE_MESSAGE


@pytest.mark.parametrize("change", ["enabled_type", "weak_profile", "argon2i", "bad_base64", "whitespace", "extra"])
def test_config_rejects_insecure_or_ambiguous_accounts(change):
    config = deepcopy(credentials()["credentials"])
    entry = config["users"][TEST_USERNAME]
    if change == "enabled_type":
        entry["enabled"] = "true"
    elif change == "weak_profile":
        entry["password_hash"] = entry["password_hash"].replace("m=65536", "m=8")
    elif change == "argon2i":
        entry["password_hash"] = entry["password_hash"].replace("argon2id", "argon2i")
    elif change == "bad_base64":
        entry["password_hash"] = entry["password_hash"][:-1] + "B"
    elif change == "whitespace":
        config["users"][" whitespace "] = entry
    else:
        entry["password"] = "plaintext-is-rejected"
    with pytest.raises(auth.AuthenticationConfigError):
        auth.load_accounts(config)


@pytest.fixture
def cheap_hasher(monkeypatch):
    """Test counter behavior without repeatedly spending Argon2 work/memory."""
    hasher = Mock()
    hasher.hash.return_value = "dummy-test-hash"
    hasher.verify.side_effect = VerifyMismatchError("synthetic mismatch")
    monkeypatch.setattr(auth, "PASSWORD_HASHER", hasher)
    return hasher


def test_per_username_throttle_and_expiration(cheap_hasher):
    now = [0.]
    limiter = auth.LoginLimiter(clock=lambda: now[0])
    for _ in range(8):
        assert not limiter.authenticate(accounts(), TEST_USERNAME, "wrong")
    assert cheap_hasher.verify.call_count == 5
    # Another session/limiter caller cannot bypass a name's counter.
    now[0] = 299
    assert not limiter.authenticate(accounts(), TEST_USERNAME, TEST_PASSWORD)
    assert cheap_hasher.verify.call_count == 5
    now[0] = 300
    cheap_hasher.verify.side_effect = None
    cheap_hasher.verify.return_value = True
    assert limiter.authenticate(accounts(), TEST_USERNAME, TEST_PASSWORD)
    assert cheap_hasher.verify.call_count == 6


def test_global_throttle_bounds_unknown_username_work(cheap_hasher):
    now = [0.]
    limiter = auth.LoginLimiter(clock=lambda: now[0])
    for i in range(75):
        assert not limiter.authenticate(accounts(), f"unknown-{i}", "wrong")
    assert cheap_hasher.verify.call_count == 50
    now[0] = 60
    assert not limiter.authenticate(accounts(), "new-name", "wrong")
    assert cheap_hasher.verify.call_count == 51


def test_throttle_memory_bound_does_not_evict_active_locks(cheap_hasher):
    now = [0.]
    limiter = auth.LoginLimiter(clock=lambda: now[0])
    # Seed saturation independently of the stricter global work budget.
    limiter._attempts = {str(i): auth._Attempts(5, 300) for i in range(1024)}
    assert not limiter.authenticate(accounts(), "new-name", "wrong")
    cheap_hasher.verify.assert_not_called()
    assert len(limiter._attempts) == 1024
    now[0] = 300
    assert not limiter.authenticate(accounts(), "new-name", "wrong")
    assert len(limiter._attempts) == 1


def test_concurrent_attempts_cannot_bypass_account_limit(cheap_hasher):
    limiter = auth.LoginLimiter()
    configured = accounts()
    with ThreadPoolExecutor(max_workers=12) as pool:
        outcomes = list(pool.map(lambda _: limiter.authenticate(configured, TEST_USERNAME, "wrong"), range(24)))
    assert not any(outcomes)
    assert cheap_hasher.verify.call_count == 5


def test_success_resets_username_failures(cheap_hasher):
    limiter = auth.LoginLimiter()
    configured = accounts()
    for _ in range(4):
        assert not limiter.authenticate(configured, TEST_USERNAME, "wrong")
    cheap_hasher.verify.side_effect = None
    cheap_hasher.verify.return_value = True
    assert limiter.authenticate(configured, TEST_USERNAME, TEST_PASSWORD)
    cheap_hasher.verify.side_effect = VerifyMismatchError("synthetic mismatch")
    for _ in range(5):
        assert not limiter.authenticate(configured, TEST_USERNAME, "wrong")
    assert cheap_hasher.verify.call_count == 10


def test_ui_throttle_survives_new_sessions_and_uses_same_error():
    for _ in range(5):
        app = login(new_app().run(), TEST_USERNAME, "wrong")
        assert_locked(app)
        assert app.error[0].value == auth.FAILURE_MESSAGE
    app = login(new_app().run())  # Correct credentials are temporarily blocked too.
    assert_locked(app)
    assert app.error[0].value == auth.FAILURE_MESSAGE


def test_oversized_input_is_rejected_server_side(cheap_hasher):
    limiter = auth.LoginLimiter()
    assert not limiter.authenticate(accounts(), "x" * 129, TEST_PASSWORD)
    assert not limiter.authenticate(accounts(), TEST_USERNAME, "é" * 513)
    cheap_hasher.verify.assert_not_called()
