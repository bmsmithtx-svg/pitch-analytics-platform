"""Synthetic offline report fixtures; no real player records."""
from datetime import date, datetime, timezone

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from pitch_arsenal import aggregate_pitch_arsenal
from scouting_report import build_scouting_report
from report_export import export_report_html
from statcast_validation import InputValidationError

START = date(2025, 4, 1)
END = date(2025, 4, 30)


def report(data):
    return build_scouting_report(data, 123, START, END)


def fixture():
    return pd.DataFrame({
        "pitch_type": [" FF ", "SL", "FF", None],
        "release_speed": [94, 84, 96, 90], "release_spin_rate": [2200, None, 2400, 100],
        "pfx_x": [-1, 0.5, None, 0], "pfx_z": [1, -0.5, 1.5, 0],
        "release_pos_x": [0, "bad", 2, None], "release_pos_y": [54, 55, 56, 53],
        "release_pos_z": [6, 5, 6.5, None],
        "description": ["swinging_strike", "called_strike", "foul", None],
        "player_name": ["Synthetic fixture"] * 4,
    })


def test_report_reuses_arsenal_and_preserves_input():
    data = fixture()
    before = data.copy(deep=True)
    result = report(data)
    expected = aggregate_pitch_arsenal(data)
    assert_frame_equal(result.arsenal[expected.metrics.columns], expected.metrics)
    assert_frame_equal(data, before)
    assert result.total_pitches == 4
    assert result.unclassified_pitches == 1
    assert result.pitcher_name == "Synthetic fixture"
    ff, sl = result.arsenal.iloc[0], result.arsenal.iloc[1]
    assert ff.min_release_speed_mph == 94
    assert ff.avg_release_pos_x_ft == 1
    assert ff.valid_release_pos_x == 2
    assert ff.whiff_pct == 50
    assert ff.swings == 2
    assert sl.swings == 0 and np.isnan(sl.whiff_pct)
    assert np.isnan(sl.avg_release_pos_x_ft)
    assert any("release_pos_x: 2/4 usable; 2 missing or invalid" in n for n in result.notes)


@pytest.mark.parametrize("types", [[], [None, ""], ["XX"], ["SL", "SL"], ["XX", "FF"]])
def test_empty_unknown_single_and_multiple_types(types):
    result = report(pd.DataFrame({"pitch_type": types}))
    assert result.total_pitches == len(types)
    assert result.arsenal.pitch_count.sum() + result.unclassified_pitches == len(types)
    if not result.arsenal.empty:
        assert result.arsenal.usage_pct.sum() == pytest.approx(100)
        assert result.arsenal.whiff_pct.isna().all()
    else:
        assert "No classified pitches" in result.observations[0]
    assert "N/A" in export_report_html(result, datetime.now(timezone.utc))


def test_determinism_and_low_sample():
    data = fixture()
    one, two = report(data), report(data)
    assert_frame_equal(one.arsenal, two.arsenal)
    assert one.observations == two.observations
    assert one.notes == two.notes
    assert any("no velocity comparison" in x for x in one.observations)
    stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert export_report_html(one, stamp) == export_report_html(two, stamp)


def test_velocity_comparison_threshold():
    data = pd.DataFrame({"pitch_type": ["FF"] * 20 + ["SL"] * 20,
                         "release_speed": [95] * 20 + [85] * 20})
    assert any("10.0 mph" in x for x in report(data).observations)
    assert not any("separation:" in x for x in report(data.iloc[:-1]).observations)


@pytest.mark.parametrize("bad", [True, "broken", float("inf"), [1], None])
def test_invalid_optional_measurements_report_coverage(bad):
    result = report(pd.DataFrame({"pitch_type": ["FF"], "release_pos_x": [bad]}))
    assert result.arsenal.valid_release_pos_x.iloc[0] == 0
    assert np.isnan(result.arsenal.avg_release_pos_x_ft.iloc[0])
    assert any("release_pos_x: 0/1 usable; 1 missing or invalid" in n for n in result.notes)


def test_export_content_and_escaping():
    data = fixture()
    data["pitch_type"] = '<script>alert("x")</script>'
    data["player_name"] = '<img src=x onerror="x">'
    result = report(data)
    stamp = datetime(2026, 1, 2, tzinfo=timezone.utc)
    html = export_report_html(result, stamp)
    assert "<script>" not in html and "<img " not in html
    assert "&lt;script&gt;" in html and "&lt;img" in html
    for text in ("MLBAM 123", "2025-04-01", "2025-04-30", "2026-01-02T00:00:00+00:00",
                 "Total pitches analyzed: 4", "Baseball Savant", "N/A", "not grades"):
        assert text in html
    with pytest.raises(ValueError):
        export_report_html(result, datetime(2026, 1, 1))


def test_constraints_and_duplicate_columns():
    with pytest.raises(InputValidationError):
        build_scouting_report(fixture(), 123, START, date(2025, 5, 1))
    with pytest.raises(ValueError):
        report(pd.DataFrame([[1, 2]], columns=["pitch_type", "pitch_type"]))


def test_ambiguous_name_is_unavailable():
    data = fixture()
    data.loc[0, "player_name"] = "Another synthetic label"
    assert report(data).pitcher_name is None


def test_empty_schema_and_arbitrary_code_export():
    empty = report(pd.DataFrame())
    full = report(fixture())
    assert list(empty.arsenal.columns) == list(full.arsenal.columns)
    odd = report(pd.DataFrame({"pitch_type": ["Metric", "Pitch type", "<b>"]}))
    assert "Pitch type: Metric" in export_report_html(odd, datetime.now(timezone.utc))
