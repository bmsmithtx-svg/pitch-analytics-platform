"""Pure movement/location analytics over the existing Statcast rows.

Source: Baseball Savant CSV, https://baseballsavant.mlb.com/csv-docs.
No I/O, deduplication, game filters, handedness transforms or zero filling.
Classification and scalar validity follow the Milestone 1.3 arsenal conventions.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from pitch_arsenal import _finite_measurement


def prepare_pitch_coordinates(data: pd.DataFrame) -> pd.DataFrame:
    """Copy all rows; strip string type codes, label unclassified rows explicitly.

    Numeric strings are accepted; malformed, Boolean, null and nonfinite values
    become NaN independently per field. Missing columns are entirely missing.
    pfx_x/pfx_z (feet) become signed inches. pfx_z is gravity-adjusted induced
    movement, not total displacement. Catcher's coordinates are retained:
    positive x is right, negative left; positive z is up. No arm/glove labels.
    plate_x/plate_z and sz_bot/sz_top remain feet. Overflow on conversion is missing.
    """
    if not isinstance(data, pd.DataFrame):
        raise TypeError("Pitch coordinates input must be a DataFrame.")
    if not data.columns.is_unique:
        raise ValueError("Pitch coordinates input must have unique column names.")
    rows = pd.DataFrame(index=range(len(data)))
    types = data.get("pitch_type", pd.Series(index=data.index, dtype=object))
    rows["pitch_type"] = types.map(
        lambda v: v.strip() if isinstance(v, str) and v.strip() else "Unclassified"
    ).to_numpy()
    for column in ("pfx_x", "pfx_z", "plate_x", "plate_z", "sz_bot", "sz_top"):
        values = data.get(column, pd.Series(index=data.index, dtype=float))
        numbers = values.map(_finite_measurement).to_numpy(dtype=float)
        with np.errstate(over="ignore", invalid="ignore"):
            numbers = numbers * (12 if column.startswith("pfx_") else 1)
        rows[column] = np.where(np.isfinite(numbers), numbers, np.nan)
    return rows


def filter_pitch_types(rows: pd.DataFrame, selected: list[str]) -> pd.DataFrame:
    """Filter prepared rows locally; empty selection returns no observations."""
    return rows.loc[rows["pitch_type"].isin(selected)].copy()


def _mean(values: pd.Series) -> float:
    """Arithmetic mean with its own valid denominator; empty is explicitly NaN."""
    valid = values.dropna()
    return float((valid / len(valid)).sum()) if len(valid) else float("nan")


def movement_summary(rows: pd.DataFrame) -> pd.DataFrame:
    """Summarize prepared rows by code (including explicit Unclassified group).

    Independent finite x/z samples define table means; chart means use ONLY
    rows with BOTH coordinates. Counts are observations, not unique events.
    No rounding; zero and negative values remain valid. No empty-group means.
    """
    records = []
    for pitch_type, group in rows.groupby("pitch_type", sort=True):
        paired = group.dropna(subset=["pfx_x", "pfx_z"])
        records.append((pitch_type, _mean(group.pfx_x), _mean(group.pfx_z),
                        int(group.pfx_x.count()), int(group.pfx_z.count()), len(paired),
                        _mean(paired.pfx_x), _mean(paired.pfx_z)))
    return pd.DataFrame(records, columns=[
        "pitch_type", "avg_horizontal_inches", "avg_induced_vertical_inches",
        "valid_horizontal", "valid_vertical", "valid_paired",
        "paired_horizontal_inches", "paired_vertical_inches",
    ])


def valid_locations(rows: pd.DataFrame) -> pd.DataFrame:
    """Use every prepared row with both plate coordinates, unchanged in feet."""
    return rows.dropna(subset=["plate_x", "plate_z"]).copy()


@dataclass(frozen=True)
class StrikeZone:
    """Representative rectangle in feet; horizontal width is physical 17 inches."""

    bottom: float
    top: float
    label: str
    count: int
    left: float = -17 / 24
    right: float = 17 / 24


def strike_zone_reference(rows: pd.DataFrame) -> StrikeZone:
    """Medians of same-row valid 0 < bottom < top boundaries in selected sample.

    Uses all selected rows, independently of location/movement availability.
    If no valid boundary pairs exist, use a labeled generic 1.5–3.5 ft zone.
    No baseball-radius expansion; this is not each batter's exact strike zone.
    """
    valid = rows.loc[(rows.sz_bot > 0) & (rows.sz_top > rows.sz_bot)]
    if valid.empty:
        return StrikeZone(1.5, 3.5, "Generic reference zone (1.5–3.5 ft)", 0)
    return StrikeZone(float(valid.sz_bot.median()), float(valid.sz_top.median()),
                      f"Sample median reference zone (n={len(valid)})", len(valid))
