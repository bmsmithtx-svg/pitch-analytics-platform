"""Deterministic descriptive reports from already validated Statcast rows.

No retrieval, deduplication, additional filtering, grades or prediction. Request
identity/date validation belongs to statcast_validation; callers supply the
validated rows for that request. Optional measurements are normalized with the
same finite-scalar policy as the existing arsenal; coverage exposes exclusions.
"""
from dataclasses import dataclass
from datetime import date

import numpy as np
import pandas as pd

from pitch_arsenal import aggregate_pitch_arsenal, _finite_measurement
from statcast_validation import validate_request

MIN_VELOCITY_SAMPLE = 20
SWINGS = frozenset({"swinging_strike", "swinging_strike_blocked", "foul_tip",
                    "foul", "hit_into_play", "foul_bunt", "missed_bunt", "bunt_foul_tip"})
MISSES = frozenset({"swinging_strike", "swinging_strike_blocked", "missed_bunt"})
SOURCE = "Baseball Savant Statcast via pybaseball; loaded request rows."
METHODS = (
    "Each row counts as one pitch; no deduplication or additional game-type filtering. "
    "Usage = type count / all classified rows × 100; unclassified rows are excluded. "
    "Source codes are whitespace-stripped and case-preserved, including unknown codes. "
    "Means and velocity extrema use independently available finite measurements. "
    "Movement is signed pfx_x/pfx_z × 12 inches; vertical movement is induced, not total break. "
    "Release positions retain source coordinates in feet. Whiff (%) = misses / recognized swings × 100. "
    "Recognized swing descriptions: " + ", ".join(sorted(SWINGS)) + ". "
    "Misses: " + ", ".join(sorted(MISSES)) + ". Foul tips count as swings, not misses. "
    "Unknown/missing descriptions are excluded from swing denominators; zero swings yields N/A. "
    "N/A means unavailable, never zero-filled. Coverage counts include only classified rows. "
    "Velocity comparisons require 20 valid speeds per type, an operational caution threshold, "
    "not a statistical significance test. Observations describe this sample, not grades, "
    "pitch effectiveness or predictive assessments. Coverage does not establish source completeness."
)


@dataclass(frozen=True)
class ScoutingReport:
    pitcher_id: int
    pitcher_name: str | None
    start_date: date
    end_date: date
    total_pitches: int
    unclassified_pitches: int
    arsenal: pd.DataFrame
    observations: tuple[str, ...]
    notes: tuple[str, ...]


def scouting_observations(arsenal: pd.DataFrame) -> tuple[str, ...]:
    """Describe observed usage; compare velocity only at the documented threshold."""
    if arsenal.empty:
        return ("No classified pitches available; no arsenal observations can be made.",)
    primary = arsenal.iloc[0]
    observations = [
        f"Observed arsenal: {len(arsenal)} classified pitch type(s).",
        f"Highest observed usage: {primary.pitch_type}, {primary.usage_pct:.1f}% "
        f"({primary.pitch_count} classified pitches); ties ordered by source code.",
    ]
    if len(arsenal) > 1:
        secondary = arsenal.iloc[1]
        observations.append(f"Next in usage: {secondary.pitch_type}, {secondary.usage_pct:.1f}% "
                            f"({secondary.pitch_count} pitches).")
    supported = arsenal[arsenal.valid_release_speed >= MIN_VELOCITY_SAMPLE]
    if len(supported) > 1:
        ordered = supported.sort_values(["avg_release_speed_mph", "pitch_type"])
        slow, fast = ordered.iloc[0], ordered.iloc[-1]
        gap = fast.avg_release_speed_mph - slow.avg_release_speed_mph
        if np.isfinite(gap):
            observations.append(f"Observed mean velocity separation: {fast.pitch_type} versus "
                                f"{slow.pitch_type}, {gap:.1f} mph "
                                f"(valid speeds: {fast.valid_release_speed}, {slow.valid_release_speed}).")
    else:
        observations.append("Small or incomplete velocity sample: no velocity comparison "
                            "(requires 20 valid speeds per type for at least two types).")
    return tuple(observations)


def build_scouting_report(data: pd.DataFrame, pitcher_id: int | str,
                          start_date: date, end_date: date) -> ScoutingReport:
    """Build from validated request data; keep timestamps out of analytical output.

    Existing arsenal metrics, ordering and denominators are reused verbatim.
    Additional min speed (mph), release means (ft), and coverage counts use
    independent finite values, including numeric strings and valid zero values.
    Missing columns, malformed scalars, booleans and infinities are unavailable;
    per-column notes count unavailable values across ALL rows. Duplicate columns
    reject via arsenal validation. No names are inferred: only a single unique
    nonblank player_name is shown; absent/ambiguous names are reported missing.
    """
    identity, start_date, end_date = validate_request(pitcher_id, start_date, end_date)
    base = aggregate_pitch_arsenal(data)
    arsenal = base.metrics.copy()
    for column in ("min_release_speed_mph", "avg_release_pos_x_ft",
                   "avg_release_pos_y_ft", "avg_release_pos_z_ft"):
        arsenal[column] = pd.Series(index=arsenal.index, dtype=float)
    types = data.get("pitch_type", pd.Series(index=data.index, dtype=object)).map(
        lambda x: x.strip() if isinstance(x, str) else "")
    notes = [f"Unclassified pitches: {base.unclassified_pitch_count} of {len(data)}."]
    sources = ("release_speed", "release_spin_rate", "pfx_x", "pfx_z",
               "release_pos_x", "release_pos_y", "release_pos_z")
    for source in sources:
        raw = data.get(source, pd.Series(index=data.index, dtype=float))
        numbers = raw.map(_finite_measurement).to_numpy(dtype=float)
        if source in ("pfx_x", "pfx_z"):
            with np.errstate(over="ignore", invalid="ignore"):
                numbers = numbers * 12
            numbers[~np.isfinite(numbers)] = np.nan
        notes.append(f"{source}: {int(np.isfinite(numbers).sum())}/{len(data)} usable; "
                     f"{int((~np.isfinite(numbers)).sum())} missing or invalid.")
        grouped = pd.DataFrame({"pitch_type": types.to_numpy(), "value": numbers})
        for code in arsenal.pitch_type:
            values = grouped.loc[grouped.pitch_type.eq(code), "value"].dropna()
            index = arsenal.index[arsenal.pitch_type.eq(code)][0]
            arsenal.loc[index, f"valid_{source}"] = len(values)
            if source == "release_speed":
                arsenal.loc[index, "min_release_speed_mph"] = values.min()
            elif source.startswith("release_pos_"):
                arsenal.loc[index, f"avg_{source}_ft"] = (
                    (values / len(values)).sum() if len(values) else np.nan)
        if f"valid_{source}" not in arsenal:
            arsenal[f"valid_{source}"] = pd.Series(dtype=int)
        arsenal[f"valid_{source}"] = arsenal[f"valid_{source}"].astype(int)
    descriptions = data.get("description", pd.Series(index=data.index, dtype=object)).map(
        lambda x: x.strip() if isinstance(x, str) else "")
    notes.append(f"Recognized swing descriptions: {int(descriptions.isin(SWINGS).sum())}/{len(data)}. "
                 "Other descriptions may be takes, missing or unknown; excluded from swing denominator.")
    for column in ("swings", "misses", "whiff_pct"):
        arsenal[column] = pd.Series(index=arsenal.index, dtype=float)
    for index, code in arsenal.pitch_type.items():
        selected = descriptions[types.eq(code)]
        swings, misses = int(selected.isin(SWINGS).sum()), int(selected.isin(MISSES).sum())
        arsenal.loc[index, ["swings", "misses", "whiff_pct"]] = (
            swings, misses, 100 * misses / swings if swings else np.nan)
    for column in ("swings", "misses"):
        arsenal[column] = arsenal[column].astype(int)
    names = data.get("player_name", pd.Series(dtype=object)).dropna()
    names = sorted({name.strip() for name in names if isinstance(name, str) and name.strip()})
    name = names[0] if len(names) == 1 else None
    if name is None:
        notes.append("Pitcher name unavailable or ambiguous in source rows; identified by MLBAM ID.")
    if data.empty:
        notes.append("No returned records; this does not establish zero pitches thrown.")
    notes.append("Small samples may not represent stable tendencies. Missing/invalid optional values "
                 "are excluded independently; upstream required-field validation remains unchanged.")
    return ScoutingReport(identity, name, start_date, end_date, len(data),
                          base.unclassified_pitch_count, arsenal,
                          scouting_observations(arsenal), tuple(notes))
