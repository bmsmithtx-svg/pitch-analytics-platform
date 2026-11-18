"""Offline navigation and request-provenance regression coverage.

All identities and pitch rows are synthetic UI fixtures, not player statistics.
"""
from datetime import date
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

from pitcher_search import parse_candidates
from statcast_validation import NoStatcastDataError, StatcastError

SECTIONS = ["Pitcher Selection & Analysis", "Pitch Arsenal", "Visualizations", "Scouting Report"]


@pytest.fixture
def dashboard(monkeypatch):
    st.cache_data.clear()
    candidates = parse_candidates({"people": [{"id": 123, "fullName": "Example Pitcher"}]})
    lookup = Mock(return_value=candidates)
    rows = pd.DataFrame({"pitch_type": ["FF", "SL"], "release_speed": [95., 85.],
                         "pfx_x": [-1., 0.5], "pfx_z": [1., -0.25]})
    fetch = Mock(return_value=rows)
    monkeypatch.setattr("pitcher_search.fetch_candidates", lookup)
    monkeypatch.setattr("statcast_service.get_pitcher_statcast", fetch)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run(timeout=10)
    assert not app.exception
    yield app, lookup, fetch
    st.cache_data.clear()


def select_and_generate(app):
    app.text_input(key="pitcher_query").set_value("Example Pitcher")
    app.button(key="search_players").click().run()
    assert not app.exception
    app.button(key="request_data").click().run()
    assert not app.exception


def navigate(app, section):
    # AppTest exposes tab panels as read-only containers. Seed the tracked
    # tabs key to exercise the same rerun state as the real agent API.
    app.session_state["analysis_section"] = section
    app.run()
    assert not app.exception
    assert app.session_state["analysis_section"] == section


@pytest.mark.parametrize("section", SECTIONS)
def test_empty_sections_do_not_retrieve(dashboard, section):
    app, lookup, fetch = dashboard
    navigate(app, section)
    assert [tab.label for tab in app.tabs] == SECTIONS
    assert not app.metric and not app.get("download_button")
    assert any("Select a pitcher" in info.value for info in app.info)
    lookup.assert_not_called()
    fetch.assert_not_called()


@pytest.mark.parametrize("section", SECTIONS)
def test_selection_results_filter_and_report_survive_navigation(dashboard, section):
    app, lookup, fetch = dashboard
    select_and_generate(app)
    timestamp = app.session_state["report_generated_at"]
    loaded = app.session_state["statcast_result"]
    report_table = app.table[0].value.copy(deep=True)
    app.multiselect(key="analysis_pitch_types").set_value(["SL"]).run()
    navigate(app, section)
    assert app.session_state["selected_candidate"].player_id == 123
    assert app.session_state["resolved_player_id"] == 123
    assert app.text_input(key="pitcher_query").value == "Example Pitcher"
    assert app.multiselect(key="analysis_pitch_types").value == ["SL"]
    assert app.session_state["statcast_result"][:3] == loaded[:3]
    pd.testing.assert_frame_equal(app.session_state["statcast_result"][3], loaded[3])
    pd.testing.assert_frame_equal(app.table[0].value, report_table)
    assert app.session_state["report_generated_at"] == timestamp
    assert app.get("download_button")
    assert any("Active pitcher: Example Pitcher" in text.value for text in app.text)
    app.run()
    assert app.session_state["analysis_section"] == section
    assert lookup.call_count == fetch.call_count == 1


@pytest.mark.parametrize("key", ["analysis_start", "analysis_end"])
def test_date_edits_clear_all_results_before_submission(dashboard, key):
    app, _, fetch = dashboard
    select_and_generate(app)
    previous = app.date_input(key=key).value
    app.date_input(key=key).set_value(previous - pd.Timedelta(days=1)).run()
    assert not app.exception
    assert app.session_state["resolved_player_id"] == 123
    for state_key in ["statcast_result", "report_generated_at", "analysis_pitch_types"]:
        assert state_key not in app.session_state
    assert not app.metric and not app.table and not app.get("download_button")
    for section in SECTIONS:
        navigate(app, section)
        assert not app.dataframe and not app.get("plotly_chart")
    assert fetch.call_count == 1


@pytest.mark.parametrize("start,end", [(date(2025, 4, 1), date(2025, 5, 1)),
                                      (date(2025, 4, 3), date(2025, 4, 1))])
def test_invalid_dates_never_fetch_or_retain_results(dashboard, start, end):
    app, _, fetch = dashboard
    select_and_generate(app)
    app.date_input(key="analysis_start").set_value(start)
    app.date_input(key="analysis_end").set_value(end)
    app.button(key="request_data").click().run()
    assert not app.exception
    assert app.error and not app.metric and not app.table
    assert "statcast_result" not in app.session_state
    assert fetch.call_count == 1


@pytest.mark.parametrize("error", [NoStatcastDataError("No records found; try another date range."),
                                   StatcastError("Unable to retrieve data; retry.")])
def test_failed_requests_stay_empty_through_navigation_and_can_retry(dashboard, error):
    app, _, fetch = dashboard
    select_and_generate(app)
    fetch.side_effect = error
    app.button(key="request_data").click().run()
    for section in SECTIONS:
        navigate(app, section)
        assert not app.metric and not app.dataframe and not app.table
        assert not app.get("download_button")
        assert "report_generated_at" not in app.session_state
        assert any(str(error) == alert.value for alert in [*app.info, *app.error])
    assert fetch.call_count == 2
    fetch.side_effect = None
    app.button(key="request_data").click().run()
    assert not app.exception
    assert app.success and app.get("download_button")
    assert fetch.call_count == 3


def test_expired_candidate_clears_analysis_and_requires_new_choice(dashboard):
    app, lookup, fetch = dashboard
    lookup.return_value = parse_candidates({"people": [
        {"id": 123, "fullName": "Example Pitcher"},
        {"id": 456, "fullName": "Example Pitcher"},
        {"id": 789, "fullName": "Example Pitcher"},
    ]})
    app.text_input(key="pitcher_query").set_value("Example Pitcher")
    app.button(key="search_players").click().run()
    app.selectbox(key="candidate_id").select(123).run()
    app.button(key="request_data").click().run()
    # Simulate restored selection metadata that no longer contains this ID.
    app.session_state["search_candidates"] = lookup.return_value[1:]
    app.run()
    assert not app.exception
    assert app.warning and app.session_state["resolved_player_id"] is None
    assert app.selectbox(key="candidate_id").value is None
    assert not app.metric and not app.get("download_button")
    assert fetch.call_count == 1


@pytest.mark.parametrize("loaded_id", ["456", "invalid"])
def test_provenance_guard_clears_restored_mismatched_results(dashboard, loaded_id):
    app, _, fetch = dashboard
    select_and_generate(app)
    pitcher, start, end, data = app.session_state["statcast_result"]
    app.session_state["statcast_result"] = (loaded_id, start, end, data)
    app.run()
    assert not app.exception
    assert "statcast_result" not in app.session_state
    assert "report_generated_at" not in app.session_state
    assert not app.metric and not app.get("download_button")
    assert fetch.call_count == 1
