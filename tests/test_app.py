"""Offline smoke coverage for the Streamlit dashboard foundation."""

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_dashboard_renders_without_data() -> None:
    """The initial dashboard renders navigation without fake metrics."""
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=10)

    assert not app.exception
    assert app.title[0].value == "Pitch Analytics Platform"
    assert [header.value for header in app.main.header] == [
        "Pitcher selection and analysis",
    ]
    assert [tab.label for tab in app.tabs] == [
        "Pitcher Analysis", "Pitch Arsenal", "Visualizations", "Scouting Report",
    ]
    assert app.sidebar.header[0].value == "Pitcher selection"
    assert app.sidebar.text_input[0].value == ""
    assert "No player data is loaded or retrieved" in app.info[0].value
    assert len(app.metric) == 0


def test_request_preview_and_failure_clear_previous_result(monkeypatch) -> None:
    from unittest.mock import Mock
    import pandas as pd
    from statcast_validation import StatcastError

    fetch = Mock(return_value=pd.DataFrame({"pitcher": [123], "release_speed": [None]}))
    monkeypatch.setattr("statcast_service.get_pitcher_statcast", fetch)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    fetch.assert_not_called()
    app.sidebar.radio(key="selection_source").set_value("Manual ID").run()
    app.sidebar.text_input(key="pitcher_id").set_value("123")
    app.sidebar.button(key="request_data").click().run()
    assert not app.exception
    assert app.metric[0].value == "1"
    assert len(app.dataframe[0].value) == 1
    app.run()
    assert fetch.call_count == 1
    assert len(app.dataframe) == 2
    assert app.dataframe[1].value["valid_paired"].eq(0).all()
    fetch.side_effect = StatcastError("Unable to retrieve data")
    app.sidebar.button(key="request_data").click().run()
    assert not app.exception
    assert app.error[0].value == "Unable to retrieve data"
    assert len(app.dataframe) == 0


def _request_app(monkeypatch, data):
    """Submit mocked pitch rows without contacting Statcast."""
    from unittest.mock import Mock

    fetch = Mock(return_value=data)
    monkeypatch.setattr("statcast_service.get_pitcher_statcast", fetch)
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py")).run()
    fetch.assert_not_called()
    app.sidebar.radio(key="selection_source").set_value("Manual ID").run()
    app.sidebar.text_input(key="pitcher_id").set_value("123")
    app.sidebar.button(key="request_data").click().run()
    assert not app.exception
    assert fetch.call_count == 1
    if not data.empty:
        app.button(key="generate_report").click().run()
        assert not app.exception
    return app, fetch


def test_arsenal_success_formats_and_repeat_use(monkeypatch):
    import json
    import pandas as pd
    from pitch_arsenal import aggregate_pitch_arsenal

    # Synthetic UI fixture only; not a player record.
    data = pd.DataFrame({
        "pitch_type": ["FF", "SL", "FF", None],
        "release_speed": [94.123, 85.0, 96.0, 90.0],
        "release_spin_rate": [2200, 2500, 2300, 2100],
        "pfx_x": [-1.0, 0.5, -0.5, 0.0],
        "pfx_z": [1.0, -0.25, 1.5, 0.0],
    })
    original = data.copy(deep=True)
    app, fetch = _request_app(monkeypatch, data)
    assert "Pitch Arsenal" in [h.value for h in app.header]
    pd.testing.assert_frame_equal(app.dataframe[0].value, data)
    pd.testing.assert_frame_equal(app.dataframe[1].value, aggregate_pitch_arsenal(data).metrics)
    assert app.metric[1].label == "Unclassified pitches"
    assert app.metric[1].value == "1"
    assert any("only from classified pitches" in c.value for c in app.caption)
    config = json.loads(app.dataframe[1].proto.columns)
    expected = {
        "pitch_count": ("Pitch count", "%,d"),
        "usage_pct": ("Usage (%)", "%.1f%%"),
        "avg_release_speed_mph": ("Avg velocity (mph)", "%.1f"),
        "max_release_speed_mph": ("Max velocity (mph)", "%.1f"),
        "avg_spin_rate_rpm": ("Avg spin (rpm)", "%.0f"),
        "avg_pfx_x_inches": ("Avg horizontal movement (in)", "%+.1f"),
        "avg_pfx_z_inches": ("Avg vertical movement (in)", "%+.1f"),
    }
    for column, (label, number_format) in expected.items():
        assert config[column]["label"] == label
        assert config[column]["type_config"]["format"] == number_format
    app.run()
    assert not app.exception
    assert fetch.call_count == 1
    assert len(app.dataframe) == 3
    assert "valid_paired" in app.dataframe[-1].value.columns
    fetch.return_value = data.iloc[[1]].copy()
    app.sidebar.button(key="request_data").click().run()
    assert not app.exception
    assert fetch.call_count == 2
    assert app.dataframe[1].value["pitch_type"].tolist() == ["SL"]
    assert app.metric[1].value == "0"
    pd.testing.assert_frame_equal(data, original)


def test_arsenal_missing_measurements(monkeypatch):
    import pandas as pd

    app, _ = _request_app(monkeypatch, pd.DataFrame({
        "pitch_type": ["FF", "SL"], "release_speed": [None, 0.0],
        "pfx_x": [None, 0.0], "pfx_z": [None, -0.5],
    }))
    metrics = app.dataframe[1].value.set_index("pitch_type")
    assert metrics.loc["FF"].drop(["pitch_count", "usage_pct"]).isna().all()
    assert metrics["avg_spin_rate_rpm"].isna().all()
    assert metrics.loc["SL", "avg_release_speed_mph"] == 0
    assert metrics.loc["SL", "avg_pfx_x_inches"] == 0
    assert metrics.loc["SL", "avg_pfx_z_inches"] == -6


def test_arsenal_empty_and_unclassified(monkeypatch):
    import pandas as pd

    for data, count in [(pd.DataFrame({"pitch_type": []}), 0),
                        (pd.DataFrame({"pitch_type": [None, "", " "]}), 3)]:
        app, _ = _request_app(monkeypatch, data)
        if data.empty:
            assert not app.metric and not app.dataframe
            assert any("No records found" in info.value for info in app.info)
            continue
        assert len(app.dataframe) == 2  # Include unclassified movement coverage.
        assert app.metric[1].value == str(count)
        assert any("No classified pitches" in info.value for info in app.info)


def test_arsenal_cleared_for_all_retrieval_failures(monkeypatch):
    import pandas as pd
    from statcast_validation import (
        InputValidationError, NoStatcastDataError, ResponseValidationError, StatcastError,
    )

    for error in [InputValidationError, NoStatcastDataError, ResponseValidationError, StatcastError]:
        app, fetch = _request_app(monkeypatch, pd.DataFrame({"pitch_type": ["FF"]}))
        assert len(app.dataframe) == 3
        assert "valid_paired" in app.dataframe[-1].value.columns
        fetch.side_effect = error("Request failed")
        app.sidebar.button(key="request_data").click().run()
        assert not app.exception
        assert fetch.call_count == 2
        assert len(app.dataframe) == 0
        assert len(app.metric) == 0
        assert "Pitch Arsenal" not in [h.value for h in app.header]
        assert app.session_state.get("statcast_result") is None
        app.run()
        assert not app.exception
        assert len(app.dataframe) == 0
        assert fetch.call_count == 2
        fetch.side_effect = None
        app.sidebar.button(key="request_data").click().run()
        assert not app.exception
        assert len(app.dataframe) == 3
        assert "valid_paired" in app.dataframe[-1].value.columns
        assert fetch.call_count == 3


def test_arsenal_uses_full_result_beyond_preview(monkeypatch):
    """The 100-row preview must not truncate the arsenal's denominator."""
    import pandas as pd

    data = pd.DataFrame({"pitch_type": ["FF"] * 100 + ["SL"] * 25})
    app, fetch = _request_app(monkeypatch, data)
    assert len(app.dataframe[0].value) == 100
    metrics = app.dataframe[1].value.set_index("pitch_type")
    assert metrics["pitch_count"].to_dict() == {"FF": 100, "SL": 25}
    assert metrics["usage_pct"].to_dict() == {"FF": 80, "SL": 20}
    app.run()
    assert not app.exception
    assert fetch.call_count == 1


def test_movement_filter_reset_and_independent_charts(monkeypatch):
    import json
    import pandas as pd
    from statcast_validation import StatcastError

    data = pd.DataFrame({'pitch_type': ['FF', 'SL'], 'pfx_x': [1, None],
                         'pfx_z': [2, None], 'plate_x': [None, -1], 'plate_z': [None, 2]})
    app, fetch = _request_app(monkeypatch, data)
    assert app.multiselect[0].value == ['FF', 'SL']
    assert len(app.get('plotly_chart')) == 3
    app.multiselect[0].set_value(['SL']).run()
    assert not app.exception
    assert fetch.call_count == 1
    assert app.dataframe[-1].value.pitch_type.tolist() == ['SL']
    assert app.dataframe[-1].value.valid_paired.tolist() == [0]
    assert len(app.get('plotly_chart')) == 2
    spec = json.loads(app.get('plotly_chart')[0].proto.spec)
    assert spec['data'][0]['x'] == [-1]
    app.multiselect[0].set_value(['FF']).run()
    assert not app.exception
    assert len(app.get('plotly_chart')) == 2
    spec = json.loads(app.get('plotly_chart')[0].proto.spec)
    assert spec['data'][0]['x'] == [12]
    app.multiselect[0].set_value([]).run()
    assert not app.exception
    assert len(app.get('plotly_chart')) == 1  # Usage retains the full loaded arsenal.
    assert any('Select at least one' in i.value for i in app.info)
    fetch.return_value = data.iloc[[0]]
    app.sidebar.text_input(key="pitcher_id").set_value('456')
    from datetime import date
    app.sidebar.date_input[0].set_value(date(2026, 1, 1))
    app.sidebar.date_input[1].set_value(date(2026, 1, 30))
    app.sidebar.button(key="request_data").click().run()
    assert not app.exception
    assert app.multiselect[0].options == ['FF']
    assert app.multiselect[0].value == ['FF']
    assert fetch.call_count == 2
    fetch.side_effect = StatcastError('Request failed')
    app.sidebar.button(key="request_data").click().run()
    assert not app.exception
    assert not app.multiselect and not app.get('plotly_chart')
    assert not app.dataframe


def test_usage_full_dataset_reruns_and_failure(monkeypatch):
    import json
    import pandas as pd
    from statcast_validation import StatcastError

    data = pd.DataFrame({'pitch_type': ['FF'] * 100 + ['SL'] * 25 + [None] * 5})
    app, fetch = _request_app(monkeypatch, data)
    def usage_spec():
        return json.loads(app.get('plotly_chart')[-1].proto.spec)
    spec = usage_spec()
    assert spec['data'][0]['y'] == ['FF', 'SL']
    assert spec['data'][0]['x'] == [80, 20]
    assert spec['data'][0]['customdata'] == [[100], [25]]
    assert any('Unclassified pitches: 5 (excluded)' in c.value for c in app.caption)
    app.multiselect[0].set_value([]).run()
    assert not app.exception
    assert usage_spec() == spec
    assert fetch.call_count == 1
    fetch.return_value = pd.DataFrame({'pitch_type': ['SL']})
    app.sidebar.button(key="request_data").click().run()
    assert not app.exception
    assert usage_spec()['data'][0]['x'] == [100]
    fetch.side_effect = StatcastError('Request failed')
    app.sidebar.button(key="request_data").click().run()
    assert not app.exception
    assert not app.get('plotly_chart')
    assert any('Load Statcast records' in i.value for i in app.info)
    assert fetch.call_count == 3


def test_usage_empty_and_unclassified_messages(monkeypatch):
    import pandas as pd

    for data, message in [
        (pd.DataFrame(), 'No records found. Choose another pitcher or date range.'),
        (pd.DataFrame({'pitch_type': [None, ' ']}),
         'No classified pitches available for pitch usage.'),
    ]:
        app, fetch = _request_app(monkeypatch, data)
        assert any(i.value == message for i in app.info)
        assert not app.get('plotly_chart')
        app.run()
        assert not app.exception
        assert fetch.call_count == 1


def test_scouting_report_tracks_submitted_identity_dates_and_clears(monkeypatch):
    from datetime import date
    import pandas as pd
    from statcast_validation import StatcastError

    app, fetch = _request_app(monkeypatch, pd.DataFrame({"pitch_type": ["FF"], "release_speed": [95]}))
    assert any("MLBAM 123" in text.value for text in app.text)
    assert len(app.get("download_button")) == 1
    timestamp = app.session_state["scouting_report"][1]
    app.run()
    assert app.session_state["scouting_report"][1] == timestamp
    app.sidebar.text_input(key="pitcher_id").set_value("456")
    app.sidebar.date_input[0].set_value(date(2025, 4, 1))
    app.sidebar.date_input[1].set_value(date(2025, 4, 3))
    app.sidebar.button(key="request_data").click().run()
    assert not app.exception
    assert not app.get("download_button")
    app.button(key="generate_report").click().run()
    assert any("MLBAM 456" in text.value for text in app.text)
    assert any("2025-04-01 through 2025-04-03" in text.value for text in app.text)
    assert not any("MLBAM 123" in text.value for text in app.text)
    fetch.side_effect = StatcastError("Retrieval failed")
    app.sidebar.button(key="request_data").click().run()
    assert not app.exception
    assert not app.get("download_button")
    assert not app.table
    assert "scouting_report" not in app.session_state
    assert not any("MLBAM 456" in text.value for text in app.text)


def test_focused_arsenal_views_preserve_values_and_loaded_state(monkeypatch):
    import pandas as pd
    import json
    from pitch_arsenal import aggregate_pitch_arsenal

    data = pd.DataFrame({"pitch_type": ["FF", "SL", None],
                         "release_speed": [None, 0, 91],
                         "pfx_x": [None, 0, 1], "pfx_z": [None, -1, 1]})
    app, fetch = _request_app(monkeypatch, data)
    expected = aggregate_pitch_arsenal(data).metrics
    timestamp = app.session_state["scouting_report"][1]
    for view, columns in [
        ("Usage", ["pitch_type", "pitch_count", "usage_pct"]),
        ("Velocity and spin", ["pitch_type", "pitch_count", "avg_release_speed_mph",
                               "max_release_speed_mph", "avg_spin_rate_rpm"]),
        ("Movement", ["pitch_type", "pitch_count", "avg_pfx_x_inches", "avg_pfx_z_inches"]),
        ("All metrics", list(expected.columns)),
    ]:
        app.radio(key="arsenal_metrics").set_value(view).run()
        assert not app.exception
        pd.testing.assert_frame_equal(app.dataframe[1].value, expected)
        assert list(app.dataframe[1].proto.column_order) == columns
        assert app.session_state["scouting_report"][1] == timestamp
        assert len(app.get("download_button")) == 1
    assert fetch.call_count == 1
    assert any("Empty measurement cells mean unavailable" in c.value for c in app.caption)
    assert "Movement measurement coverage" in [s.value for s in app.subheader]
    specs = [json.loads(chart.proto.spec) for chart in app.get("plotly_chart")]
    usage = specs[-1]["data"][0]
    usage_colors = dict(zip(usage["y"], usage["marker"]["color"]))
    movement_colors = {trace["name"]: trace["marker"]["color"] for trace in specs[0]["data"]}
    assert movement_colors["SL"] == usage_colors["SL"]


def test_accessible_native_controls_and_scrollable_presentations(monkeypatch):
    """Inspect public element configuration, independently of frontend markup."""
    import json
    import pandas as pd

    app, fetch = _request_app(monkeypatch, pd.DataFrame({
        "pitch_type": ["FF", "SL"], "pfx_x": [-1., .5], "pfx_z": [1., -.25],
        "plate_x": [-.4, .5], "plate_z": [2., 3.],
    }))
    assert not app.radio(key="arsenal_metrics").proto.horizontal
    assert app.radio(key="arsenal_metrics").label == "Arsenal metrics"
    assert [widget.label for widget in app.date_input] == ["Start date", "End date"]
    assert app.multiselect(key="analysis_pitch_types").label == "Pitch types"
    for table in app.dataframe:
        assert table.proto.alt
    for table in app.dataframe[1:]:
        assert json.loads(table.proto.columns)["pitch_type"]["pinned"] is True
    for chart in app.get("plotly_chart"):
        assert chart.proto.alt
        spec = json.loads(chart.proto.spec)
        assert spec["layout"]["autosize"] is True
        assert "width" not in spec["layout"]
    assert app.table[0].proto.alt == "Scouting arsenal metrics and valid sample counts"
    assert any("Scroll the arsenal table" in c.value for c in app.caption)
    assert any("top-left toggle" in c.value for c in app.caption)
    assert fetch.call_count == 1
