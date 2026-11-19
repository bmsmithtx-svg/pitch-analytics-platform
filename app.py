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
from report_export import export_report_html, report_table, report_filename
from statcast_service import get_pitcher_statcast
from statcast_validation import NoStatcastDataError, StatcastError, validate_request
from pitcher_search import (
    PlayerCandidate, PitcherSearchError, fetch_candidates, normalize_query, resolve_candidate,
    validate_player_id,
)


def render_pitch_arsenal(result: PitchArsenalResult) -> None:
    """Present the existing aggregate without rounding or filling its data."""
    st.header("Pitch Arsenal")
    st.metric("Unclassified pitches", result.unclassified_pitch_count, border=True,
              help="Rows without a usable source pitch classification; excluded from usage.")
    st.caption(
        "Usage percentages are calculated only from classified pitches; "
        "unclassified pitches are excluded. Each retrieved row counts as one pitch."
    )
    if result.metrics.empty:
        st.info("No classified pitches available for an arsenal summary.")
        return
    st.subheader("Pitch-type comparison")
    detail = st.radio(
        "Arsenal metrics", ["All metrics", "Usage", "Velocity and spin", "Movement"],
        horizontal=True, key="arsenal_metrics",
    )
    groups = {
        "All metrics": list(result.metrics.columns),
        "Usage": ["pitch_type", "pitch_count", "usage_pct"],
        "Velocity and spin": ["pitch_type", "pitch_count", "avg_release_speed_mph",
                              "max_release_speed_mph", "avg_spin_rate_rpm"],
        "Movement": ["pitch_type", "pitch_count", "avg_pfx_x_inches", "avg_pfx_z_inches"],
    }
    st.caption("Choose a focused view for smaller screens. Empty measurement cells mean unavailable, not zero.")
    st.dataframe(
        result.metrics,
        column_order=groups[detail],
        width="stretch",
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
    st.caption("Filter movement and location charts; usage and reports retain all loaded pitches.")
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
    movement, location = st.container(border=True), st.container(border=True)
    with movement:
        st.subheader("Pitch movement")
        st.caption("Paired mean movement by pitch type · inches · catcher view")
        if summary.valid_paired.sum():
            st.plotly_chart(movement_chart(summary, colors), alt="Paired mean pitch movement by pitch type")
        else:
            st.info("No pitches have both movement measurements in this selection.")
    with location:
        st.subheader("Pitch location")
        st.caption("Individual recorded locations · feet · catcher view")
        if not locations.empty:
            zone = strike_zone_reference(rows)
            st.plotly_chart(location_chart(locations, zone, colors), alt="Pitch locations with representative strike zone")
            st.caption(f"{zone.label}. Physical 17-inch plate width; no ball-radius expansion.")
        else:
            st.info("No pitches have both plate location measurements in this selection.")
    if not summary.empty:
        st.subheader("Movement measurement coverage")
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
    """Generate once from the valid loaded request; share preview/export state."""
    st.header("Pitcher scouting report")
    st.text(f"MLBAM {pitcher_id} · {start_date} through {end_date} (inclusive)")
    st.caption("Generate from the completed analysis; no additional data request is needed.")
    request = validate_request(pitcher_id, start_date, end_date)
    stored = st.session_state.get("scouting_report")
    if stored is not None:
        report, _, _ = stored
        if (report.pitcher_id, report.start_date, report.end_date) != request:
            st.session_state.pop("scouting_report", None)
            stored = None
    if st.button("Generate scouting report", key="generate_report", type="primary",
                 disabled=stored is not None):
        st.session_state.pop("scouting_report", None)
        st.session_state.pop("report_message", None)
        try:
            report = build_scouting_report(data, pitcher_id, start_date, end_date)
            generated_at = datetime.now(timezone.utc)
            html = export_report_html(report, generated_at)
            stored = (report, generated_at, html)
            st.session_state["scouting_report"] = stored
        except Exception:
            # Fail closed without exposing source rows or internal exception details.
            stored = None
            st.session_state["report_message"] = (
                "Unable to generate the report. Retry Generate scouting report. "
                "If the problem continues, retrieve a new analysis."
            )
    if st.session_state.get("report_message"):
        st.error(st.session_state["report_message"])
    if stored is None:
        st.info("Analysis ready. Choose Generate scouting report to preview and download it.")
        return
    report, generated_at, html = stored
    st.subheader("Report preview")
    st.text(f"{report.pitcher_name or 'Name unavailable'} · MLBAM {report.pitcher_id}")
    st.text(f"{report.start_date} through {report.end_date} (inclusive); "
            f"{report.total_pitches:,} pitches analyzed")
    st.caption("Movement, location and usage charts are in Visualizations. "
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
    st.caption(f"Report generated: {generated_at.isoformat()}")
    with st.container(border=True):
        st.subheader("Download report")
        st.caption("Save the preview as a self-contained HTML file. Open it in a browser to read or print.")
        st.download_button("Download scouting report (HTML)", html,
                           file_name=report_filename(report), mime="text/html",
                           key="scouting_download", on_click="ignore")


@st.cache_data(ttl=3600, max_entries=64, show_spinner=False)
def cached_player_search(query: str) -> tuple[PlayerCandidate, ...]:
    """Cache validated successful MLB searches for an hour, at most 64 names.

    Exceptions are not cached. Empty people lists are valid successful results.
    Query keys are normalized and casefolded before entering this cache.
    """
    return fetch_candidates(query)


def clear_loaded_analysis() -> None:
    """Drop results and reports when identity changes or a request fails."""
    for key in ("analysis_pitch_types", "statcast_result", "scouting_report", "report_message", "statcast_message"):
        st.session_state.pop(key, None)


def clear_search_selection() -> None:
    for key in ("search_results_query", "search_candidates", "selected_candidate", "search_message"):
        st.session_state.pop(key, None)
    st.session_state.pop("candidate_id", None)
    st.session_state["resolved_player_id"] = None
    clear_loaded_analysis()


def change_selection_mode() -> None:
    clear_search_selection()
    st.session_state["pitcher_id"] = ""


def render_pitcher_selection() -> str:
    """Keep typed query, result query, selection and effective identity separate."""
    st.session_state.setdefault("resolved_player_id", None)
    mode = st.radio("Select pitcher by", ["Name search", "Manual ID"],
                    key="selection_source", on_change=change_selection_mode)
    selected = None
    pitcher_id = ""
    if mode == "Name search":
        query = st.text_input("Pitcher name", key="pitcher_query", on_change=clear_search_selection)
        if st.button("Search", key="search_players"):
            clear_search_selection()
            try:
                normalized = normalize_query(query)
                with st.spinner("Searching MLB player identities…"):
                    candidates = cached_player_search(normalized.casefold())
                st.session_state["search_results_query"] = normalized
                st.session_state["search_candidates"] = candidates
            except PitcherSearchError as exc:
                st.session_state["search_message"] = str(exc)
        if st.session_state.get("search_message"):
            st.error(st.session_state["search_message"])
        candidates = st.session_state.get("search_candidates", ())
        results_query = st.session_state.get("search_results_query")
        # Independently guard the provenance even if a widget callback was skipped.
        if results_query is not None:
            try:
                current = normalize_query(query)
            except PitcherSearchError:
                current = None
            if current != results_query:
                clear_search_selection()
                candidates = ()
            elif not candidates:
                st.info("No matching players. Try a fuller name or enter an ID manually.")
            else:
                selected = resolve_candidate(results_query, candidates)
                if selected is None:
                    st.caption("Select the intended player. Historical and two-way players are included.")
                    by_id = {c.player_id: c for c in candidates}
                    if (st.session_state.get("candidate_id") is not None
                            and st.session_state["candidate_id"] not in by_id):
                        st.session_state.pop("candidate_id", None)
                        clear_loaded_analysis()
                        st.warning("The previous player selection is unavailable. Select a matching player again.")
                    candidate_id = st.selectbox("Matching players", list(by_id), index=None,
                                                format_func=lambda value: by_id[value].label(),
                                                key="candidate_id")
                    selected = by_id.get(candidate_id)
                if selected is not None:
                    pitcher_id = str(validate_player_id(selected.player_id))
                    st.text(selected.label())
    with st.expander("Advanced: Enter MLB Player ID manually"):
        st.caption("Choose Manual ID above to use this fallback, including when search is unavailable.")
        manual_id = st.text_input("MLBAM pitcher ID", key="pitcher_id", disabled=mode != "Manual ID")
    if mode == "Manual ID":
        pitcher_id = manual_id
    st.session_state["selected_candidate"] = selected
    try:
        valid_id, _, _ = validate_request(pitcher_id, date.today(), date.today())
    except StatcastError:
        valid_id = None
    st.session_state["resolved_player_id"] = valid_id
    identity = (mode, valid_id)
    if st.session_state.get("effective_identity") != identity:
        clear_loaded_analysis()
    st.session_state["effective_identity"] = identity
    if valid_id is not None:
        st.text(f"Selected via {mode.lower()}: MLB ID {valid_id}")
    return pitcher_id


def render_pitch_usage(data: pd.DataFrame, arsenal: PitchArsenalResult) -> None:
    """Present classified usage from all loaded rows, without chart filtering."""
    st.subheader("Pitch usage")
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
            pitch_usage_chart(arsenal.metrics, pitch_colors(
                prepare_pitch_coordinates(data).pitch_type.unique().tolist()
            )), width="stretch", key="pitch_usage",
            alt="Pitch counts and classified usage percentages, highest usage first",
        )


def main() -> None:
    """Render one dashboard; only explicit submission can retrieve Statcast rows."""
    st.set_page_config(
        page_title="Pitch Analytics Platform", page_icon="⚾", layout="wide",
    )
    with st.sidebar:
        st.header("Pitcher selection")
        pitcher_id = render_pitcher_selection()
        st.subheader("Analysis dates")
        # Outside a form so edits invalidate results immediately, before another
        # view can present rows or a report from the old dates. No edit fetches data.
        start_date = st.date_input(
            "Start date", value=date.today() - timedelta(days=29),
            key="analysis_start", on_change=clear_loaded_analysis,
        )
        end_date = st.date_input(
            "End date", value=date.today(), key="analysis_end",
            on_change=clear_loaded_analysis,
        )
        submitted = st.button("Generate analysis", key="request_data", type="primary", width="stretch")
        st.caption("Maximum 30 days, including both endpoints. Data loads only on request.")

    st.title("Pitch Analytics Platform")
    st.caption("MLB pitch arsenal, movement, location and descriptive scouting · Statcast")
    candidate = st.session_state.get("selected_candidate")
    active_name = candidate.full_name if candidate is not None else "Name unavailable"
    active_id = st.session_state.get("resolved_player_id")
    with st.container(border=True):
        if active_id is None:
            st.text("No pitcher selected")
        else:
            st.text(f"Active pitcher: {active_name} · MLB ID {active_id}")
        st.text(f"Analysis dates: {start_date} through {end_date} (inclusive)")

    # Guard provenance independently of widget callbacks (including restored state).
    loaded = st.session_state.get("statcast_result")
    if loaded is not None:
        try:
            request = validate_request(pitcher_id, start_date, end_date)
            if request != validate_request(*loaded[:3]):
                clear_loaded_analysis()
        except StatcastError:
            clear_loaded_analysis()

    if submitted:
        clear_loaded_analysis()
        try:
            validate_request(pitcher_id, start_date, end_date)
            with st.spinner("Generating analysis: retrieving Statcast data…"):
                data = get_pitcher_statcast(pitcher_id, start_date, end_date)
            if data.empty:
                raise NoStatcastDataError("No records found. Choose another pitcher or date range.")
            st.session_state["statcast_result"] = (pitcher_id.strip(), start_date, end_date, data)
        except NoStatcastDataError as exc:
            st.session_state["statcast_message"] = ("info", str(exc))
        except StatcastError as exc:
            st.session_state["statcast_message"] = ("error", str(exc))

    loaded = st.session_state.get("statcast_result")
    if "statcast_message" in st.session_state:
        level, message = st.session_state["statcast_message"]
        getattr(st, level)(message)
        st.caption("Adjust the pitcher or dates, or choose Generate analysis to retry.")
    elif loaded is not None:
        st.success("Analysis ready. Explore the arsenal, visualizations, or scouting report below.")
    elif active_id is None:
        st.info("No player data is loaded or retrieved. Select a pitcher in the sidebar, then generate analysis.")
    else:
        st.info("Pitcher selected. Choose dates in the sidebar, then select Generate analysis.")

    # These native tabs deliberately keep the inexpensive in-memory presentations
    # mounted: chart filters survive navigation and no tab can initiate retrieval.
    # Tracking the selected tab also preserves it through unrelated widget reruns.
    overview, arsenal_view, charts, report_view = st.tabs(
        ["Pitcher Selection & Analysis", "Pitch Arsenal", "Visualizations", "Scouting Report"],
        key="analysis_section", on_change="rerun",
    )
    with overview:
        st.header("Pitcher selection and analysis")
        st.caption("Select a pitcher and dates in the sidebar. Generate analysis once, then explore the tabs.")
        if loaded is not None:
            loaded_id, loaded_start, loaded_end, data = loaded
            st.caption(f"Loaded pitcher {loaded_id}: {loaded_start} through {loaded_end} (inclusive).")
            st.metric("Statcast records", len(data), border=True,
                      help="Returned rows in the loaded request, including unclassified pitches.")
            with st.expander("Retrieved records preview"):
                st.dataframe(data.head(100), hide_index=True,
                             alt="Preview of the first 100 retrieved Statcast records")
                st.caption("Preview limited to 100 rows. Missing measurements remain missing.")
    if loaded is None:
        for view in (arsenal_view, charts, report_view):
            with view:
                st.info("Load Statcast records with Generate analysis in the sidebar to use this section.")
        return

    arsenal = aggregate_pitch_arsenal(data)
    with arsenal_view:
        render_pitch_arsenal(arsenal)
    with charts:
        render_movement_location(data)
        with st.container(border=True):
            render_pitch_usage(data, arsenal)
    with report_view:
        render_scouting_report(data, loaded_id, loaded_start, loaded_end)


if __name__ == "__main__":
    main()
