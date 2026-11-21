"""Authenticated OBU presentation; local observations only, separate from MLB state."""
from datetime import datetime, timezone

import streamlit as st

from obu_analytics import (
    LIMITATIONS, METHODS, SOURCE, arsenal_summary, build_obu_report, coverage_table,
    export_obu_report, filter_pitcher, load_obu_dataset, measurement_chart,
    obu_report_filename, pitcher_options,
)
from obu_data import OBUDataError
from pitch_arsenal import aggregate_pitch_arsenal
from pitch_plots import pitch_colors, pitch_usage_chart


def clear_obu_analysis() -> None:
    for key in ('obu_result', 'obu_report', 'obu_message'):
        st.session_state.pop(key, None)


def render_obu_dashboard() -> None:
    """Called only after the existing authentication gate and source selection."""
    st.title('Pitch Analytics Platform')
    st.caption(SOURCE)
    dataset = None
    digest = ''
    selected = None
    with st.sidebar:
        try:
            dataset, digest = load_obu_dataset()
            options = pitcher_options(dataset)
            selected = st.selectbox('OBU pitcher', list(options), index=None,
                                    format_func=lambda value: options[value],
                                    key='obu_pitcher', on_change=clear_obu_analysis)
        except OBUDataError as exc:
            clear_obu_analysis()
            st.error(str(exc))
        submitted = st.button('Generate analysis', key='request_obu_data', type='primary',
                              disabled=selected is None, width='stretch')
        st.caption('All available local observations; no MLB ID or date range required.')
    identity = (selected, digest)
    if st.session_state.get('obu_identity') != identity:
        clear_obu_analysis()
    st.session_state['obu_identity'] = identity
    if submitted and selected is not None and dataset is not None:
        try:
            rows = filter_pitcher(dataset, selected)
            st.session_state['obu_result'] = (identity, rows)
        except OBUDataError as exc:
            st.session_state['obu_message'] = str(exc)
    if st.session_state.get('obu_message'):
        st.error(st.session_state['obu_message'])
    loaded = st.session_state.get('obu_result')
    # Independent provenance checks prevent restored/callback-skipped stale state.
    if loaded is not None and loaded[0] != identity:
        clear_obu_analysis()
        loaded = None
    overview, arsenal_view, charts, report_view = st.tabs(
        ['Pitcher Analysis', 'Pitch Arsenal', 'Visualizations', 'Scouting Report'],
        key='analysis_section', on_change='rerun',
    )
    with overview:
        st.header('Pitcher selection and analysis')
        if selected is not None and dataset is not None:
            st.text(f'Active pitcher: {options[selected]} · OBU')
        st.caption('Choose an OBU pitcher in the sidebar, then Generate analysis. '
                   'On narrow screens, open the sidebar with the top-left toggle.')
        st.caption(LIMITATIONS)
        if loaded is not None:
            rows = loaded[1]
            st.metric('OBU pitch observations', len(rows), border=True)
            st.dataframe(coverage_table(rows), hide_index=True, width='stretch',
                         alt='OBU measurement coverage including unclassified observations')
    if loaded is None:
        for view in (arsenal_view, charts, report_view):
            with view:
                st.info('Select an OBU pitcher and Generate analysis to use this section.')
        return
    assert selected is not None
    rows = loaded[1]
    metrics, unclassified = arsenal_summary(rows)
    with arsenal_view:
        st.header('Pitch Arsenal')
        st.metric('Unclassified pitches', unclassified, border=True)
        if metrics.empty:
            st.info('No classified observations available for an arsenal summary.')
        else:
            st.dataframe(metrics, hide_index=True, width='stretch',
                         alt='OBU pitch arsenal metrics and per-measurement sample counts')
        st.caption(METHODS)
    with charts:
        st.header('OBU visualizations')
        compatible = rows[['pitch_type', 'obu_release_speed_mph']].rename(
            columns={'obu_release_speed_mph': 'release_speed'})
        usage = aggregate_pitch_arsenal(compatible)
        st.subheader('Pitch usage')
        st.caption(f'{unclassified} unclassified observations excluded from classified usage.')
        if usage.metrics.empty:
            st.info('No classified observations available for pitch usage.')
        else:
            st.plotly_chart(pitch_usage_chart(usage.metrics, pitch_colors(
                rows.pitch_type.fillna('Unclassified').unique().tolist())),
                width='stretch', alt='OBU classified pitch usage percentages')
        for title, field in [('Velocity by pitch type', 'obu_release_speed_mph'),
                             ('Spin by pitch type', 'obu_spin_rate_source'),
                             ('Source break', None)]:
            st.subheader(title)
            required = [field] if field else ['obu_horizontal_break_source', 'obu_induced_vertical_break_source']
            if rows.dropna(subset=required).empty:
                st.info(f'{title}: no available measurements.')
            else:
                st.plotly_chart(measurement_chart(rows, field), width='stretch',
                                alt=f'OBU {title.lower()} from available measurements')
        st.info('Statcast movement and pitch location charts are unavailable: '
                'OBU units and coordinate conventions are unverified.')
        st.caption(METHODS)
    with report_view:
        st.header('Pitcher scouting report')
        stored = st.session_state.get('obu_report')
        if stored is not None and (stored[0].pitcher_id, stored[0].dataset_digest) != identity:
            st.session_state.pop('obu_report', None)
            stored = None
        if st.button('Generate scouting report', key='generate_obu_report', type='primary',
                     disabled=stored is not None, width='stretch'):
            report = build_obu_report(rows, selected, digest)
            generated_at = datetime.now(timezone.utc)
            stored = (report, generated_at, export_obu_report(report, generated_at))
            st.session_state['obu_report'] = stored
        if stored is None:
            st.info('Analysis ready. Choose Generate scouting report to preview and download it.')
            return
        report, generated_at, html = stored
        st.subheader('Report preview')
        st.text(f'{report.pitcher_name} · OBU · {report.total} observations; '
                f'{report.unclassified} unclassified')
        st.caption(SOURCE)
        st.dataframe(report.arsenal, hide_index=True, width='stretch',
                     alt='OBU scouting arsenal metrics and valid sample counts')
        st.dataframe(report.coverage, hide_index=True, width='stretch',
                     alt='OBU scouting measurement coverage including unclassified pitches')
        for observation in report.observations:
            st.text(observation)
        st.caption(METHODS)
        st.caption(LIMITATIONS)
        st.caption(f'Report generated: {generated_at.isoformat()} · Dataset SHA-256: {digest}')
        st.download_button('Download scouting report (HTML)', html,
                           file_name=obu_report_filename(report), mime='text/html',
                           key='obu_scouting_download', on_click='ignore', width='stretch')
