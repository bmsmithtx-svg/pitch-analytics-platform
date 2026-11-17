"""Input and response contracts for unaggregated Baseball Savant pitch records."""

from datetime import date, datetime
import re

import pandas as pd

MAX_WINDOW_DAYS = 30
# Identity/context columns plus the measurements needed by future pitch displays.
# release_speed is mph; pfx_x/pfx_z are feet. No statistics are calculated here.
REQUIRED_COLUMNS = ("game_date", "pitcher", "pitch_type", "release_speed", "pfx_x", "pfx_z")


class StatcastError(Exception):
    """User-facing failure in the Statcast pipeline."""


class InputValidationError(StatcastError):
    """Invalid request; no upstream call should be made."""


class ResponseValidationError(StatcastError):
    """Upstream returned an unusable response."""


class NoStatcastDataError(StatcastError):
    """No rows were returned; deliberately not cached."""


def validate_request(
    pitcher_id: int | str, start_date: date, end_date: date
) -> tuple[int, date, date]:
    """Normalize a positive MLBAM ID and enforce at most 30 inclusive dates.

    ID syntax is checked, not player existence. Dates must be date objects (not
    datetimes); future dates are allowed and may legitimately return no data.
    """
    if isinstance(pitcher_id, bool) or not isinstance(pitcher_id, (str, int)):
        raise InputValidationError("Pitcher ID must be a positive MLBAM integer.")
    value = str(pitcher_id).strip()
    if not re.fullmatch(r"[0-9]{1,10}", value) or int(value) <= 0:
        raise InputValidationError("Pitcher ID must be a positive MLBAM integer (up to 10 digits).")
    if any(not isinstance(d, date) or isinstance(d, datetime) for d in (start_date, end_date)):
        raise InputValidationError("Select both a start date and an end date.")
    if end_date < start_date:
        raise InputValidationError("End date must be on or after start date.")
    if (end_date - start_date).days + 1 > MAX_WINDOW_DAYS:
        raise InputValidationError("Select at most 30 calendar days, including both endpoints.")
    return int(value), start_date, end_date


def validate_response(
    response: object, pitcher_id: int, start_date: date, end_date: date
) -> pd.DataFrame:
    """Validate identity, date scope and schema without inventing or dropping rows.

    Missing measurement/type values remain missing, never zero-filled. Numeric
    measurement columns are normalized to nullable numbers; nonnumeric non-null
    values are rejected. Extra columns and upstream row order are preserved.
    Missing identity/date values, duplicate columns, or out-of-scope rows reject
    the whole response rather than silently changing its meaning.
    """
    if not isinstance(response, pd.DataFrame):
        raise ResponseValidationError("Statcast returned a malformed response; expected a table.")
    if response.empty:
        raise NoStatcastDataError("No Statcast records found for this pitcher and date range.")
    if not response.columns.is_unique:
        raise ResponseValidationError("Statcast returned duplicate column names.")
    missing = set(REQUIRED_COLUMNS) - set(response.columns)
    if missing:
        raise ResponseValidationError("Statcast response is missing required columns: " + ", ".join(sorted(missing)))
    data = response.copy()
    try:
        dates = pd.to_datetime(data["game_date"], errors="raise")
        ids = pd.to_numeric(data["pitcher"], errors="raise")
        if dates.isna().any() or ids.isna().any():
            raise ValueError("Missing identity")
        if not ids.eq(pitcher_id).all() or not dates.dt.date.between(start_date, end_date).all():
            raise ValueError("Outside request scope")
        data["game_date"] = dates
        data["pitcher"] = ids.astype("Int64")
        for column in ("release_speed", "pfx_x", "pfx_z"):
            numbers = pd.to_numeric(data[column], errors="raise").astype("Float64")
            if numbers.isin([float("inf"), -float("inf")]).any():
                raise ValueError("Nonfinite measurement")
            data[column] = numbers
    except (ValueError, TypeError, OverflowError, AttributeError) as exc:
        raise ResponseValidationError("Statcast returned invalid values or rows outside the requested pitcher/date range.") from exc
    return data
