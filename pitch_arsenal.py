"""Pure scouting summaries of validated Baseball Savant Statcast pitch rows."""

from dataclasses import dataclass
from numbers import Real

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class PitchArsenalResult:
    """Per-type metrics and the number of rows excluded from their denominator."""

    metrics: pd.DataFrame
    unclassified_pitch_count: int


def _finite_measurement(value: object) -> float:
    """Accept real numbers/numeric strings; treat other scalars as missing."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (Real, str)):
        return float("nan")
    try:
        number = float(value)
    except (ValueError, TypeError, OverflowError):
        return float("nan")
    return number if np.isfinite(number) else float("nan")


def aggregate_pitch_arsenal(data: pd.DataFrame) -> PitchArsenalResult:
    """Summarize rows without mutation, I/O, deduplication or game-type filters.

    Source: existing validated Baseball Savant/pybaseball Statcast rows. Each
    row counts as one pitch. A valid classification is a nonblank string;
    surrounding whitespace is stripped, case is preserved, and no fixed code
    whitelist is imposed. Null, blank and non-string types are unclassified.
    A missing pitch_type column makes every row unclassified.

    pitch_count includes every classified row regardless of measurement coverage.
    usage_pct = 100 * pitch_count / all classified rows (unrounded). Types sort
    by descending count then ascending code. Unclassified rows are counted
    separately and excluded from all metrics and the usage denominator.

    avg_release_speed_mph/max_release_speed_mph use release_speed (mph);
    avg_spin_rate_rpm uses optional release_spin_rate (rpm). avg_pfx_x_inches
    and avg_pfx_z_inches use pfx_x/pfx_z (feet) multiplied by 12, preserving
    Statcast's signs and coordinate frame; no arm-side or gravity adjustment
    is applied. These are direct movement summaries, not total break metrics.

    Each mean uses its own finite measurement count. Missing columns, malformed
    values, Booleans, and nonfinite values are ignored, never zero-filled. A
    metric with no usable measurements is NaN, including the velocity maximum.
    Empty/all-unclassified inputs return the same typed schema with no rows.
    Duplicate columns reject the input with ValueError rather than guessing.
    This defensive normalization does not replace upstream response validation.
    """
    if not isinstance(data, pd.DataFrame):
        raise TypeError("Pitch arsenal input must be a DataFrame.")
    if not data.columns.is_unique:
        raise ValueError("Pitch arsenal input must have unique column names.")

    types = data.get("pitch_type", pd.Series(index=data.index, dtype=object))
    types = types.map(lambda value: value.strip() if isinstance(value, str) else "")
    classified = types.ne("")
    unclassified = int((~classified).sum())
    rows = pd.DataFrame({"pitch_type": types[classified].to_numpy()})
    measurements = {
        "release_speed": ("avg_release_speed_mph", 1),
        "release_spin_rate": ("avg_spin_rate_rpm", 1),
        "pfx_x": ("avg_pfx_x_inches", 12),
        "pfx_z": ("avg_pfx_z_inches", 12),
    }
    for source, (target, scale) in measurements.items():
        values = data.get(source, pd.Series(index=data.index, dtype=float))
        numbers = values[classified].map(_finite_measurement).to_numpy(dtype=float)
        with np.errstate(over="ignore", invalid="ignore"):
            numbers = numbers * scale
        rows[target] = np.where(np.isfinite(numbers), numbers, np.nan)

    grouped = rows.groupby("pitch_type", sort=True)
    metrics = grouped.size().rename("pitch_count").to_frame()
    metrics["usage_pct"] = metrics["pitch_count"] / len(rows) * 100 if len(rows) else np.nan
    for target, _ in measurements.values():
        # Scaling before summation avoids overflow for large finite inputs.
        metrics[target] = grouped[target].agg(
            lambda values: (values.dropna() / values.count()).sum()
            if values.count() else np.nan
        )
    metrics.insert(4, "max_release_speed_mph", grouped["avg_release_speed_mph"].max())
    metrics = metrics.reset_index().sort_values(
        ["pitch_count", "pitch_type"], ascending=[False, True], ignore_index=True
    )
    return PitchArsenalResult(metrics, unclassified)
