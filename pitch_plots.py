"""Plotly charts for prepared Statcast coordinates; no retrieval or analytics."""

import pandas as pd
import plotly.graph_objects as go
from plotly.colors import qualitative

from pitch_movement import StrikeZone


def pitch_colors(types: list[str]) -> dict[str, str]:
    """Assign colors once from the full arsenal so filtering preserves colors."""
    return {code: qualitative.Safe[i % len(qualitative.Safe)] for i, code in enumerate(sorted(types))}


def pitch_symbols(colors: dict[str, str]) -> dict[str, str]:
    """Use the full arsenal color mapping, never the visible filtered subset.

    Each 11-color cycle gets a different SVG/WebGL-compatible symbol. The
    seven symbols repeat after 77 categories; names remain explicit in legends.
    """
    symbols = ("circle", "square", "diamond", "cross", "x", "triangle-up", "triangle-down")
    return {code: symbols[(i // len(qualitative.Safe)) % len(symbols)]
            for i, code in enumerate(sorted(colors))}


def movement_chart(summary: pd.DataFrame, colors: dict[str, str]) -> go.Figure:
    """Plot paired means only, in signed inches, with paired sample counts."""
    fig = go.Figure()
    symbols = pitch_symbols(colors)
    for row in summary.itertuples():
        if row.valid_paired:
            fig.add_trace(go.Scatter(
                x=[row.paired_horizontal_inches], y=[row.paired_vertical_inches],
                mode="markers+text", text=[row.pitch_type], textposition="top center",
                name=row.pitch_type,
                marker=dict(color=colors[row.pitch_type], symbol=symbols[row.pitch_type], size=13),
                customdata=[row.valid_paired],
                hovertemplate="%{text}<br>Horizontal: %{x:.1f} in<br>Induced vertical: %{y:.1f} in<br>Paired pitches: %{customdata}<extra></extra>",
            ))
    fig.update_layout(xaxis_title="Horizontal Movement (inches)",
                      yaxis_title="Induced Vertical Movement (inches)",
                      legend_title_text="Pitch type", height=480)
    fig.update_xaxes(zeroline=True, zerolinewidth=2)
    fig.update_yaxes(zeroline=True, zerolinewidth=2, scaleanchor="x", scaleratio=1)
    return fig


def location_chart(locations: pd.DataFrame, zone: StrikeZone,
                   colors: dict[str, str]) -> go.Figure:
    """Plot every valid location in feet, equal physical axis scaling, no mirror."""
    fig = go.Figure()
    symbols = pitch_symbols(colors)
    for code, group in locations.groupby("pitch_type", sort=True):
        fig.add_trace(go.Scattergl(
            x=group.plate_x.tolist(), y=group.plate_z.tolist(), mode="markers",
            name=f"{code} (n={len(group)})",
            marker=dict(color=colors[code], symbol=symbols[code], size=7, opacity=0.55),
            hovertemplate=code + "<br>Horizontal: %{x:.2f} ft<br>Vertical: %{y:.2f} ft<extra></extra>",
        ))
    fig.add_shape(type="rect", x0=zone.left, x1=zone.right, y0=zone.bottom, y1=zone.top,
                  line=dict(color="#808080", width=3, dash="dash"),
                  name=zone.label, showlegend=True)
    fig.update_layout(xaxis_title="Horizontal Plate Location (feet)",
                      yaxis_title="Vertical Plate Location (feet)",
                      legend_title_text="Pitch type / reference", height=480)
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    return fig
