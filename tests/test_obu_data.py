"""Synthetic OBU preparation fixtures; no actual athlete records or network access."""

import csv
import json
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from obu_data import (COLUMNS, NUMERIC_FIELDS, OBUDataError, pitcher_identifier,
                      prepare_csv, validate_dataset, write_result)
from obu_pdf import parse_report_text, validate_pdf_reports


@pytest.fixture
def source(tmp_path):
    def make(rows=None, headers=None):
        path = tmp_path / 'synthetic.csv'
        headers = headers or ['Pitcher', 'TaggedPitchType', 'RelSpeed', 'AutoPitchType', 'HorzBreak', 'SpinRate', 'PitchofPA']
        rows = rows if rows is not None else [["Example, Zoë O’Test", 'Fastball', '81.25', 'Cutter', '-12', '2000', '1']]
        with path.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(headers)
            writer.writerows(rows)
        return path
    return make


def test_success_schema_names_and_source_preservation(source):
    path = source()
    result = prepare_csv(path)
    assert tuple(result.data.columns) == COLUMNS
    row = result.data.iloc[0]
    assert row.pitcher_name == 'Example, Zoë O’Test'
    assert row.pitcher_name_source == row.pitcher_name
    assert row.pitcher_id == pitcher_identifier(row.pitcher_name)
    assert row.pitch_type == 'Fastball'
    assert row.auto_pitch_type_source == 'Cutter'
    assert row.obu_release_speed_mph == 81.25
    assert row.obu_horizontal_break_source == -12  # NO assumed inches->feet/sign conversion.
    assert 'pfx_x' not in result.data
    assert 'pitcher' not in result.data  # Not an MLBAM identifier.
    assert all(pd.api.types.is_numeric_dtype(result.data[c]) for c in NUMERIC_FIELDS.values())
    assert result.summary['output_record_count'] == 1
    assert result.summary['unmapped_source_columns'] == []
    assert path.read_text().startswith('Pitcher,')


@pytest.mark.parametrize('pitch,expected', [(' fastball ', 'Fastball'), ('CURVEBALL', 'Curveball'),
    ('Changeup', 'Changeup'), ('Slider', 'Slider'), ('Cutter', 'Cutter'), ('Sinker', 'Sinker'), ('Splitter', 'Splitter')])
def test_classification_mapping(source, pitch, expected):
    result = prepare_csv(source([['Synthetic, One', pitch, '80', 'Fastball', '', '', '1']]))
    assert result.data.pitch_type.iloc[0] == expected


@pytest.mark.parametrize('pitch,warning', [('', False), ('Mystery', True), ('FF', True)])
def test_no_automatic_classification_fallback(source, pitch, warning):
    result = prepare_csv(source([['Synthetic, One', pitch, '', 'Fastball', '', '', '1']]))
    assert pd.isna(result.data.pitch_type.iloc[0])
    assert bool(result.summary['warnings']) is warning
    assert result.summary['pitch_classification_counts'] == {'UNCLASSIFIED': 1}


@pytest.mark.parametrize('value,reason', [('bad', 'malformed_numeric'), ('True', 'malformed_numeric'),
    ('NaN', 'nonfinite_numeric'), ('inf', 'nonfinite_numeric'), ('1e999', 'nonfinite_numeric'),
    ('0', 'nonpositive_speed'), ('-1', 'nonpositive_speed')])
def test_invalid_optional_speed_keeps_observation(source, value, reason):
    result = prepare_csv(source([['Synthetic, One', 'Fastball', value, '', '', '', '1']]))
    assert len(result.data) == 1
    assert pd.isna(result.data.obu_release_speed_mph.iloc[0])
    assert result.summary['warnings'][0]['reason'] == reason


def test_missing_and_valid_zero_are_different(source):
    result = prepare_csv(source([['Synthetic, One', '', '', '', '0', '0', '1']]))
    row = result.data.iloc[0]
    assert pd.isna(row.obu_release_speed_mph) and pd.isna(row.pitch_date)
    assert row.obu_horizontal_break_source == 0 and row.obu_spin_rate_source == 0
    assert result.summary['missing_value_counts']['obu_release_speed_mph'] == 1


def test_rejections_accounting_and_duplicate_retention(source):
    pitch = ['Synthetic, One', 'Fastball', '80', '', '', '', '1']
    other_pitch = pitch[:-1] + ['2']
    result = prepare_csv(source([pitch, pitch, other_pitch, [''] * 7, ['', 'Fastball', '80', '', '', '', '1']]))
    assert len(result.data) == 3
    assert result.summary['source_record_count'] == 5
    assert result.summary['rejected_reasons'] == {'blank_record': 1, 'missing_pitcher': 1}
    assert result.summary['duplicate_record_count'] == 1
    assert result.data.duplicate_of_record.iloc[1] == 1
    assert pd.isna(result.data.duplicate_of_record.iloc[2])
    assert result.data.observation_id.nunique() == 3
    assert result.data.source_record.tolist() == [1, 2, 3]


def test_stable_ids_unicode_and_order(source):
    a = pitcher_identifier('  Example,  Zoe\u0308 O’Test ')
    assert a == pitcher_identifier('Example, Zoë O’Test')
    path = source([['Other, Synthetic', '', '', '', '', '', '1'], ['Example, Zoë O’Test', '', '', '', '', '', '2']])
    result = prepare_csv(path)
    assert result.data.pitcher_id.iloc[1] == a
    assert result.data.pitcher_name.iloc[0] == 'Other, Synthetic'


@pytest.mark.parametrize('headers', [['Pitcher', 'RelSpeed'], ['Pitcher', 'TaggedPitchType'],
    ['TaggedPitchType', 'RelSpeed'], ['Pitcher', 'Pitcher', 'RelSpeed'], ['Pitcher', 'Pitch-er', 'RelSpeed']])
def test_invalid_required_columns(source, headers):
    with pytest.raises(OBUDataError):
        prepare_csv(source([], headers))


def test_header_normalization(source):
    result = prepare_csv(source([['Synthetic, One', 'Fastball', '80']], [' pitcher ', 'tagged_pitch_type', 'rel_speed']))
    assert len(result.data) == 1


@pytest.mark.parametrize('value', ['2026-02-30', '10/28/2026', '', '20261028'])
def test_invalid_date(source, value):
    with pytest.raises(OBUDataError, match='ISO'):
        prepare_csv(source(), pitch_date=value)


def test_explicit_date_and_determinism(source, tmp_path):
    path = source()
    out = tmp_path / 'result/cleaned.csv'
    first = prepare_csv(path, pitch_date='2026-10-28')
    write_result(first, out)
    before = (out.read_bytes(), out.with_suffix('.validation.json').read_bytes())
    write_result(prepare_csv(path, pitch_date='2026-10-28'), out)
    assert before == (out.read_bytes(), out.with_suffix('.validation.json').read_bytes())
    pd.testing.assert_frame_equal(first.data, prepare_csv(path, pitch_date='2026-10-28').data)
    assert first.data.pitch_date.iloc[0] == '2026-10-28'
    assert first.data.pitch_date_source.iloc[0] == 'explicit_file_metadata'
    assert json.loads(before[1])['source_record_count'] == 1
    assert pd.read_csv(out).obu_release_speed_mph.iloc[0] == 81.25


def test_missing_source(tmp_path):
    with pytest.raises(OBUDataError, match='readable --source'):
        prepare_csv(tmp_path / 'absent.csv')


def test_malformed_csv(source):
    path = source()
    path.write_text('Pitcher,TaggedPitchType,RelSpeed\nName,Fastball,80,extra\n')
    with pytest.raises(OBUDataError, match='field count'):
        prepare_csv(path)


@pytest.mark.parametrize('field,value', [('obu_release_speed_mph', float('inf')),
    ('obu_release_speed_mph', -1), ('obu_spin_rate_source', -2), ('pitch_of_pa', 1.5),
    ('pitcher_id', 'mlbam-123'), ('pitcher_name', ''), ('pitch_type', 'Unknown'),
    ('pitch_date', 'not-a-date'), ('observation_id', 'wrong')])
def test_standardized_validation_rejects_corruption(source, field, value):
    result = prepare_csv(source())
    result.data.loc[0, field] = value
    with pytest.raises(OBUDataError):
        validate_dataset(result.data, result.summary)


def test_standardized_schema_and_accounting(source):
    result = prepare_csv(source())
    with pytest.raises(OBUDataError, match='schema'):
        validate_dataset(result.data.drop(columns='pitcher_id'))
    result.summary['source_record_count'] += 1
    with pytest.raises(OBUDataError, match='row loss'):
        validate_dataset(result.data, result.summary)


def test_empty_source_produces_typed_schema(source):
    result = prepare_csv(source([]))
    assert result.data.empty and tuple(result.data.columns) == COLUMNS
    assert result.summary['output_record_count'] == 0


def test_cli_create_missing_and_overwrite_guard(source, tmp_path):
    script = Path(__file__).resolve().parents[1] / 'scripts/prepare_obu_data.py'
    path = source()
    output = tmp_path / 'cli.csv'
    command = [sys.executable, str(script), '--source', str(path), '--output', str(output)]
    result = subprocess.run(command, capture_output=True, text=True, cwd=tmp_path)
    assert result.returncode == 0, result.stderr
    assert output.exists()
    result = subprocess.run(command[:-1] + [str(path)], capture_output=True, text=True)
    assert result.returncode == 2 and 'overwrite' in result.stderr
    path.unlink()
    output.unlink()
    result = subprocess.run(command, capture_output=True, text=True)
    assert result.returncode == 2 and 'readable --source' in result.stderr
    assert not output.exists()


# Synthetic single-page report text, matching only the supported printed table.
REPORT = '''SYNTHETIC ONE · PITCHER REPORT
One 2
PITCH METRICS — PER PITCH TYPE
Fastball 2 80.0 81.0 50% 1000 to 2000 1 to 2 -1 to 2
COUNT SEQUENCING — PITCH USAGE BY COUNT
VS TEST · OCTOBER 28, 2026 · WIN SMARTPARK
'''


def test_pdf_strict_extraction():
    report = parse_report_text(REPORT)
    assert report['total_pitches'] == 2
    assert report['metrics'][0]['mean_speed_mph'] == 80
    assert report['level'] == 'pitcher_pitch_type_summary'


@pytest.mark.parametrize('text', [REPORT.replace('One 2', 'One 3'), REPORT.replace('80.0', 'missing'),
    REPORT.replace('PITCHER REPORT', 'OTHER'), REPORT.replace('Fastball', 'Unknown')])
def test_pdf_unsupported_layout_fails(text):
    with pytest.raises(OBUDataError):
        parse_report_text(text)


def test_pdf_association_and_discrepancies_without_enrichment(source, tmp_path, monkeypatch):
    from types import SimpleNamespace
    path = tmp_path / 'synthetic.pdf'
    path.write_bytes(b'SYNTHETIC PDF placeholder; mocked extraction')
    monkeypatch.setitem(sys.modules, 'pypdf', SimpleNamespace(PdfReader=lambda _: SimpleNamespace(
        pages=[SimpleNamespace(extract_text=lambda: REPORT)])))
    result = prepare_csv(source([['One, Synthetic', 'Fastball', '80', '', '', '', '1']]))
    before = result.data.copy(deep=True)
    validate_pdf_reports(result, tmp_path)
    pd.testing.assert_frame_equal(before, result.data)
    validation = result.summary['pdf_validation']
    assert validation['status'] == 'validated_with_discrepancies'
    assert any(d['field'] == 'total_pitches' for d in validation['discrepancies'])
    assert validation['reports'][0]['pitcher_id'] == result.data.pitcher_id.iloc[0]
    result.data.loc[0, 'pitcher_name'] = 'Different, Synthetic'
    with pytest.raises(OBUDataError, match='association'):
        validate_pdf_reports(result, tmp_path)


@pytest.mark.parametrize('field,value', [('pitcher_id', pd.NA), ('source_row_sha256', 'bad'),
    ('source_record', 0), ('duplicate_of_record', 1), ('pitch_date_source', 'unverified'),
    ('schema_version', '2')])
def test_provenance_validation(source, field, value):
    result = prepare_csv(source())
    result.data.loc[0, field] = value
    with pytest.raises(OBUDataError):
        validate_dataset(result.data, result.summary)


def test_no_mutation_of_statcast_pipeline(source):
    from datetime import date
    from statcast_validation import validate_response
    from pitch_arsenal import aggregate_pitch_arsenal
    data = pd.DataFrame({'game_date': ['2026-01-01'], 'pitcher': [123],
                         'pitch_type': ['FF'], 'release_speed': [80], 'pfx_x': [-1], 'pfx_z': [1]})
    original = validate_response(data, 123, date(2026, 1, 1), date(2026, 1, 1))
    expected = aggregate_pitch_arsenal(original).metrics
    prepare_csv(source())
    pd.testing.assert_frame_equal(expected, aggregate_pitch_arsenal(original).metrics)
    assert expected.avg_pfx_x_inches.iloc[0] == -12


def test_negative_spin_and_invalid_count_warn(source):
    result = prepare_csv(source([['Synthetic, One', 'Fastball', '80', '', '-1', '-2', '1.5']]))
    assert {w['reason'] for w in result.summary['warnings']} == {'negative_spin', 'invalid_count'}
    assert result.data.obu_horizontal_break_source.iloc[0] == -1


def test_pdf_rounding_tolerance(source, tmp_path, monkeypatch):
    from types import SimpleNamespace
    (tmp_path / 'synthetic.pdf').write_bytes(b'mock')
    monkeypatch.setitem(sys.modules, 'pypdf', SimpleNamespace(PdfReader=lambda _: SimpleNamespace(
        pages=[SimpleNamespace(extract_text=lambda: REPORT)])))
    result = prepare_csv(source([['One, Synthetic', 'Fastball', '79.04', '', '', '', '1'],
                                 ['One, Synthetic', 'Fastball', '81.04', '', '', '', '2']]))
    validate_pdf_reports(result, tmp_path)
    assert result.summary['pdf_validation']['status'] == 'validated'
    assert result.summary['pdf_validation']['discrepancies'] == []


def test_unknown_columns_are_disclosed(source):
    result = prepare_csv(source([['Synthetic, One', '', '', 'unmapped']],
                                ['Pitcher', 'TaggedPitchType', 'RelSpeed', 'Mystery']))
    assert result.summary['unmapped_source_columns'] == ['Mystery']
