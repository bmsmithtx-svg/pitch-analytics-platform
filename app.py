"""Streamlit entry point for the Pitch Analytics Platform."""

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import streamlit as st

from pitch_movement import (
    filter_pitch_types, movement_summary, prepare_pitch_coordinates,
    strike_zone_reference, valid_locations,
)
from pitch_plots import movement_chart, location_chart, pitch_colors, pitch_usage_chart
from pitch_arsenal import PitchArsenalResult, aggregate_pitch_arsenal
from scouting_report import build_scouting_report, METHODS, SOURCE
from report_export import export_report_html, report_table
from statcast_service import get_pitcher_statcast
from statcast_validation import NoStatcastDataError, StatcastError


def render_pitch_arsenal(result: PitchArsenalResult) -> None:
    """Present the existing aggregate without rounding or filling its data."""
    st.header("Pitch Arsenal")
    st.metric("Unclassified pitches", result.unclassified_pitch_count)
    st.caption(
        "Usage percentages are calculated only from classified pitches; "
        "unclassified pitches are excluded. Each retrieved row counts as one pitch."
    )
    if result.metrics.empty:
        st.info("No classified pitches available for an arsenal summary.")
        return
    st.dataframe(
        result.metrics,
        hide_index=True,
        alt="Pitch arsenal summary by classified Statcast pitch type",
        column_config={
            "pitch_type": "Pitch type",
            "pitch_count": st.column_config.NumberColumn("Pitch count", format="%,d"),
            "usage_pct": st.column_config.NumberColumn("Usage (%)", format="%.1f%%"),
            "avg_release_speed_mph": st.column_config.NumberColumn("Avg velocity (mph)", format="%.1f"),
            "max_release_speed_mph": st.column_config.NumberColumn("Max velocity (mph)", format="%.1f"),
            "avg_spin_rate_rpm": st.column_config.NumberColumn("Avg spin (rpm)", format="%.0f"),
            "avg_pfx_x_inches": st.column_config.NumberColumn("Avg horizontal movement (in)", format="%+.1f"),
            "avg_pfx_z_inches": st.column_config.NumberColumn("Avg vertical movement (in)", format="%+.1f"),
        },
    )
    st.caption(
        "Source: retrieved Baseball Savant Statcast records. Averages and maxima "
        "use available finite measurements; missing measurements remain missing, "
        "not zero. Movement is mean pfx_x/pfx_z converted from feet to inches, "
        "preserving Statcast signs and coordinates, without arm-side or gravity "
        "adjustment; these are not total break metrics."
    )


def render_movement_location(data: pd.DataFrame) -> None:
    """Filter already loaded rows; render each chart independently."""
    st.header("Pitch Movement & Location Analysis")
    rows = prepare_pitch_coordinates(data)
    options = sorted(rows.pitch_type.unique().tolist())
    selected = st.multiselect("Pitch types", options, default=options, key="analysis_pitch_types")
    rows = filter_pitch_types(rows, selected)
    if not selected:
        st.info("Select at least one pitch type to view movement and locations.")
        return
    colors = pitch_colors(options)
    summary = movement_summary(rows)
    locations = valid_locations(rows)
    movement, location = st.columns(2)
    with movement:
        st.subheader("Pitch movement")
        if summary.valid_paired.sum():
            st.plotly_chart(movement_chart(summary, colors), alt="Paired mean pitch movement by pitch type")
        else:
            st.info("No pitches have both movement measurements in this selection.")
    with location:
        st.subheader("Pitch location")
        if not locations.empty:
            zone = strike_zone_reference(rows)
            st.plotly_chart(location_chart(locations, zone, colors), alt="Pitch locations with representative strike zone")
            st.caption(f"{zone.label}. Physical 17-inch plate width; no ball-radius expansion.")
        else:
            st.info("No pitches have both plate location measurements in this selection.")
    if not summary.empty:
        st.dataframe(summary.drop(columns=["paired_horizontal_inches", "paired_vertical_inches"]),
                     hide_index=True, alt="Movement averages and valid observation counts",
                     column_config={
                         "pitch_type": "Pitch type",
                         "avg_horizontal_inches": st.column_config.NumberColumn("Avg horizontal movement (in)", format="%+.1f"),
                         "avg_induced_vertical_inches": st.column_config.NumberColumn("Avg induced vertical movement (in)", format="%+.1f"),
                         "valid_horizontal": "Valid horizontal pitches",
                         "valid_vertical": "Valid vertical pitches",
                         "valid_paired": "Valid paired pitches",
                     })
    if not (summary.valid_horizontal.sum() or summary.valid_vertical.sum()):
        st.info("No usable movement measurements in this selection.")
    st.caption(
        "Source: Baseball Savant Statcast. Movement is pfx_x/pfx_z × 12 inches. "
        "Induced vertical movement is gravity-adjusted, not total vertical displacement. "
        "Both charts retain catcher-view signs: positive horizontal is right, negative left; "
        "positive vertical is up. Locations remain in feet; no handedness mirroring. "
        "Table means use independent valid samples; chart centroids use paired samples and can differ. "
        "Missing/invalid measurements remain missing, not zero. Unclassified rows retain their valid measurements. "
        "The zone uses median top/bottom from valid boundary pairs in the selected sample, "
        "or a labeled generic 1.5–3.5 ft reference, not each batter's exact zone. "
        "Small samples, including single pitches, do not establish stable trends. "
        "Movement describes pitches; it is not a quality or effectiveness score."
    )


def render_scouting_report(
    data: pd.DataFrame, pitcher_id: str, start_date: date, end_date: date
) -> None:
    """Use the active loaded request; report is never stored as separate stale state."""
    report = build_scouting_report(data, pitcher_id, start_date, end_date)
    st.header("Pitcher scouting report")
    st.text(f"{report.pitcher_name or 'Name unavailable'} · MLBAM {report.pitcher_id}")
    st.text(f"{report.start_date} through {report.end_date} (inclusive); "
            f"{report.total_pitches:,} pitches analyzed")
    st.caption("Relevant movement, location and usage visualizations appear in the existing sections. "
               "The report uses all loaded rows, independently of the chart filter.")
    st.subheader("Arsenal summary")
    if report.arsenal.empty:
        st.info("No classified pitches available for this report.")
    else:
        st.table(report_table(report), alt="Scouting arsenal metrics and valid sample counts")
    st.subheader("Automated scouting observations")
    for observation in report.observations:
        st.text(observation)
    st.subheader("Sample size and data quality")
    for note in report.notes:
        st.text(note)
    st.caption(METHODS)
    st.caption(SOURCE)
    generated_at = st.session_state["report_generated_at"]
    st.caption(f"Report generated: {generated_at.isoformat()}")
    st.download_button("Download scouting report (HTML)",
                       export_report_html(report, generated_at),
                       file_name=f"scouting-report-{report.pitcher_id}-{start_date}-{end_date}.html",
                       mime="text/html", key="scouting_download")


def main() -> None:
    """Render the dashboard and retrieve data only after explicit submission."""
    st.set_page_config(
        page_title="Pitch Analytics Platform",
        page_icon="⚾",
        layout="wide",
    )

    with st.sidebar:
        st.header("Pitcher selection")
        with st.form("statcast_request"):
            pitcher_id = st.text_input("MLBAM pitcher ID", key="pitcher_id")
            start_date = st.date_input("Start date", value=date.today() - timedelta(days=29))
            end_date = st.date_input("End date", value=date.today())
            submitted = st.form_submit_button("Request data")
        st.caption("Maximum 30 days, including both endpoints. Data loads only on request.")

    st.title("Pitch Analytics Platform")
    st.write(
        "Professional MLB pitching analytics and scouting insights, "
        "powered by Statcast data."
    )
    st.header("Statcast data")
    arsenal = None
    if submitted:
        # Clear the previous result so a failed request cannot show stale rows.
        st.session_state.pop("analysis_pitch_types", None)
        st.session_state.pop("statcast_result", None)
        st.session_state.pop("report_generated_at", None)
        st.session_state.pop("statcast_message", None)
        try:
            with st.spinner("Retrieving Statcast data…"):
                data = get_pitcher_statcast(pitcher_id, start_date, end_date)
            st.session_state["statcast_result"] = (pitcher_id.strip(), start_date, end_date, data)
            st.session_state["report_generated_at"] = datetime.now(timezone.utc)
        except NoStatcastDataError as exc:
            st.session_state["statcast_message"] = ("info", str(exc))
        except StatcastError as exc:
            st.session_state["statcast_message"] = ("error", str(exc))

    if "statcast_message" in st.session_state:
        level, message = st.session_state["statcast_message"]
        getattr(st, level)(message)
    elif "statcast_result" in st.session_state:
        loaded_id, loaded_start, loaded_end, data = st.session_state["statcast_result"]
        st.caption(f"Loaded pitcher {loaded_id}: {loaded_start} through {loaded_end} (inclusive).")
        st.metric("Statcast records", len(data))
        st.dataframe(data.head(100), hide_index=True, alt="Preview of the first 100 retrieved Statcast records")
        st.caption("Preview limited to 100 rows. Missing measurements remain missing.")
        arsenal = aggregate_pitch_arsenal(data)
        render_pitch_arsenal(arsenal)
        render_movement_location(data)
        render_scouting_report(data, loaded_id, loaded_start, loaded_end)
    else:
        st.info("No player data is loaded or retrieved. Submit a request to load Statcast records.")

    st.header("Performance metrics")
    st.caption("Pitching performance summaries will appear here once data is available.")
    st.info("No performance metrics available yet.")

    st.header("Pitch visualizations")
    movement, usage = st.columns(2)
    with movement:
        st.subheader("Pitch movement")
        if "statcast_result" in st.session_state:
            st.caption("See Pitch Movement & Location Analysis above.")
        else:
            st.info("Pitch movement charts will appear here.")
    with usage:
        st.subheader("Pitch usage")
        if arsenal is None:
            st.info("Load Statcast records to view pitch usage.")
        else:
            st.caption(
                f"Unclassified pitches: {arsenal.unclassified_pitch_count:,} (excluded). "
                "Usage = pitch-type count / all classified pitches × 100. "
                "Uses all loaded rows, independently of the movement/location filter. "
                "Displayed percentages round to one decimal and may not total exactly 100%."
            )
            if data.empty:
                st.info("No pitch records available for pitch usage.")
            elif arsenal.metrics.empty:
                st.info("No classified pitches available for pitch usage.")
            else:
                st.plotly_chart(
                    pitch_usage_chart(arsenal.metrics), width="stretch", key="pitch_usage",
                    alt="Pitch counts and classified usage percentages, highest usage first",
                )


if __name__ == "__main__":
    main()
