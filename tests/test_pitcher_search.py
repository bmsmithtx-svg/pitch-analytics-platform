"""Deterministic identity fixtures only; no real player statistics or HTTP."""
from unittest.mock import Mock

import pytest
import requests

from pitcher_search import (
    ENDPOINT, PitcherSearchError, SearchResponseError, SearchValidationError,
    exact_matches, fetch_candidates, normalize_query, parse_candidates,
    resolve_candidate, validate_player_id,
)


def person(player_id=123, name="Example Pitcher", **metadata):
    return dict(id=player_id, fullName=name, **metadata)


@pytest.mark.parametrize("query,expected", [
    ("Example Pitcher", "Example Pitcher"), ("  Example   Pitcher  ", "Example Pitcher"),
    ("eXample PITCHER", "eXample PITCHER"), ("José Pérez", "José Pérez"),
    ("Jean-Luc O'Example Jr.", "Jean-Luc O'Example Jr."),
    ("Jose\u0301 Pérez", "José Pérez"), ("李 明", "李 明"),
])
def test_query_normalization(query, expected):
    assert normalize_query(query) == expected


@pytest.mark.parametrize("query", ["", "   ", "A", "a" * 101, "Ab\nCd", "Ab\tCd", "Ab\x00Cd",
                                         "Ab\u200bCd", "12", "Ab1", "<script>", None, 123])
def test_invalid_queries(query):
    with pytest.raises(SearchValidationError):
        normalize_query(query)


@pytest.mark.parametrize("value", [True, False, 1.0, 0, -1, "0", "-1", "1.0", " 1", "1 ",
                                        "1e2", "１２", None, "", "1" * 11])
def test_invalid_ids(value):
    with pytest.raises(SearchValidationError):
        validate_player_id(value)
    with pytest.raises(SearchResponseError):
        parse_candidates({"people": [person(value)]})


@pytest.mark.parametrize("value", [123, "123", "00123"])
def test_valid_ids(value):
    assert validate_player_id(value) == 123


def test_optional_historical_two_way_and_labels():
    candidates = parse_candidates({"people": [person(), person(456, "Historical Example", active=False,
        birthDate="1900-01-01", primaryPosition={"name": "Two-Way Player"}, currentTeam={"name": "Example Team"})]})
    assert candidates[0].active is None
    assert candidates[0].label() == "Example Pitcher · MLB ID 123"
    assert candidates[1].label() == "Historical Example · Example Team · Two-Way Player · Inactive · Born 1900-01-01 · MLB ID 456"


@pytest.mark.parametrize("payload", [None, [], {}, {"people": None}, {"people": {}},
    {"people": [None]}, {"people": [{}]}, {"people": [person(name=123)]},
    *({"people": [person(**metadata)]} for metadata in [
        {"active": "false"}, {"active": 1}, {"birthDate": "bad"}, {"birthDate": 123},
        {"primaryPosition": []}, {"primaryPosition": {"name": 1}},
        {"currentTeam": "Team"}, {"currentTeam": {"name": ""}},
    ])])
def test_malformed_records_fail_whole_response(payload):
    with pytest.raises(SearchResponseError):
        parse_candidates(payload)


def test_deduplication_and_order_independent_of_source_order():
    rows = [person(456, "Same Name"), person(123, "Same Name"), person(123, "Same Name", active=False),
            person(789, "Another Example")]
    forward = parse_candidates({"people": rows})
    assert forward == parse_candidates({"people": rows[::-1]})
    assert [c.player_id for c in forward] == [789, 123, 456]
    assert forward[1].active is False
    assert resolve_candidate("same name", forward) is None
    assert len(exact_matches(" SAME  NAME ", forward)) == 2


@pytest.mark.parametrize("rows,query,expected", [
    ([person()], " example   PITCHER ", 123),
    ([person(), person(456, "Other Example")], "Example Pitcher", 123),
    ([person()], "Example", None),
    ([person(), person(456, "Example Other")], "Example", None),
    ([person(), person(456)], "Example Pitcher", None),
    ([], "Example Pitcher", None),
    ([person(), person()], "Example Pitcher", 123),
])
def test_resolution(rows, query, expected):
    resolved = resolve_candidate(query, parse_candidates({"people": rows}))
    assert (resolved.player_id if resolved else None) == expected


def response(payload=None, status=200):
    result = Mock(status_code=status)
    result.json.return_value = payload if payload is not None else {"people": [person()]}
    if status >= 400:
        result.raise_for_status.side_effect = requests.HTTPError()
    return result


def test_request_contract_and_empty_success(monkeypatch):
    get = Mock(return_value=response({"people": []}))
    monkeypatch.setattr("pitcher_search.requests.get", get)
    assert fetch_candidates("  Example  Pitcher ") == ()
    get.assert_called_once_with(ENDPOINT, params={"names": "Example Pitcher"}, timeout=(5, 15))


@pytest.mark.parametrize("failure,message", [
    (requests.Timeout(), "timed out"), (requests.ConnectionError(), "Cannot connect"),
    (response(status=429), "rate limited"), (response(status=500), "HTTP error"),
    (response(status=404), "HTTP error"), (response({"wrong": []}), "unexpected response"),
])
def test_network_failures(monkeypatch, failure, message):
    get = Mock(side_effect=failure) if isinstance(failure, Exception) else Mock(return_value=failure)
    monkeypatch.setattr("pitcher_search.requests.get", get)
    with pytest.raises(PitcherSearchError, match=message):
        fetch_candidates("Example Pitcher")
    assert get.call_count == 1


def test_invalid_json(monkeypatch):
    result = response()
    result.json.side_effect = ValueError()
    monkeypatch.setattr("pitcher_search.requests.get", Mock(return_value=result))
    with pytest.raises(SearchResponseError, match="invalid JSON"):
        fetch_candidates("Example Pitcher")


def test_cache_success_and_failures(monkeypatch):
    from app import cached_player_search
    cached_player_search.clear()
    bad_json = response()
    bad_json.json.side_effect = ValueError()
    get = Mock(side_effect=[response(), requests.Timeout(), response(status=429),
                           response(status=500), bad_json, response({"bad": []}), response()])
    monkeypatch.setattr("pitcher_search.requests.get", get)
    try:
        assert cached_player_search("example pitcher")[0].player_id == 123
        assert cached_player_search("example pitcher")[0].player_id == 123
        assert get.call_count == 1
        # Success for one name must not mask failure for another. Failures retry.
        for _ in range(5):
            with pytest.raises(PitcherSearchError):
                cached_player_search("other example")
        assert cached_player_search("other example")[0].player_id == 123
        assert get.call_count == 7
    finally:
        cached_player_search.clear()
