"""Offline usage charts from synthetic aggregate inputs, never player records."""

import pandas as pd
import pytest

from pitch_arsenal import aggregate_pitch_arsenal
from pitch_plots import pitch_usage_chart


@pytest.mark.parametrize('types, names, counts, percentages, labels', [
    (['SL', 'FF', 'FF', None, '', 42], ['FF', 'SL'], [2, 1], [200/3, 100/3],
     ['2 pitches · 66.7%', '1 pitch · 33.3%']),
    (['SL'] * 3, ['SL'], [3], [100], ['3 pitches · 100.0%']),
    (['SL', 'CH', 'FF'], ['CH', 'FF', 'SL'], [1, 1, 1], [100/3] * 3,
     ['1 pitch · 33.3%'] * 3),
    ([' FF ', 'FF', 'ff'], ['FF', 'ff'], [2, 1], [200/3, 100/3],
     ['2 pitches · 66.7%', '1 pitch · 33.3%']),
])
def test_usage_values_and_order(types, names, counts, percentages, labels):
    result = aggregate_pitch_arsenal(pd.DataFrame({'pitch_type': types}))
    original = result.metrics.copy(deep=True)
    # The renderer must sort even when handed a reordered aggregate.
    fig = pitch_usage_chart(result.metrics.iloc[::-1])
    bar = fig.data[0]
    assert bar.orientation == 'h'
    assert list(bar.y) == names
    assert list(bar.x) == pytest.approx(percentages)
    assert sum(bar.x) == pytest.approx(100)
    assert [row[0] for row in bar.customdata] == counts
    assert list(fig.layout.yaxis.categoryarray) == names
    assert fig.layout.yaxis.autorange == 'reversed'
    assert bar.hovertemplate == (
        'Pitch type: %{y}<br>Pitch count: %{customdata[0]:,d}'
        '<br>Usage: %{x:.1f}%<extra></extra>'
    )
    assert list(bar.text) == labels
    pd.testing.assert_frame_equal(result.metrics, original)


def test_usage_count_grammar_and_thousands_formatting():
    # Prepared chart inputs, not player records; zero tests the plural boundary.
    metrics = pd.DataFrame({'pitch_type': ['A', 'B', 'C'],
                            'pitch_count': [1000, 1, 0],
                            'usage_pct': [99.9, 0.1, 0.0]})
    bar = pitch_usage_chart(metrics).data[0]
    assert list(bar.text) == ['1,000 pitches · 99.9%', '1 pitch · 0.1%',
                              '0 pitches · 0.0%']
    assert list(bar.x) == [99.9, 0.1, 0.0]
    assert [row[0] for row in bar.customdata] == [1000, 1, 0]


def test_usage_height_grows_with_larger_arsenals():
    def chart(size):
        return pitch_usage_chart(aggregate_pitch_arsenal(pd.DataFrame({
            'pitch_type': [f'T{i}' for i in range(size)],
        })).metrics)

    small, large, larger = [chart(size) for size in (2, 8, 12)]
    assert small.layout.height >= 320
    assert large.layout.height > small.layout.height
    assert larger.layout.height > large.layout.height
    # Added categories retain at least the existing per-category vertical space.
    assert (larger.layout.height - large.layout.height) / 4 >= 52


def test_arsenal_aggregates_once_per_loaded_dashboard_render(monkeypatch):
    import json
    from unittest.mock import Mock

    from auth_helpers import authenticated_app

    data = pd.DataFrame({'pitch_type': ['FF', 'FF', 'SL']})
    fetch = Mock(return_value=data)
    aggregate = Mock(wraps=aggregate_pitch_arsenal)
    monkeypatch.setattr('statcast_service.get_pitcher_statcast', fetch)
    monkeypatch.setattr('pitch_arsenal.aggregate_pitch_arsenal', aggregate)
    app = authenticated_app()
    assert not app.exception
    fetch.assert_not_called()
    app.sidebar.radio(key="selection_source").set_value("Manual ID").run()
    aggregate.assert_not_called()
    app.sidebar.text_input(key="pitcher_id").set_value('123')
    app.sidebar.button(key="request_data").click().run()

    for render in range(3):
        assert not app.exception
        aggregate.assert_called_once()
        pd.testing.assert_frame_equal(aggregate.call_args.args[0], data)
        fetch.assert_called_once()
        charts = [json.loads(chart.proto.spec) for chart in app.get('plotly_chart')]
        usage = [spec for spec in charts if spec['data'][0]['type'] == 'bar']
        assert len(usage) == 1
        assert usage[0]['data'][0]['y'] == ['FF', 'SL']
        assert usage[0]['data'][0]['customdata'] == [[2], [1]]
        if render < 2:
            aggregate.reset_mock()
            if render == 0:
                app.run()
            else:
                app.multiselect[0].set_value([]).run()


@pytest.mark.parametrize('data, excluded', [
    (pd.DataFrame(), 0),
    (pd.DataFrame({'pitch_type': [None, '', ' ', False, 5]}), 5),
    (pd.DataFrame({'release_speed': [90, 91]}), 2),
])
def test_no_classified_usage(data, excluded):
    result = aggregate_pitch_arsenal(data)
    fig = pitch_usage_chart(result.metrics)
    assert result.unclassified_pitch_count == excluded
    assert not fig.data
    assert 'No classified pitches' in fig.layout.annotations[0].text


def test_measurements_do_not_change_usage_and_long_names_are_preserved():
    name = 'Synthetic long pitch classification name'
    data = pd.DataFrame({'pitch_type': [name, name, 'SL', None],
                         'release_speed': [None, 'bad', float('inf'), False],
                         'pfx_x': [[], {}, True, None]})
    fig = pitch_usage_chart(aggregate_pitch_arsenal(data).metrics)
    assert list(fig.data[0].y) == [name, 'SL']
    assert list(fig.data[0].x) == pytest.approx([200/3, 100/3])
    assert fig.layout.yaxis.automargin
    assert fig.data[0].cliponaxis is False


def test_usage_presentation_accepts_full_dataset_colors_without_changing_metrics():
    """Unclassified coordinate groups must not shift usage colors."""
    from pitch_plots import pitch_colors

    metrics = aggregate_pitch_arsenal(pd.DataFrame({"pitch_type": ["FF", "SL", "FF"]})).metrics
    original = metrics.copy(deep=True)
    colors = pitch_colors(["FF", "SL", "Unclassified"])
    fig = pitch_usage_chart(metrics, colors)
    assert list(fig.data[0].marker.color) == [colors[code] for code in fig.data[0].y]
    assert fig.layout.font.size == 14
    assert fig.layout.hoverlabel.font.size == 14
    assert fig.layout.margin.r == 30
    assert fig.layout.xaxis.automargin
    assert fig.data[0].textposition == "auto"
    pd.testing.assert_frame_equal(metrics, original)


def test_chart_labels_keep_readable_sizes_and_legend_space():
    from pitch_plots import style_chart
    import plotly.graph_objects as go

    fig = go.Figure()
    style_chart(fig)
    assert fig.layout.autosize is True
    assert fig.layout.width is None
    assert fig.layout.font.size == 14
    assert fig.layout.uniformtext.minsize == 12
    assert fig.layout.uniformtext.mode == "hide"
    assert fig.layout.legend.orientation == "h"
    assert fig.layout.legend.maxheight == .3
    assert fig.layout.margin.b >= 100
    assert fig.layout.xaxis.automargin and fig.layout.yaxis.automargin
