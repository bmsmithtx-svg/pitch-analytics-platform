"""Local OBU adapter: no MLB retrieval, coordinate conversion or inferred outcomes."""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from html import escape
from io import StringIO
from pathlib import Path
import re

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from obu_data import COLUMNS, NUMERIC_FIELDS, OBUDataError, validate_dataset
from pitch_arsenal import aggregate_pitch_arsenal
from pitch_plots import pitch_colors, style_chart

DATA_PATH = Path(__file__).resolve().parent / 'data' / 'obu_pitching_cleaned.csv'
SOURCE = 'OBU (Oklahoma Baptist University) · data/obu_pitching_cleaned.csv'
METHODS = (
    'One cleaned CSV observation counts as one pitch observation. Usage = type count / '
    'all classified observations × 100; unclassified observations are reported separately. '
    'Means and maxima use available measurements only; valid counts are their denominators. '
    'Velocity is release speed in mph. Spin and break retain source units and signs: '
    'units and coordinate conventions are unverified, with no Statcast equivalence or conversion. '
    'Break table means use independent samples; the break chart uses only paired measurements. '
    'Missing values remain unavailable, never zero. Small samples do not establish stable trends.'
)
LIMITATIONS = (
    'Pitch dates are unavailable; all available observations are used without date filtering. '
    'Statcast movement, pitch location, release-point, whiff-rate and strikeout analysis are unavailable. '
    'Source event labels are not interpreted as verified outcomes. '
    'The 7 tagged/automatic classification disagreements and 78 documented PDF discrepancies '
    'are retained without correction; no PDF observations are added.'
)
MEASUREMENTS = {
    'obu_release_speed_mph': 'Velocity (mph)',
    'obu_spin_rate_source': 'Spin (source units; unverified)',
    'obu_horizontal_break_source': 'Horizontal break (source units; unverified)',
    'obu_vertical_break_source': 'Vertical break (source units; unverified)',
    'obu_induced_vertical_break_source': 'Induced vertical break (source units; unverified)',
}


@st.cache_data(max_entries=4, show_spinner=False)
def _parse_dataset(content: bytes) -> pd.DataFrame:
    """Cache by exact file contents so changed/missing files never reuse stale data.

    Read text first and use Python float parsing to round-trip original numeric
    representations. Reuse the complete milestone 3.3 schema/provenance validator.
    Reject invalid cells instead of silently coercing or dropping observations.
    """
    try:
        data = pd.read_csv(StringIO(content.decode('utf-8')), dtype='string')
        if tuple(data.columns) != COLUMNS or data.empty:
            raise OBUDataError('OBU dataset is empty or has an invalid schema.')
        for column in (*NUMERIC_FIELDS.values(), 'source_record', 'duplicate_of_record'):
            data[column] = data[column].map(lambda v: float(v) if pd.notna(v) else float('nan'))
        # The provenance identifier uses integer source record formatting.
        data['source_record'] = data.source_record.astype('Int64')
        data['duplicate_of_record'] = data.duplicate_of_record.astype('Int64')
        validate_dataset(data)
        return data
    except (ValueError, TypeError, UnicodeError, OverflowError) as exc:
        raise OBUDataError('OBU dataset is malformed or fails schema/provenance validation.') from exc


def load_obu_dataset(path: Path = DATA_PATH) -> tuple[pd.DataFrame, str]:
    """Load only the cleaned local CSV; return its content digest for provenance."""
    try:
        content = path.read_bytes()
    except OSError as exc:
        raise OBUDataError('OBU dataset is unavailable. Restore data/obu_pitching_cleaned.csv.') from exc
    return _parse_dataset(content), sha256(content).hexdigest()


def display_name(name: str) -> str:
    """Present source 'surname, given' names without changing identity associations."""
    parts = name.split(',', 1)
    return f'{parts[1].strip()} {parts[0].strip()}' if len(parts) == 2 else name


def pitcher_options(data: pd.DataFrame) -> dict[str, str]:
    """Dataset-derived identities, sorted by display name; no MLB IDs."""
    pairs = data[['pitcher_id', 'pitcher_name']].drop_duplicates()
    return dict(sorted(((row.pitcher_id, display_name(row.pitcher_name))
                        for row in pairs.itertuples()), key=lambda pair: pair[1]))


def filter_pitcher(data: pd.DataFrame, pitcher_id: str) -> pd.DataFrame:
    """Exact source identity match, all observations in original order."""
    rows = data.loc[data.pitcher_id.eq(pitcher_id)].copy()
    if rows.empty:
        raise OBUDataError('No OBU observations available for the selected pitcher.')
    return rows


def arsenal_summary(rows: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    """Reuse classified counts/usage and mph summaries only where semantics match.

    OBU Fastball remains Fastball, never relabeled as Statcast four-seam. No spin
    or break is mapped to Statcast rpm/pfx fields. Additional means use independent
    nonmissing samples in source units, with explicit per-type valid counts.
    Unclassified measurements appear in overall coverage and charts, not usage.
    """
    compatible = rows[['pitch_type', 'obu_release_speed_mph']].rename(
        columns={'obu_release_speed_mph': 'release_speed'})
    result = aggregate_pitch_arsenal(compatible)
    metrics = result.metrics[['pitch_type', 'pitch_count', 'usage_pct',
                              'avg_release_speed_mph', 'max_release_speed_mph']].copy()
    metrics = metrics.rename(columns={'pitch_type': 'Pitch type', 'pitch_count': 'Pitch count',
        'usage_pct': 'Usage (%)', 'avg_release_speed_mph': 'Mean velocity (mph)',
        'max_release_speed_mph': 'Max velocity (mph)'})
    grouped = rows.groupby('pitch_type')
    for column, label in MEASUREMENTS.items():
        if column != 'obu_release_speed_mph':
            metrics[f'Mean {label}'] = metrics['Pitch type'].map(grouped[column].mean())
        metrics[f'Valid {label} (count)'] = metrics['Pitch type'].map(grouped[column].count())
    return metrics, result.unclassified_pitch_count


def coverage_table(rows: pd.DataFrame) -> pd.DataFrame:
    """All rows including unclassified; each field has its own valid denominator."""
    return pd.DataFrame([{'Measurement': label, 'Valid observations': int(rows[column].count()),
                          'Total observations': len(rows)}
                         for column, label in MEASUREMENTS.items()])


def measurement_chart(rows: pd.DataFrame, field: str | None) -> go.Figure:
    """Individual observed values, or paired source horizontal/induced break.

    No unit conversion, coordinate mirroring, reference zone or imputation.
    Unclassified observations retain usable measurements as an explicit group.
    """
    if field is not None and field not in MEASUREMENTS:
        raise ValueError('Unsupported OBU measurement.')
    labels = rows.pitch_type.fillna('Unclassified')
    colors = pitch_colors(labels.unique().tolist())
    fig = go.Figure()
    required = [field] if field else ['obu_horizontal_break_source', 'obu_induced_vertical_break_source']
    valid = rows.dropna(subset=required)
    for code in sorted(labels.unique()):
        group = valid.loc[labels.loc[valid.index].eq(code)]
        if group.empty:
            continue
        fig.add_trace(go.Scatter(
            x=[code] * len(group) if field else group[required[0]].tolist(),
            y=group[field].tolist() if field else group[required[1]].tolist(),
            mode='markers', name=f'{code} (n={len(group)})',
            marker=dict(color=colors[code], size=8, opacity=0.65),
        ))
    style_chart(fig)
    fig.update_layout(xaxis_title='Pitch type' if field else MEASUREMENTS[required[0]],
                      yaxis_title=MEASUREMENTS[field] if field else MEASUREMENTS[required[1]],
                      height=480)
    if valid.empty:
        fig.add_annotation(text='No available measurements in this selection.',
                           x=.5, y=.5, xref='paper', yref='paper', showarrow=False)
    return fig


@dataclass(frozen=True)
class OBUReport:
    pitcher_id: str
    pitcher_name: str
    dataset_digest: str
    total: int
    unclassified: int
    arsenal: pd.DataFrame
    coverage: pd.DataFrame
    observations: tuple[str, ...]


def build_obu_report(rows: pd.DataFrame, pitcher_id: str, digest: str) -> OBUReport:
    """Deterministic descriptive report; never applies MLB effectiveness heuristics."""
    rows = filter_pitcher(rows, pitcher_id)
    metrics, unclassified = arsenal_summary(rows)
    notes = tuple(f'{r["Pitch type"]}: {r["Pitch count"]} observations '
                  f'({r["Usage (%)"]:.1f}% of classified observations).'
                  for r in metrics.to_dict('records'))
    return OBUReport(pitcher_id, display_name(rows.pitcher_name.iloc[0]), digest,
                     len(rows), unclassified, metrics, coverage_table(rows), notes)


def export_obu_report(report: OBUReport, generated_at: datetime) -> str:
    """Escape every source string; export the same metrics/coverage as the preview."""
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError('Report timestamp must include a timezone.')
    observations = ''.join(f'<li>{escape(note)}</li>' for note in report.observations)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>OBU scouting report — {escape(report.pitcher_name)}</title>
<style>body{{font-family:system-ui,sans-serif;margin:2rem;color:#17212b}}
table{{border-collapse:collapse;font-size:.8rem}}td,th{{padding:.4rem;border:1px solid #aaa}}
.table-wrap{{overflow-x:auto}}@media print{{body{{margin:0}}@page{{size:landscape;margin:12mm}}}}</style>
</head><body><h1>OBU pitcher scouting report</h1>
<p>{escape(report.pitcher_name)} · {escape(report.pitcher_id)}</p>
<p>Source: {escape(SOURCE)}</p><p>Dataset SHA-256: {escape(report.dataset_digest)}</p>
<p>Generated: {escape(generated_at.isoformat())}</p>
<p>{report.total} observations; {report.unclassified} unclassified (excluded from usage).</p>
<h2>Arsenal summary</h2><div class="table-wrap">{report.arsenal.to_html(index=False, escape=True, na_rep='N/A', float_format=lambda v: f'{v:.2f}')}</div>
<h2>Measurement coverage (including unclassified)</h2>{report.coverage.to_html(index=False, escape=True)}
<h2>Descriptive observations</h2><ul>{observations}</ul>
<h2>Definitions and limitations</h2><p>{escape(METHODS)}</p><p>{escape(LIMITATIONS)}</p>
</body></html>'''


def obu_report_filename(report: OBUReport) -> str:
    """Bounded ASCII filename with source, name and dataset version; no invented dates."""
    slug = re.sub(r'[^a-z0-9]+', '-', report.pitcher_name.lower()).strip('-')[:64] or 'pitcher'
    return f'scouting-report-obu-{slug}-{report.dataset_digest[:12]}.html'
