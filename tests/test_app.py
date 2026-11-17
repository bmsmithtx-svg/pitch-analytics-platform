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
