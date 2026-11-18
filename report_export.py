"""Self-contained, escaped HTML export; formatting has no analytical side effects."""
from datetime import datetime
from html import escape

import pandas as pd

from scouting_report import METHODS, SOURCE, ScoutingReport


def report_table(report: ScoutingReport) -> pd.DataFrame:
    """Readable units in headings; preserve underlying metric precision in model."""
    labels = {
        "pitch_type": "Pitch type", "pitch_count": "Pitch count", "usage_pct": "Usage (%)",
        "avg_release_speed_mph": "Mean velocity (mph)",
        "max_release_speed_mph": "Max velocity (mph)",
        "min_release_speed_mph": "Min velocity (mph)",
        "avg_spin_rate_rpm": "Mean spin (rpm)",
        "avg_pfx_x_inches": "Mean horizontal movement (in)",
        "avg_pfx_z_inches": "Mean induced vertical movement (in)",
        "whiff_pct": "Whiff (%)", "swings": "Swings", "misses": "Misses",
    }
    labels.update({f"avg_release_pos_{axis}_ft": f"Mean release {axis} (ft)" for axis in "xyz"})
    labels.update({column: f"Valid {column.removeprefix('valid_')} (count)"
                   for column in report.arsenal if column.startswith("valid_")})
    table = report.arsenal.rename(columns=labels).copy()
    for column in table:
        if column != "Pitch type":
            table[column] = table[column].map(
                lambda value: "N/A" if pd.isna(value) else
                (str(int(value)) if column.endswith("(count)") or column in
                 ("Pitch count", "Swings", "Misses") else f"{value:.2f}"))
    # Metrics down the page keep the full coverage table readable when printed.
    table["Pitch type"] = table["Pitch type"].map(lambda code: f"Pitch type: {code}")
    return table.set_index("Pitch type").T.rename_axis("Metric").reset_index()


def export_report_html(report: ScoutingReport, generated_at: datetime) -> str:
    """Timestamp must include timezone; callers control it independently of statistics."""
    if generated_at.tzinfo is None or generated_at.utcoffset() is None:
        raise ValueError("Report timestamp must include a timezone.")
    def items(values):
        return "<ul>" + "".join(f"<li>{escape(value)}</li>" for value in values) + "</ul>"
    name = escape(report.pitcher_name or "Name unavailable")
    table = report_table(report).to_html(index=False, na_rep="N/A", escape=True,
                                         float_format=lambda value: f"{value:.2f}")
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>Pitcher scouting report — {report.pitcher_id}</title>
<style>body{{font-family:system-ui,sans-serif;margin:2rem;color:#17212b}}
table{{border-collapse:collapse;font-size:.8rem}}th,td{{padding:.4rem;border:1px solid #aaa}}
th{{text-align:left}}@media print{{body{{margin:0}}thead{{display:table-header-group}}
@page{{size:landscape;margin:12mm}}}} </style></head><body>
<h1>Pitcher scouting report</h1><p>{name} · MLBAM {report.pitcher_id}</p>
<p>Analysis period: {report.start_date} through {report.end_date} (inclusive)</p>
<p>Generated: {escape(generated_at.isoformat())}</p>
<p>Total pitches analyzed: {report.total_pitches}; unclassified: {report.unclassified_pitches}</p>
<h2>Arsenal summary</h2>{table}<h2>Automated scouting observations</h2>
{items(report.observations)}<h2>Sample size and data quality</h2>{items(report.notes)}
<h2>Definitions and interpretation</h2><p>{escape(METHODS)}</p>
<p>Source: {escape(SOURCE)}</p></body></html>'''
