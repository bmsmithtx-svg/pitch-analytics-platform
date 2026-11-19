"""Offline report workflow fixtures are synthetic, never actual player records."""
from dataclasses import replace
from datetime import date
from unittest.mock import Mock

import pandas as pd
import pytest

from test_navigation import dashboard, navigate, SECTIONS
from scouting_report import build_scouting_report
from report_export import report_filename


def load_analysis(app):
    app.text_input(key="pitcher_query").set_value("Example Pitcher")
    app.button(key="search_players").click().run()
    app.button(key="request_data").click().run()
    assert not app.exception


def test_explicit_generation_preview_export_and_no_rebuild(dashboard, monkeypatch):
    app, _, fetch = dashboard
    builder = Mock(wraps=build_scouting_report)
    monkeypatch.setattr("scouting_report.build_scouting_report", builder)
    load_analysis(app)
    assert not app.table and not app.get("download_button")
    builder.assert_not_called()
    app.button(key="generate_report").click().run()
    assert not app.exception
    report, timestamp, html = app.session_state["scouting_report"]
    assert report.pitcher_id == 123
    assert report.start_date == app.date_input(key="analysis_start").value
    assert report.end_date == app.date_input(key="analysis_end").value
    assert "Report preview" in [h.value for h in app.subheader]
    assert app.table and app.get("download_button")
    assert str(report.start_date) in html and "MLBAM 123" in html
    for section in SECTIONS:
        navigate(app, section)
        assert app.session_state["scouting_report"][1:] == (timestamp, html)
    builder.assert_called_once()
    fetch.assert_called_once()


@pytest.mark.parametrize("stage", ["scouting_report.build_scouting_report", "report_export.export_report_html"])
def test_generation_and_export_fail_closed_and_retry(dashboard, monkeypatch, stage):
    app, _, fetch = dashboard
    load_analysis(app)
    with monkeypatch.context() as patch:
        patch.setattr(stage, Mock(side_effect=ValueError("private source details")))
        app.button(key="generate_report").click().run()
        assert not app.exception
        assert app.error and "private source details" not in app.error[0].value
        assert not app.table and not app.get("download_button")
        assert "scouting_report" not in app.session_state
        navigate(app, "Scouting Report")
        assert app.error and not app.get("download_button")
    app.button(key="generate_report").click().run()
    assert not app.exception
    assert app.table and app.get("download_button") and not app.error
    fetch.assert_called_once()


@pytest.mark.parametrize("rows", [pd.DataFrame(), pd.DataFrame({"pitch_type": [None]})])
def test_empty_and_insufficient_data(dashboard, rows):
    app, _, fetch = dashboard
    fetch.return_value = rows
    load_analysis(app)
    if rows.empty:
        assert "statcast_result" not in app.session_state
        assert not app.get("download_button")
        assert any("No records" in i.value for i in app.info)
    else:
        app.button(key="generate_report").click().run()
        assert not app.exception
        report, _, html = app.session_state["scouting_report"]
        assert report.arsenal.empty
        assert "No classified pitches" in html
        assert app.get("download_button")


@pytest.mark.parametrize("field,value", [("pitcher_id", 456), ("start_date", date(2025, 1, 1))])
def test_mismatched_report_cannot_be_previewed_or_exported(dashboard, field, value):
    app, _, _ = dashboard
    load_analysis(app)
    app.button(key="generate_report").click().run()
    report, timestamp, html = app.session_state["scouting_report"]
    app.session_state["scouting_report"] = (replace(report, **{field: value}), timestamp, html)
    app.run()
    assert not app.exception
    assert not app.table and not app.get("download_button")
    assert "scouting_report" not in app.session_state


@pytest.mark.parametrize("name,slug", [("Example Pitcher", "example-pitcher-123"),
                                      ("../../Éxample <script>\\:*?", "example-script-123"),
                                      (None, "123"), ("日本", "123"), ("x" * 200, "x" * 64 + "-123")])
def test_safe_descriptive_filename(name, slug):
    report = build_scouting_report(pd.DataFrame({"pitch_type": ["FF"]}), 123,
                                   date(2025, 4, 1), date(2025, 4, 3))
    assert report_filename(replace(report, pitcher_name=name)) == (
        f"scouting-report-{slug}-2025-04-01-2025-04-03.html")
