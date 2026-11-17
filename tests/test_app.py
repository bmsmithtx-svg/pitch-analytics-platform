"""Offline smoke coverage for the Streamlit dashboard foundation."""

from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_dashboard_renders_without_data() -> None:
    """The initial dashboard renders its planned sections without fake metrics."""
    app_path = Path(__file__).resolve().parents[1] / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=10)

    assert not app.exception
    assert app.title[0].value == "Pitch Analytics Platform"
    assert [header.value for header in app.main.header] == [
        "Statcast data",
        "Performance metrics",
        "Pitch visualizations",
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
    app.sidebar.text_input[0].set_value("123")
    app.sidebar.button[0].click().run()
    assert not app.exception
    assert app.metric[0].value == "1"
    assert len(app.dataframe[0].value) == 1
    app.run()
    assert fetch.call_count == 1
    assert len(app.dataframe) == 1
    fetch.side_effect = StatcastError("Unable to retrieve data")
    app.sidebar.button[0].click().run()
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
    app.sidebar.text_input[0].set_value("123")
    app.sidebar.button[0].click().run()
    assert not app.exception
    assert fetch.call_count == 1
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
    assert len(app.dataframe) == 2
    fetch.return_value = data.iloc[[1]].copy()
    app.sidebar.button[0].click().run()
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
        assert len(app.dataframe) == 1  # Preserve preview, omit empty arsenal table.
        assert app.metric[1].value == str(count)
        assert any("No classified pitches" in info.value for info in app.info)


def test_arsenal_cleared_for_all_retrieval_failures(monkeypatch):
    import pandas as pd
    from statcast_validation import (
        InputValidationError, NoStatcastDataError, ResponseValidationError, StatcastError,
    )

    for error in [InputValidationError, NoStatcastDataError, ResponseValidationError, StatcastError]:
        app, fetch = _request_app(monkeypatch, pd.DataFrame({"pitch_type": ["FF"]}))
        assert len(app.dataframe) == 2
        fetch.side_effect = error("Request failed")
        app.sidebar.button[0].click().run()
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
        app.sidebar.button[0].click().run()
        assert not app.exception
        assert len(app.dataframe) == 2
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
