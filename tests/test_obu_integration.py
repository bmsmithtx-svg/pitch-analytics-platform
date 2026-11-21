"""Offline milestone 3.4 regressions against the authoritative cleaned artifact."""
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from unittest.mock import Mock

import pandas as pd
import pytest

from auth_helpers import authenticated_app, new_app
from obu_analytics import (
    DATA_PATH, MEASUREMENTS, arsenal_summary, build_obu_report, coverage_table,
    export_obu_report, filter_pitcher, load_obu_dataset, measurement_chart,
    obu_report_filename, pitcher_options,
)
from obu_data import OBUDataError

EXPECTED = ['AJ Minyard', 'Cade Stephentich', 'Colton Angell', 'Dillon French',
            'Eli Montgomery', 'Jacob Galloway', 'Jarrmez Daniels', 'Nick Cozzi', 'Teagon Standlee']
DIGEST = 'a03e2f0b652baf6945950320b891e1bdf07b598cebb1fd95478aebfecdcef83d'


def test_authoritative_dataset_integrity():
    data, digest = load_obu_dataset()
    assert digest == DIGEST == sha256(DATA_PATH.read_bytes()).hexdigest()
    assert len(data) == 262
    assert list(pitcher_options(data).values()) == EXPECTED
    assert data.pitch_type.value_counts().to_dict() == {
        'Fastball': 142, 'Changeup': 45, 'Cutter': 32, 'Curveball': 25, 'Slider': 14}
    assert data.pitch_type.isna().sum() == 4
    assert data.obu_release_speed_mph.count() == 262
    assert data.obu_spin_rate_source.count() == 251
    assert data.obu_horizontal_break_source.count() == 251
    assert data.pitch_date.isna().all()
    assert data.observation_id.nunique() == 262
    # Exact float/missingness preservation for every original numeric cell.
    original = pd.read_csv(DATA_PATH, dtype='string')
    for column in MEASUREMENTS:
        for actual, source in zip(data[column], original[column]):
            assert pd.isna(actual) if pd.isna(source) else actual == float(source)
    assert data.tagged_pitch_type_source.equals(original.tagged_pitch_type_source)
    assert data.auto_pitch_type_source.equals(original.auto_pitch_type_source)


@pytest.mark.parametrize('content', [b'', b'x,y\n1,2\n', b'\xff', b'"unclosed',
    DATA_PATH.read_bytes().split(b'\n', 1)[0] + b'\n',
    DATA_PATH.read_bytes().replace(b'85.16', b'bad', 1),
    DATA_PATH.read_bytes().replace(b'85.16', b'inf', 1),
    DATA_PATH.read_bytes().replace(b'Standlee, Teagon', b'Wrong, Name', 1)])
def test_invalid_dataset_fails_closed(tmp_path, content):
    path = tmp_path / 'invalid.csv'
    path.write_bytes(content)
    with pytest.raises(OBUDataError):
        load_obu_dataset(path)


def test_missing_file_and_cache_freshness(tmp_path):
    path = tmp_path / 'local.csv'
    with pytest.raises(OBUDataError, match='unavailable'):
        load_obu_dataset(path)
    path.write_bytes(DATA_PATH.read_bytes())
    first, digest = load_obu_dataset(path)
    first.loc[0, 'obu_release_speed_mph'] = 0
    assert load_obu_dataset(path)[0].obu_release_speed_mph.iloc[0] == 85.16
    path.write_bytes(DATA_PATH.read_bytes().replace(b'85.16', b'85.17', 1))
    assert load_obu_dataset(path)[1] != digest
    assert load_obu_dataset(path)[0].obu_release_speed_mph.iloc[0] == 85.17
    path.unlink()
    with pytest.raises(OBUDataError):
        load_obu_dataset(path)


@pytest.mark.parametrize('name', EXPECTED)
def test_pitcher_metrics_and_reports(name):
    data, digest = load_obu_dataset()
    identity = next(k for k, v in pitcher_options(data).items() if v == name)
    rows = filter_pitcher(data, identity)
    assert rows.pitcher_id.eq(identity).all()
    metrics, unclassified = arsenal_summary(rows)
    assert metrics['Pitch count'].sum() + unclassified == len(rows)
    assert metrics['Usage (%)'].sum() == pytest.approx(100)
    for metric in metrics.to_dict('records'):
        group = rows.loc[rows.pitch_type.eq(metric['Pitch type'])]
        assert metric['Mean velocity (mph)'] == pytest.approx(group.obu_release_speed_mph.mean())
        assert metric['Max velocity (mph)'] == group.obu_release_speed_mph.max()
        for field, label in MEASUREMENTS.items():
            assert metric[f'Valid {label} (count)'] == group[field].count()
            if field != 'obu_release_speed_mph':
                actual = metric[f'Mean {label}']
                assert pd.isna(actual) if not group[field].count() else actual == pytest.approx(group[field].mean())
    report = build_obu_report(data, identity, digest)
    assert report.pitcher_name == name
    assert report.total == len(rows)
    pd.testing.assert_frame_equal(report.arsenal, metrics)
    html = export_obu_report(report, datetime(2026, 11, 21, tzinfo=timezone.utc))
    assert name in html and 'Oklahoma Baptist University' in html
    assert digest in html and 'source units; unverified' in html
    assert 'MLBAM' not in html and 'whiff_pct' not in html and 'pfx_' not in html
    assert obu_report_filename(report).startswith('scouting-report-obu-')
    assert '/' not in obu_report_filename(report)


def test_unknown_pitcher():
    with pytest.raises(OBUDataError):
        filter_pitcher(load_obu_dataset()[0], 'missing')


@pytest.mark.parametrize('field', list(MEASUREMENTS) + [None])
def test_charts_units_counts_missingness(field):
    data, _ = load_obu_dataset()
    before = data.copy(deep=True)
    figure = measurement_chart(data, field)
    required = [field] if field else ['obu_horizontal_break_source', 'obu_induced_vertical_break_source']
    assert sum(len(trace.y) for trace in figure.data) == len(data.dropna(subset=required))
    assert any('Unclassified' in trace.name for trace in figure.data)
    assert figure.layout.yaxis.title.text == MEASUREMENTS[field or required[1]]
    for col in required:
        data[col] = float('nan')
    unavailable = measurement_chart(data, field)
    assert not unavailable.data
    assert 'No available measurements' in unavailable.layout.annotations[0].text
    assert before.obu_release_speed_mph.iloc[0] == 85.16


def test_missing_and_unclassified_denominators():
    data, _ = load_obu_dataset()
    data.loc[:, list(MEASUREMENTS)] = float('nan')
    metrics, count = arsenal_summary(data)
    assert count == 4
    assert metrics['Pitch count'].sum() == 258
    assert metrics['Usage (%)'].sum() == pytest.approx(100)
    assert metrics['Mean velocity (mph)'].isna().all()
    assert metrics.filter(like='Valid ').eq(0).all().all()
    assert coverage_table(data)['Valid observations'].eq(0).all()
    data['pitch_type'] = pd.NA
    metrics, count = arsenal_summary(data)
    assert metrics.empty and count == 262


def test_report_escape_and_timestamp():
    data, digest = load_obu_dataset()
    report = build_obu_report(data, data.pitcher_id.iloc[0], digest)
    report = replace(report, pitcher_name='<script>alert(1)</script>',
                     pitcher_id='<img src=x>', observations=('<b>bad</b>',))
    html = export_obu_report(report, datetime.now(timezone.utc))
    assert '<script>' not in html and '<img' not in html and '<b>bad' not in html
    assert '&lt;script&gt;' in html and '&lt;img' in html and '&lt;b&gt;' in html
    with pytest.raises(ValueError):
        export_obu_report(report, datetime(2026, 11, 21))


def obu_app(monkeypatch):
    fetch = Mock(side_effect=AssertionError('OBU must never retrieve MLB data'))
    monkeypatch.setattr('statcast_service.get_pitcher_statcast', fetch)
    search = Mock(side_effect=AssertionError('OBU must never search MLB players'))
    monkeypatch.setattr('pitcher_search.fetch_candidates', search)
    app = authenticated_app()
    assert app.sidebar.selectbox(key='data_source').value == 'MLB (Statcast)'
    app.sidebar.selectbox(key='data_source').set_value('OBU (Oklahoma Baptist University)').run()
    assert not app.exception
    return app, fetch, search


def test_obu_selection_analysis_report_and_invalidation(monkeypatch):
    app, fetch, search = obu_app(monkeypatch)
    selector = app.sidebar.selectbox(key='obu_pitcher')
    assert selector.options == EXPECTED
    assert not app.sidebar.date_input
    assert len(app.tabs) == 4
    data, _ = load_obu_dataset()
    options = list(pitcher_options(data))
    app.sidebar.selectbox(key='obu_pitcher').set_value(options[0]).run()
    app.sidebar.button(key='request_obu_data').click().run()
    assert not app.exception
    assert app.metric[0].value == '26'
    app.button(key='generate_obu_report').click().run()
    assert not app.exception
    assert app.session_state['obu_report'][0].pitcher_name == 'AJ Minyard'
    assert len(app.get('download_button')) == 1
    app.run()
    assert len(app.get('download_button')) == 1
    app.sidebar.selectbox(key='obu_pitcher').set_value(options[1]).run()
    assert not app.exception
    assert 'obu_result' not in app.session_state
    assert 'obu_report' not in app.session_state
    assert len(app.get('download_button')) == 0
    app.sidebar.button(key='request_obu_data').click().run()
    app.button(key='generate_obu_report').click().run()
    app.sidebar.selectbox(key='data_source').set_value('MLB (Statcast)').run()
    assert not app.exception
    assert 'obu_report' not in app.session_state and 'obu_result' not in app.session_state
    assert 'obu_pitcher' not in app.session_state
    assert len(app.get('download_button')) == 0
    assert len(app.sidebar.date_input) == 2
    assert app.sidebar.text_input(key='pitcher_id').value == ''
    fetch.assert_not_called()
    search.assert_not_called()


@pytest.mark.parametrize('name', EXPECTED)
def test_all_pitchers_selectable_offline(monkeypatch, name):
    app, fetch, search = obu_app(monkeypatch)
    data, _ = load_obu_dataset()
    identity = next(k for k, v in pitcher_options(data).items() if v == name)
    app.sidebar.selectbox(key='obu_pitcher').set_value(identity).run()
    app.sidebar.button(key='request_obu_data').click().run()
    assert not app.exception
    assert app.session_state['obu_result'][1].pitcher_id.eq(identity).all()
    fetch.assert_not_called()
    search.assert_not_called()


def test_mlb_results_cleared_when_switching_to_obu(monkeypatch):
    data = pd.DataFrame({'pitch_type': ['FF'], 'release_speed': [90.]})
    fetch = Mock(return_value=data)
    monkeypatch.setattr('statcast_service.get_pitcher_statcast', fetch)
    app = authenticated_app()
    app.sidebar.radio(key='selection_source').set_value('Manual ID').run()
    app.sidebar.text_input(key='pitcher_id').set_value('123')
    app.sidebar.button(key='request_data').click().run()
    app.button(key='generate_report').click().run()
    assert 'statcast_result' in app.session_state and 'scouting_report' in app.session_state
    app.sidebar.selectbox(key='data_source').set_value('OBU (Oklahoma Baptist University)').run()
    assert not app.exception
    assert 'statcast_result' not in app.session_state and 'scouting_report' not in app.session_state
    assert len(app.get('download_button')) == 0
    assert not app.metric
    assert app.session_state['resolved_player_id'] is None
    assert fetch.call_count == 1


def test_obu_unavailable_ui_and_authentication(monkeypatch):
    app = new_app().run()
    assert not app.sidebar.selectbox
    loader = Mock(side_effect=OBUDataError('OBU dataset is unavailable.'))
    monkeypatch.setattr('obu_ui.load_obu_dataset', loader)
    app, _, _ = obu_app(monkeypatch)
    assert 'unavailable' in app.error[0].value
    assert app.sidebar.button(key='request_obu_data').disabled
    assert not app.metric
    app.sidebar.button(key='logout').click().run()
    assert not app.sidebar.selectbox
    assert 'obu_result' not in app.session_state
