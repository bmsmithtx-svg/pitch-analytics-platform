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
        "Performance metrics",
        "Pitch visualizations",
    ]
    assert app.sidebar.header[0].value == "Pitcher selection"
    assert app.sidebar.selectbox[0].disabled
    assert app.sidebar.selectbox[0].value is None
    assert "No player data is loaded or retrieved" in app.info[0].value
    assert len(app.metric) == 0
