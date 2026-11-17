"""Synthetic contracts and mocked retrieval; no live Statcast requests."""
from datetime import date
from unittest.mock import Mock

import pandas as pd
import pytest

import statcast_service as service
from statcast_validation import (
    InputValidationError, NoStatcastDataError, ResponseValidationError,
    StatcastError, validate_request, validate_response,
)

START = date(2024, 4, 1)
END = date(2024, 4, 30)


@pytest.fixture
def records():
    return pd.DataFrame({"game_date": ["2024-04-01"], "pitcher": [123],
                         "pitch_type": [None], "release_speed": [None],
                         "pfx_x": [0.0], "pfx_z": [1.2]})


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    import pybaseball
    monkeypatch.setattr(pybaseball, "statcast_pitcher", Mock(side_effect=AssertionError("Network forbidden")))
    service._cached_pitcher_statcast.clear()
    yield
    service._cached_pitcher_statcast.clear()


@pytest.mark.parametrize("pitcher,start,end", [
    ("", START, END), (0, START, END), (-1, START, END), (True, START, END),
    (1.5, START, END), ("1.5", START, END), ("x", START, END),
    (123, END, START), (123, START, date(2024, 5, 1)),
    (123, None, END), (123, "2024-04-01", END),
])
def test_invalid_requests_never_fetch(pitcher, start, end):
    with pytest.raises(InputValidationError):
        service.get_pitcher_statcast(pitcher, start, end)


def test_inclusive_boundary():
    assert validate_request(" 00123 ", START, END) == (123, START, END)
    assert validate_request(123, START, START) == (123, START, START)


def test_missing_measurements_preserved(records):
    result = validate_response(records, 123, START, END)
    assert pd.isna(result.loc[0, "release_speed"])
    assert pd.isna(result.loc[0, "pitch_type"])
    assert result.loc[0, "pfx_x"] == 0
    assert records.loc[0, "game_date"] == "2024-04-01"


@pytest.mark.parametrize("response", [None, {}, "bad", pd.DataFrame({"foo": [1]})])
def test_malformed_response(response):
    with pytest.raises(ResponseValidationError):
        validate_response(response, 123, START, END)


@pytest.mark.parametrize("column,value", [
    ("pitcher", None), ("pitcher", 456), ("game_date", None),
    ("game_date", "bad"), ("game_date", "2024-05-01"),
    ("release_speed", "bad"), ("pfx_x", float("inf")),
])
def test_bad_values(records, column, value):
    records[column] = value
    with pytest.raises(ResponseValidationError):
        validate_response(records, 123, START, END)


def test_duplicate_columns(records):
    records.columns = ["pitcher"] * len(records.columns)
    with pytest.raises(ResponseValidationError):
        validate_response(records, 123, START, END)


def test_fetch_signature_cache_and_copy(monkeypatch, records):
    fetch = Mock(return_value=records)
    monkeypatch.setattr("pybaseball.statcast_pitcher", fetch)
    first = service.get_pitcher_statcast("00123", START, END)
    first.loc[0, "pfx_x"] = 99
    second = service.get_pitcher_statcast(123, START, END)
    assert second.loc[0, "pfx_x"] == 0
    fetch.assert_called_once_with(start_dt="2024-04-01", end_dt="2024-04-30", player_id=123)
    service.get_pitcher_statcast(123, START, START)
    assert fetch.call_count == 2


@pytest.mark.parametrize("response,error", [(pd.DataFrame(), NoStatcastDataError), (None, ResponseValidationError)])
def test_unsuccessful_responses_not_cached(monkeypatch, response, error):
    fetch = Mock(return_value=response)
    monkeypatch.setattr("pybaseball.statcast_pitcher", fetch)
    for _ in range(2):
        with pytest.raises(error):
            service.get_pitcher_statcast(123, START, END)
    assert fetch.call_count == 2


def test_network_error_not_cached(monkeypatch):
    fetch = Mock(side_effect=ConnectionError("private upstream detail"))
    monkeypatch.setattr("pybaseball.statcast_pitcher", fetch)
    for _ in range(2):
        with pytest.raises(StatcastError, match="Check your connection"):
            service.get_pitcher_statcast(123, START, END)
    assert fetch.call_count == 2
