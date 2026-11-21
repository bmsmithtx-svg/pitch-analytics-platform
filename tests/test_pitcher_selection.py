"""Offline Streamlit identity transitions through the unchanged retrieval path."""
from datetime import date
from unittest.mock import Mock

import pandas as pd
import pytest
from auth_helpers import authenticated_app

from pitcher_search import PitcherSearchError, parse_candidates
from statcast_validation import NoStatcastDataError


@pytest.fixture
def dashboard(monkeypatch):
    import streamlit as st
    st.cache_data.clear()
    lookup = Mock(return_value=parse_candidates({"people": [{"id": 123, "fullName": "Example Pitcher"}]}))
    fetch = Mock(return_value=pd.DataFrame({"pitch_type": ["FF"]}))
    monkeypatch.setattr("pitcher_search.fetch_candidates", lookup)
    monkeypatch.setattr("statcast_service.get_pitcher_statcast", fetch)
    app = authenticated_app()
    assert not app.exception
    yield app, lookup, fetch
    st.cache_data.clear()


def search(app, name="Example Pitcher"):
    app.text_input(key="pitcher_query").set_value(name)
    app.button(key="search_players").click().run()
    assert not app.exception


def request(app):
    app.button(key="request_data").click().run()
    assert not app.exception


def test_name_resolution_explicit_retrieval_and_rerun(dashboard):
    app, lookup, fetch = dashboard
    lookup.assert_not_called()
    fetch.assert_not_called()
    search(app, "  EXample   Pitcher ")
    assert app.session_state["resolved_player_id"] == 123
    assert app.session_state["search_results_query"] == "EXample Pitcher"
    assert app.session_state["selected_candidate"].player_id == 123
    fetch.assert_not_called()
    app.run()
    assert lookup.call_count == 1
    request(app)
    fetch.assert_called_once_with("123", date.today() - pd.Timedelta(days=29), date.today())
    assert app.metric and not app.get("download_button")
    app.button(key="generate_report").click().run()
    assert app.get("download_button")
    app.run()
    assert lookup.call_count == fetch.call_count == 1


@pytest.mark.parametrize("names,query", [(["Example Pitcher", "Example Pitcher"], "Example Pitcher"),
    (["Example Pitcher", "Example Other"], "Example"), (["Example Pitcher"], "Example")])
def test_explicit_selection_for_ambiguous_or_partial(dashboard, names, query):
    app, lookup, fetch = dashboard
    lookup.return_value = parse_candidates({"people": [
        {"id": 123 + i, "fullName": name} for i, name in enumerate(names)]})
    search(app, query)
    assert app.session_state["resolved_player_id"] is None
    assert app.selectbox(key="candidate_id").value is None
    request(app)
    fetch.assert_not_called()
    app.selectbox(key="candidate_id").select(123).run()
    assert not app.exception
    fetch.assert_not_called()
    request(app)
    assert fetch.call_args.args[0] == "123"


def test_query_edit_clears_selection_results_and_report(dashboard):
    app, lookup, fetch = dashboard
    search(app)
    request(app)
    app.text_input(key="pitcher_query").set_value("Other Example").run()
    assert not app.exception
    assert app.session_state["resolved_player_id"] is None
    assert "search_candidates" not in app.session_state
    assert not app.get("download_button") and not app.metric
    request(app)
    assert fetch.call_count == 1
    assert lookup.call_count == 1
    lookup.return_value = parse_candidates({"people": [{"id": 456, "fullName": "Other Example"}]})
    search(app, "Other Example")
    assert app.session_state["resolved_player_id"] == 456
    assert not app.metric
    request(app)
    assert fetch.call_args.args[0] == "456"


def test_switch_modes_and_manual_identity_changes(dashboard):
    app, lookup, fetch = dashboard
    search(app)
    request(app)
    app.radio(key="selection_source").set_value("Manual ID").run()
    assert app.session_state["resolved_player_id"] is None
    assert not app.get("download_button")
    request(app)
    assert fetch.call_count == 1
    app.text_input(key="pitcher_id").set_value("456").run()
    assert app.session_state["resolved_player_id"] == 456
    request(app)
    assert fetch.call_args.args[0] == "456"
    app.text_input(key="pitcher_id").set_value("789").run()
    assert not app.metric and not app.get("download_button")
    request(app)
    assert fetch.call_args.args[0] == "789"
    app.radio(key="selection_source").set_value("Name search").run()
    assert app.session_state["resolved_player_id"] is None
    assert not app.metric
    request(app)
    assert fetch.call_count == 3


def test_failed_lookup_retry_and_manual_fallback(dashboard):
    app, lookup, fetch = dashboard
    search(app)
    request(app)
    lookup.side_effect = PitcherSearchError("Search unavailable; retry or enter an ID manually.")
    search(app, "Other Example")
    assert app.error and not app.metric and not app.get("download_button")
    assert app.session_state["resolved_player_id"] is None
    search(app, "Other Example")
    assert lookup.call_count == 3
    app.radio(key="selection_source").set_value("Manual ID").run()
    app.text_input(key="pitcher_id").set_value("456")
    request(app)
    assert fetch.call_args.args[0] == "456"


@pytest.mark.parametrize("query", ["", " ", "A", "Ab\nCd", "A" * 101])
def test_invalid_query_no_lookup(dashboard, query):
    app, lookup, fetch = dashboard
    search(app, query)
    assert app.error
    lookup.assert_not_called()
    request(app)
    fetch.assert_not_called()


def test_empty_results_and_no_statcast_data(dashboard):
    app, lookup, fetch = dashboard
    lookup.return_value = ()
    search(app)
    assert any("No matching players" in i.value for i in app.info)
    request(app)
    fetch.assert_not_called()
    lookup.return_value = parse_candidates({"people": [{"id": 456, "fullName": "Other Example"}]})
    search(app, "Other Example")
    fetch.side_effect = NoStatcastDataError("No Statcast records found for this pitcher and date range.")
    request(app)
    assert any("No Statcast records" in i.value for i in app.info)
    assert not app.metric and not app.get("download_button")


@pytest.mark.parametrize("value", ["", "0", "-1", "1.5", "True", "12345678901"])
def test_invalid_manual_id_never_calls_retrieval(dashboard, value):
    app, lookup, fetch = dashboard
    app.radio(key="selection_source").set_value("Manual ID").run()
    app.text_input(key="pitcher_id").set_value(value)
    request(app)
    assert app.error and app.session_state["resolved_player_id"] is None
    fetch.assert_not_called()


def test_changing_or_clearing_candidate_drops_old_report(dashboard):
    app, lookup, fetch = dashboard
    lookup.return_value = parse_candidates({"people": [
        {"id": 123, "fullName": "Example Pitcher"},
        {"id": 456, "fullName": "Example Pitcher"}]})
    search(app)
    app.selectbox(key="candidate_id").select(123).run()
    request(app)
    app.button(key="generate_report").click().run()
    assert app.get("download_button")
    app.selectbox(key="candidate_id").select(456).run()
    assert app.session_state["resolved_player_id"] == 456
    assert not app.get("download_button") and not app.metric
    assert fetch.call_count == 1
    request(app)
    assert fetch.call_args.args[0] == "456"
    app.selectbox(key="candidate_id").set_value(None).run()
    assert app.session_state["resolved_player_id"] is None
    assert not app.get("download_button") and not app.metric
    request(app)
    assert fetch.call_count == 2
