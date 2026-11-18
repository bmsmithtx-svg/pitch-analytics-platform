"""Plotly charts for prepared Statcast summaries; no retrieval."""

import pandas as pd
import plotly.graph_objects as go
from plotly.colors import qualitative

from pitch_movement import StrikeZone


def pitch_usage_chart(metrics: pd.DataFrame, colors: dict[str, str] | None = None) -> go.Figure:
    """Display the existing arsenal counts and unrounded usage, without mutation.

    Source: aggregate_pitch_arsenal over loaded Statcast rows. Usage (%) is
    100 * type count / classified row count; unclassified rows are excluded.
    Missing measurements do not affect counts. No classification substitution,
    filtering, or recalculation is performed here. Display rounds to one decimal.
    An optional full-dataset color map keeps unclassified coordinate groups from
    shifting classified colors between charts. Empty aggregates show an annotation rather than dividing by zero.
    """
    ordered = metrics.sort_values(
        ["usage_pct", "pitch_type"], ascending=[False, True]
    )
    fig = go.Figure()
    if ordered.empty:
        fig.add_annotation(text="No classified pitches available for pitch usage.",
                           x=0.5, y=0.5, xref="paper", yref="paper", showarrow=False)
    else:
        colors = colors if colors is not None else pitch_colors(ordered.pitch_type.tolist())
        fig.add_trace(go.Bar(
            x=ordered.usage_pct.tolist(), y=ordered.pitch_type.tolist(), orientation="h",
            marker_color=[colors[code] for code in ordered.pitch_type],
            customdata=ordered[["pitch_count"]].values.tolist(),
            text=[f"{row.pitch_count:,} {'pitch' if row.pitch_count == 1 else 'pitches'} · {row.usage_pct:.1f}%"
                  for row in ordered.itertuples()],
            textposition="auto", cliponaxis=False,
            hovertemplate="Pitch type: %{y}<br>Pitch count: %{customdata[0]:,d}"
                          "<br>Usage: %{x:.1f}%<extra></extra>",
        ))
    style_chart(fig)
    fig.update_layout(
        xaxis_title="Classified pitch usage (%)", yaxis_title="Pitch type",
        height=max(320, 52 * len(ordered) + 120), showlegend=False,
        margin=dict(l=20, r=30, t=30, b=60),
    )
    fig.update_xaxes(range=[0, 100], ticksuffix="%")
    fig.update_yaxes(categoryorder="array", categoryarray=ordered.pitch_type.tolist(),
                     autorange="reversed", automargin=True)
    return fig


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
                hovertemplate="Pitch type: %{text}<br>Horizontal: %{x:.1f} in<br>Induced vertical: %{y:.1f} in<br>Paired pitches: %{customdata}<extra></extra>",
            ))
    style_chart(fig)
    fig.update_layout(xaxis_title="Horizontal movement (in)",
                      yaxis_title="Induced vertical movement (in)",
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
            text=[code] * len(group),
            hovertemplate="Pitch type: %{text}<br>Horizontal: %{x:.2f} ft<br>Vertical: %{y:.2f} ft<extra></extra>",
        ))
    fig.add_shape(type="rect", x0=zone.left, x1=zone.right, y0=zone.bottom, y1=zone.top,
                  line=dict(color="#808080", width=3, dash="dash"),
                  name=zone.label, showlegend=True)
    style_chart(fig)
    fig.update_layout(xaxis_title="Horizontal plate location (ft)",
                      yaxis_title="Vertical plate location (ft)",
                      legend_title_text="Pitch type / reference", height=480)
    fig.update_yaxes(scaleanchor="x", scaleratio=1)
    return fig


def style_chart(fig: go.Figure) -> None:
    """Apply shared presentation only; preserve observations and axis geometry."""
    fig.update_layout(
        font=dict(size=14), hoverlabel=dict(font_size=14),
        margin=dict(l=20, r=20, t=30, b=60),
        legend=dict(orientation="h", yanchor="top", y=-0.2, x=0),
    )
    fig.update_xaxes(automargin=True)
    fig.update_yaxes(automargin=True)
