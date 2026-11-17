"""Bounded pitcher-level Statcast retrieval with successful-result caching."""

from datetime import date

import pandas as pd
import streamlit as st

from statcast_validation import StatcastError, validate_request, validate_response


def fetch_pitcher_statcast(pitcher_id: int, start_date: date, end_date: date) -> pd.DataFrame:
    """Fetch raw pitch rows from Baseball Savant through pybaseball 2.2.7.

    Installed signature verified: statcast_pitcher(start_dt=None, end_dt=None,
    player_id=None). The upstream API includes regular season, postseason and
    spring games; we add no game-type filters, aggregation or deduplication.
    """
    pitcher_id, start_date, end_date = validate_request(pitcher_id, start_date, end_date)
    try:
        from pybaseball import statcast_pitcher

        response = statcast_pitcher(
            start_dt=start_date.isoformat(), end_dt=end_date.isoformat(), player_id=pitcher_id
        )
    except Exception as exc:
        # pybaseball may raise requests, parsing, or internal errors. Do not expose
        # raw upstream errors in the UI; response contract failures are separate.
        raise StatcastError("Unable to retrieve Statcast data. Check your connection and try again.") from exc
    return validate_response(response, pitcher_id, start_date, end_date)


@st.cache_data(ttl=3600, max_entries=64, show_spinner=False)
def _cached_pitcher_statcast(pitcher_id: int, start_date: date, end_date: date) -> pd.DataFrame:
    """Cache validated nonempty results for one hour, up to 64 requests.

    Exceptions (including empty results) are not cached. Streamlit returns copies
    so downstream edits cannot corrupt cached results. Cache is shared by users.
    """
    return fetch_pitcher_statcast(pitcher_id, start_date, end_date)


def get_pitcher_statcast(pitcher_id: int | str, start_date: date, end_date: date) -> pd.DataFrame:
    """Validate before cache lookup and use normalized request keys."""
    return _cached_pitcher_statcast(*validate_request(pitcher_id, start_date, end_date))
