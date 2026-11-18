"""Deterministic synthetic coordinates only; no player records or network."""

import numpy as np
import pandas as pd
import pytest

from pitch_movement import (prepare_pitch_coordinates, movement_summary,
                            filter_pitch_types, valid_locations, strike_zone_reference)
from pitch_plots import movement_chart, location_chart, pitch_colors, pitch_symbols


def test_independent_and_paired_denominators():
    raw = pd.DataFrame({'pitch_type': [' FF '] * 4, 'pfx_x': [1.25, -1, 0, None],
                        'pfx_z': [-.5, None, 0, 2]})
    original = raw.copy(deep=True)
    rows = prepare_pitch_coordinates(raw)
    s = movement_summary(rows).iloc[0]
    assert rows.pfx_x.tolist()[:3] == [15, -12, 0]
    assert rows.pfx_z.iloc[0] == -6
    assert s.avg_horizontal_inches == 1
    assert s.avg_induced_vertical_inches == 6
    assert (s.valid_horizontal, s.valid_vertical, s.valid_paired) == (3, 3, 2)
    assert s.paired_horizontal_inches == 7.5
    assert s.paired_vertical_inches == -3
    fig = movement_chart(movement_summary(rows), pitch_colors(['FF']))
    assert list(fig.data[0].x) == [7.5]
    assert list(fig.data[0].y) == [-3]
    assert list(fig.data[0].customdata) == [2]
    assert fig.layout.xaxis.title.text == 'Horizontal Movement (inches)'
    assert fig.layout.yaxis.title.text == 'Induced Vertical Movement (inches)'
    assert fig.layout.xaxis.zeroline and fig.layout.yaxis.zeroline
    pd.testing.assert_frame_equal(raw, original)


@pytest.mark.parametrize('bad', [None, pd.NA, np.nan, np.inf, -np.inf, True, np.bool_(False), 'bad', [], {}, 1e308])
def test_invalid_movement_is_missing(bad):
    rows = prepare_pitch_coordinates(pd.DataFrame({'pitch_type': ['FF'], 'pfx_x': [bad], 'pfx_z': [bad]}))
    s = movement_summary(rows).iloc[0]
    assert s.valid_horizontal == s.valid_vertical == s.valid_paired == 0
    assert pd.isna(s.avg_horizontal_inches)
    assert not movement_chart(movement_summary(rows), pitch_colors(['FF'])).data


def test_types_filter_and_unclassified_locations():
    rows = prepare_pitch_coordinates(pd.DataFrame({'pitch_type': [' FF ', 'SL', None, 1, ''],
                                                  'plate_x': [-1, 0, 1, 2, 3], 'plate_z': [2] * 5}))
    assert rows.pitch_type.tolist() == ['FF', 'SL', 'Unclassified', 'Unclassified', 'Unclassified']
    assert len(filter_pitch_types(rows, ['FF', 'SL', 'Unclassified'])) == 5
    assert filter_pitch_types(rows, []).empty
    selected = filter_pitch_types(rows, ['FF'])
    assert movement_summary(selected).pitch_type.tolist() == ['FF']
    assert valid_locations(selected).plate_x.tolist() == [-1]


def test_location_and_zone_geometry():
    rows = prepare_pitch_coordinates(pd.DataFrame({
        'pitch_type': ['FF'] * 5, 'plate_x': [-1, 0, 1, None, True],
        'plate_z': [2, -1, None, 3, 2], 'sz_bot': [1, 2, 4, -1, True],
        'sz_top': [3, 4, 2, 4, 3],
    }))
    locations = valid_locations(rows)
    assert locations.plate_x.tolist() == [-1, 0]
    assert locations.plate_z.tolist() == [2, -1]
    zone = strike_zone_reference(rows)
    assert (zone.bottom, zone.top, zone.count) == (1.5, 3.5, 2)
    fig = location_chart(locations, zone, pitch_colors(['FF']))
    assert list(fig.data[0].x) == [-1, 0]
    assert list(fig.data[0].y) == [2, -1]
    shape = fig.layout.shapes[0]
    assert shape.x1 - shape.x0 == 17 / 12
    assert (shape.y0, shape.y1) == (1.5, 3.5)
    assert fig.layout.yaxis.scaleanchor == 'x'
    assert fig.layout.yaxis.scaleratio == 1
    assert fig.layout.xaxis.title.text == 'Horizontal Plate Location (feet)'
    assert fig.layout.yaxis.title.text == 'Vertical Plate Location (feet)'


@pytest.mark.parametrize('data', [pd.DataFrame(), pd.DataFrame({'pitch_type': ['FF']}),
                                  pd.DataFrame({'sz_bot': [3, None], 'sz_top': [2, np.inf]})])
def test_empty_missing_and_generic_reference(data):
    rows = prepare_pitch_coordinates(data)
    zone = strike_zone_reference(rows)
    assert zone.count == 0 and 'Generic' in zone.label
    assert (zone.bottom, zone.top) == (1.5, 3.5)
    assert not movement_chart(movement_summary(rows), pitch_colors(rows.pitch_type.tolist())).data
    assert not location_chart(valid_locations(rows), zone, pitch_colors(rows.pitch_type.tolist())).data


def test_disjoint_samples_no_centroid_and_numeric_strings():
    rows = prepare_pitch_coordinates(pd.DataFrame({'pitch_type': ['FF', 'FF'],
                                                  'pfx_x': ['1.25', None], 'pfx_z': [None, '-0.5']}))
    s = movement_summary(rows)
    assert s.avg_horizontal_inches.iloc[0] == 15
    assert s.avg_induced_vertical_inches.iloc[0] == -6
    assert s.valid_paired.iloc[0] == 0
    assert not movement_chart(s, pitch_colors(['FF'])).data


def test_contract_and_duplicate_index():
    with pytest.raises(TypeError):
        prepare_pitch_coordinates([])
    with pytest.raises(ValueError):
        prepare_pitch_coordinates(pd.DataFrame([[1, 2]], columns=['pfx_x', 'pfx_x']))
    rows = prepare_pitch_coordinates(pd.DataFrame({'pfx_x': [0, -1]}, index=[0, 0]))
    assert rows.pfx_x.tolist() == [0, -12]


@pytest.mark.parametrize('bad', [None, pd.NA, np.nan, np.inf, -np.inf, True, 'bad'])
@pytest.mark.parametrize('column', ['plate_x', 'plate_z', 'sz_top', 'sz_bot'])
def test_location_and_zone_invalid_fields(column, bad):
    data = {'pitch_type': ['FF'], 'plate_x': [0], 'plate_z': [2],
            'sz_bot': [1.5], 'sz_top': [3.5]}
    data[column] = [bad]
    rows = prepare_pitch_coordinates(pd.DataFrame(data))
    if column.startswith('plate_'):
        assert valid_locations(rows).empty
    else:
        assert strike_zone_reference(rows).count == 0


def test_colors_and_large_location_sample():
    rows = prepare_pitch_coordinates(pd.DataFrame({'pitch_type': ['FF', 'SL'] * 1000,
                                                  'plate_x': [0] * 2000, 'plate_z': [2] * 2000}))
    colors = pitch_colors(['FF', 'SL'])
    full = location_chart(valid_locations(rows), strike_zone_reference(rows), colors)
    selected = filter_pitch_types(rows, ['SL'])
    filtered = location_chart(valid_locations(selected), strike_zone_reference(selected), colors)
    assert sum(len(trace.x) for trace in full.data) == 2000
    assert filtered.data[0].marker.color == full.data[1].marker.color
    assert len(filtered.data[0].x) == 1000


def test_unequal_groups_have_independent_means_and_paired_centroids():
    # FF inches: x=[12, 24, 36], z=[6, 18, 30, 42]; pairs=(12,6),(36,18).
    # SL inches: x=[-24, -12, 0], z=[-6, 6]; pair=(-24,-6).
    raw = pd.DataFrame({
        'pitch_type': ['FF'] * 5 + ['SL'] * 4,
        'pfx_x': [1, 2, 3, None, None, -2, -1, 0, None],
        'pfx_z': [.5, None, 1.5, 2.5, 3.5, -.5, None, None, .5],
    })
    rows = prepare_pitch_coordinates(raw)
    summary = movement_summary(rows).set_index('pitch_type')
    expected = {
        'FF': [24, 24, 3, 4, 2, 24, 12],
        'SL': [-12, 0, 3, 2, 1, -24, -6],
    }
    for code, values in expected.items():
        assert summary.loc[code].tolist() == values
        alone = movement_summary(filter_pitch_types(rows, [code])).set_index('pitch_type')
        pd.testing.assert_series_equal(summary.loc[code], alone.loc[code])
    changed = rows.copy()
    changed.loc[changed.pitch_type == 'SL', ['pfx_x', 'pfx_z']] = 999
    pd.testing.assert_series_equal(
        summary.loc['FF'], movement_summary(changed).set_index('pitch_type').loc['FF'])
    fig = movement_chart(summary.reset_index(), pitch_colors(['FF', 'SL']))
    assert [(t.name, list(t.x), list(t.y), list(t.customdata)) for t in fig.data] == [
        ('FF', [24], [12], [2]), ('SL', [-24], [-6], [1])]


def test_repeated_colors_have_distinct_stable_symbols_in_both_charts():
    types = [f'P{i:02}' for i in range(23)]
    colors = pitch_colors(types)
    symbols = pitch_symbols(colors)
    assert colors == pitch_colors(list(reversed(types)))
    assert symbols == pitch_symbols(dict(reversed(list(colors.items()))))
    assert colors['P00'] == colors['P11'] == colors['P22']
    assert [symbols[c] for c in ['P00', 'P11', 'P22']] == ['circle', 'square', 'diamond']
    assert len({(colors[c], symbols[c]) for c in types}) == len(types)
    rows = prepare_pitch_coordinates(pd.DataFrame({
        'pitch_type': types, 'pfx_x': range(23), 'pfx_z': [1] * 23,
        'plate_x': [0] * 23, 'plate_z': [2] * 23,
    }))
    for chart in (
        lambda r: movement_chart(movement_summary(r), colors),
        lambda r: location_chart(valid_locations(r), strike_zone_reference(r), colors),
    ):
        full = chart(rows)
        assert len({t.name for t in full.data}) == 23
        assert len({(t.marker.color, t.marker.symbol) for t in full.data}) == 23
        for index in [0, 11, 22]:
            filtered = chart(filter_pitch_types(rows, [types[index]]))
            before, after = full.data[index], filtered.data[0]
            assert after.name == before.name
            assert after.marker.color == before.marker.color
            assert after.marker.symbol == before.marker.symbol
            assert list(after.x) == list(before.x)
            assert list(after.y) == list(before.y)
            assert filtered.layout.yaxis.scaleanchor == 'x'
            assert filtered.layout.yaxis.scaleratio == 1
