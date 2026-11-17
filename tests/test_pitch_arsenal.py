"""Synthetic, offline scouting summaries; no player records or API requests."""
from datetime import date

import numpy as np
import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from pitch_arsenal import aggregate_pitch_arsenal
from statcast_validation import ResponseValidationError, validate_response


def test_counts_usage_measurements_and_input_preserved():
    data = pd.DataFrame({
        "pitch_type": ["FF", "SL", "FF", None],
        "release_speed": [94, 84, 98, 100],
        "release_spin_rate": [2200, 2500, 2400, 9999],
        "pfx_x": [-1, .5, -.5, 99], "pfx_z": [1, -.25, 1.5, 99],
    }, index=[2, 2, 1, 0])
    original = data.copy(deep=True)
    result = aggregate_pitch_arsenal(data)
    assert result.unclassified_pitch_count == 1
    assert result.metrics.pitch_type.tolist() == ["FF", "SL"]
    ff, sl = result.metrics.to_dict("records")
    assert ff == pytest.approx({
        "pitch_type": "FF", "pitch_count": 2, "usage_pct": 200 / 3,
        "avg_release_speed_mph": 96, "max_release_speed_mph": 98,
        "avg_spin_rate_rpm": 2300, "avg_pfx_x_inches": -9,
        "avg_pfx_z_inches": 15,
    })
    assert sl["usage_pct"] == pytest.approx(100 / 3)
    assert sl["avg_pfx_x_inches"] == 6
    assert sl["avg_pfx_z_inches"] == -3
    assert result.metrics.usage_pct.sum() == pytest.approx(100)
    assert_frame_equal(data, original)


@pytest.mark.parametrize("column", ["release_speed", "release_spin_rate", "pfx_x", "pfx_z"])
def test_missing_malformed_and_nonfinite_measurements(column):
    values = [None, pd.NA, np.nan, "bad", np.inf, -np.inf, "inf", True,
              np.bool_(False), 1j, [], {}, "12", 0]
    result = aggregate_pitch_arsenal(pd.DataFrame({
        "pitch_type": ["FF"] * len(values), column: values,
    })).metrics.iloc[0]
    target = {"release_speed": "avg_release_speed_mph",
              "release_spin_rate": "avg_spin_rate_rpm",
              "pfx_x": "avg_pfx_x_inches", "pfx_z": "avg_pfx_z_inches"}[column]
    assert result[target] == (72 if column.startswith("pfx") else 6)
    assert result.pitch_count == len(values)
    if column == "release_speed":
        assert result.max_release_speed_mph == 12


@pytest.mark.parametrize("data,unclassified", [
    (pd.DataFrame(), 0),
    (pd.DataFrame(columns=["pitch_type", "release_speed"]), 0),
    (pd.DataFrame({"pitch_type": [None, pd.NA, "", "  ", 1, True, [], {}]}), 8),
    (pd.DataFrame({"release_speed": [90, 95]}), 2),
])
def test_empty_and_unclassified_schema(data, unclassified):
    result = aggregate_pitch_arsenal(data)
    assert result.metrics.empty
    assert result.unclassified_pitch_count == unclassified
    assert result.metrics.columns.tolist() == [
        "pitch_type", "pitch_count", "usage_pct", "avg_release_speed_mph",
        "avg_spin_rate_rpm", "max_release_speed_mph", "avg_pfx_x_inches",
        "avg_pfx_z_inches",
    ]
    assert result.metrics.pitch_count.dtype == np.dtype("int64")


def test_missing_columns_and_all_missing_measurements_remain_missing():
    result = aggregate_pitch_arsenal(pd.DataFrame({
        "pitch_type": ["FF", "FF"], "release_speed": ["bad", np.inf],
    })).metrics.iloc[0]
    assert result.pitch_count == 2
    assert result.usage_pct == 100
    assert result.iloc[3:].isna().all()


def test_deterministic_order_and_type_normalization():
    data = pd.DataFrame({"pitch_type": ["SL", " CU ", "FF", "FF", "new"]})
    expected = aggregate_pitch_arsenal(data).metrics
    assert expected.pitch_type.tolist() == ["FF", "CU", "SL", "new"]
    assert_frame_equal(expected, aggregate_pitch_arsenal(data.iloc[::-1]).metrics)


def test_validated_frame_integration_preserves_validation_contract():
    day = date(2024, 4, 1)
    raw = pd.DataFrame({"game_date": [day, day], "pitcher": [123, 123],
                        "pitch_type": ["FF", None], "release_speed": ["95", None],
                        "pfx_x": [-1, None], "pfx_z": [1, None],
                        "release_spin_rate": ["malformed", True]})
    validated = validate_response(raw, 123, day, day)
    original = validated.copy(deep=True)
    result = aggregate_pitch_arsenal(validated)
    assert result.metrics.iloc[0].avg_release_speed_mph == 95
    assert pd.isna(result.metrics.iloc[0].avg_spin_rate_rpm)
    assert result.unclassified_pitch_count == 1
    assert_frame_equal(validated, original)
    raw["release_speed"] = "malformed"
    with pytest.raises(ResponseValidationError):
        validate_response(raw, 123, day, day)


@pytest.mark.parametrize("data,error", [(None, TypeError),
    (pd.DataFrame([["FF", "SL"]], columns=["pitch_type", "pitch_type"]), ValueError)])
def test_ambiguous_inputs_rejected(data, error):
    with pytest.raises(error):
        aggregate_pitch_arsenal(data)


def test_partial_measurements_use_independent_denominators():
    """Each metric counts its own observations, while usage counts all pitches."""
    result = aggregate_pitch_arsenal(pd.DataFrame({
        "pitch_type": ["FF", "FF", "FF", "SL"],
        "release_speed": [90, None, 96, None],
        "release_spin_rate": [None, 2400, None, None],
        "pfx_x": [-1, None, 0, None],
        "pfx_z": [None, .5, None, None],
    })).metrics.set_index("pitch_type")
    ff = result.loc["FF"]
    assert ff.to_dict() == pytest.approx({
        "pitch_count": 3, "usage_pct": 75,
        "avg_release_speed_mph": 93, "max_release_speed_mph": 96,
        "avg_spin_rate_rpm": 2400, "avg_pfx_x_inches": -6,
        "avg_pfx_z_inches": 6,
    })
    assert result.loc["SL", "usage_pct"] == 25
    assert result.loc["SL"].drop(["pitch_count", "usage_pct"]).isna().all()
