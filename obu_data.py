"""Offline, source-faithful preparation of the inspected OBU CSV export.

One nonblank CSV record is one candidate observation, not a verified unique pitch.
No Statcast fields or statistical estimates are inferred. See data/README.md for
units, identity limitations, mappings, provenance and rejection policy.
"""

from collections import Counter
import csv
from dataclasses import dataclass
from datetime import date
import hashlib
import io
import json
import math
from pathlib import Path
import re
import unicodedata
import uuid

import pandas as pd

# Source units are undocumented except RelSpeed (mph, corroborated by reports).
# Keep source units and coordinate conventions unresolved rather than guess.
NUMERIC_FIELDS = {
    'PAofInning': 'pa_of_inning', 'PitchofPA': 'pitch_of_pa',
    'Inning': 'inning', 'Outs': 'outs', 'Balls': 'balls', 'Strikes': 'strikes',
    'RelSpeed': 'obu_release_speed_mph', 'VertRelAngle': 'obu_vertical_release_angle_source',
    'HorzRelAngle': 'obu_horizontal_release_angle_source', 'SpinRate': 'obu_spin_rate_source',
    'SpinAxis': 'obu_spin_axis_source', 'RelHeight': 'obu_release_height_source',
    'RelSide': 'obu_release_side_source', 'VertBreak': 'obu_vertical_break_source',
    'InducedVertBreak': 'obu_induced_vertical_break_source',
    'HorzBreak': 'obu_horizontal_break_source', 'PlateLocHeight': 'obu_plate_height_source',
    'PlateLocSide': 'obu_plate_side_source', 'ZoneSpeed': 'obu_zone_speed_source',
    'VertApprAngle': 'obu_vertical_approach_angle_source',
    'HorzApprAngle': 'obu_horizontal_approach_angle_source',
}
TEXT_FIELDS = {
    'Batter': 'batter_name_source', 'Top/Bottom': 'inning_half_source',
    'TaggedPitchType': 'tagged_pitch_type_source', 'AutoPitchType': 'auto_pitch_type_source',
    'PitchCall': 'pitch_call_source', 'HitType': 'hit_type_source',
    'PlayResult': 'play_result_source', 'Tilt': 'obu_tilt_source',
}
PITCH_TYPES = {name.casefold(): name for name in (
    'Fastball', 'Sinker', 'Cutter', 'Slider', 'Curveball', 'Changeup', 'Splitter',
)}
REQUIRED_INPUT = ('Pitcher', 'TaggedPitchType', 'RelSpeed')
COLUMNS = (
    'schema_version', 'source_file', 'source_sha256', 'source_record',
    'observation_id', 'source_row_sha256', 'pitcher_id', 'pitcher_name',
    'pitcher_name_source', 'pitch_date', 'pitch_date_source', 'pitch_type',
    'duplicate_of_record', *TEXT_FIELDS.values(), *NUMERIC_FIELDS.values(),
)


class OBUDataError(ValueError):
    """Actionable input/schema failure; no output should be published."""


@dataclass
class PreparationResult:
    data: pd.DataFrame
    summary: dict


def normalize_name(value: str) -> str:
    """NFC plus collapsed whitespace; preserve spelling, order, punctuation/case."""
    return ' '.join(unicodedata.normalize('NFC', value).split())


def pitcher_identifier(name: str) -> str:
    """Namespaced UUID5, not MLBAM or a verified institutional identity.

    Stable across files/order for the exact normalized name. Same-name people
    cannot be disambiguated without a reviewed roster; never fuzzy-merge names.
    """
    return 'obu-' + str(uuid.uuid5(uuid.NAMESPACE_URL, 'pap:obu:pitcher:' + normalize_name(name)))


def _header(value: str) -> str:
    return re.sub(r'[^a-z0-9]', '', value.casefold())


def _row_digest(row: dict[str, str]) -> str:
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


def _number(value: str, source: str) -> tuple[float | None, str | None]:
    if not value.strip():
        return None, None
    try:
        number = float(value)
    except (ValueError, OverflowError):
        return None, 'malformed_numeric'
    if not math.isfinite(number):
        return None, 'nonfinite_numeric'
    # Only defensible sign/domain checks; no speculative velocity/movement caps.
    if source in ('RelSpeed', 'ZoneSpeed') and number <= 0:
        return None, 'nonpositive_speed'
    if source == 'SpinRate' and number < 0:
        return None, 'negative_spin'
    bounds = {'PAofInning': (1, None), 'PitchofPA': (1, None), 'Inning': (1, None),
              'Outs': (0, 2), 'Balls': (0, 3), 'Strikes': (0, 2)}
    if source in bounds:
        lower, upper = bounds[source]
        if not number.is_integer() or number < lower or (upper is not None and number > upper):
            return None, 'invalid_count'
    return number, None


def prepare_csv(source: Path, *, pitch_date: str | None = None) -> PreparationResult:
    """Read UTF-8 CSV, retain observations and mark invalid optional values missing.

    Empty records and missing pitcher associations are explicitly rejected.
    Identical full source records are flagged, NEVER removed: repeated measured
    values alone do not prove duplicate pitches. Tagged types take precedence;
    automatic types are retained separately without fallback or reclassification.
    Date is missing unless explicitly supplied as reviewed file-level metadata.
    No unit conversion is applied because source conventions are unverified.
    """
    if pitch_date is not None:
        try:
            if date.fromisoformat(pitch_date).isoformat() != pitch_date:
                raise ValueError
        except (ValueError, TypeError) as exc:
            raise OBUDataError('pitch_date must be an ISO YYYY-MM-DD date.') from exc
    try:
        raw = source.read_bytes()
    except OSError as exc:
        raise OBUDataError('Cannot read source CSV; supply an existing readable --source path.') from exc
    digest = hashlib.sha256(raw).hexdigest()
    try:
        reader = csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline=''), strict=True)
        headers = reader.fieldnames
        if not headers:
            raise OBUDataError('Source CSV has no header.')
        normalized = [_header(h) for h in headers]
        if len(set(normalized)) != len(headers) or '' in normalized:
            raise OBUDataError('Source CSV has empty or duplicate normalized column names.')
        aliases = {_header(h): h for h in (*REQUIRED_INPUT, *TEXT_FIELDS, *NUMERIC_FIELDS)}
        mapping = {h: aliases.get(_header(h), h) for h in headers}
        missing = set(REQUIRED_INPUT) - set(mapping.values())
        if missing:
            raise OBUDataError('Missing required source columns: ' + ', '.join(sorted(missing)))
        rows = list(reader)
    except (UnicodeError, csv.Error) as exc:
        raise OBUDataError('Source must be a well-formed UTF-8 CSV.') from exc
    output, rejected, warnings = [], [], []
    seen: dict[str, int] = {}
    unknown_columns = sorted(set(mapping.values()) - set(aliases.values()))
    for index, original in enumerate(rows, 1):
        if None in original or any(v is None for v in original.values()):
            raise OBUDataError(f'CSV record {index} has a different field count from the header.')
        row = {mapping[k]: v for k, v in original.items()}
        reason = 'blank_record' if not any(v.strip() for v in row.values()) else None
        name = normalize_name(row['Pitcher'])
        if not reason and not name:
            reason = 'missing_pitcher'
        if reason:
            rejected.append({'source_record': index, 'reason': reason})
            continue
        row_hash = _row_digest(original)
        duplicate = seen.get(row_hash)
        seen.setdefault(row_hash, index)
        record = {
            'schema_version': '1', 'source_file': source.name, 'source_sha256': digest,
            'source_record': index, 'observation_id': f'{digest}:{index}',
            'source_row_sha256': row_hash, 'pitcher_id': pitcher_identifier(name),
            'pitcher_name': name, 'pitcher_name_source': row['Pitcher'],
            'pitch_date': pitch_date, 'pitch_date_source': 'explicit_file_metadata' if pitch_date else None,
            'duplicate_of_record': duplicate,
        }
        tagged = row['TaggedPitchType'].strip()
        record['pitch_type'] = PITCH_TYPES.get(tagged.casefold())
        if tagged and record['pitch_type'] is None:
            warnings.append({'source_record': index, 'field': 'pitch_type', 'reason': 'unknown_classification'})
        for field, target in TEXT_FIELDS.items():
            record[target] = row.get(field, '') or None
        for field, target in NUMERIC_FIELDS.items():
            record[target], problem = _number(row.get(field, ''), field)
            if problem:
                warnings.append({'source_record': index, 'field': target, 'reason': problem})
        output.append(record)
    data = pd.DataFrame(output, columns=COLUMNS)
    for column in (*NUMERIC_FIELDS.values(), 'source_record', 'duplicate_of_record'):
        data[column] = pd.array(data[column], dtype='Float64' if column in NUMERIC_FIELDS.values() else 'Int64')
    for column in set(COLUMNS) - set(NUMERIC_FIELDS.values()) - {'source_record', 'duplicate_of_record'}:
        data[column] = pd.array(data[column], dtype='string')
    summary = {
        'schema_version': '1', 'source_file': source.name, 'source_sha256': digest,
        'source_record_count': len(rows), 'output_record_count': len(data),
        'distinct_pitchers': int(data.pitcher_id.nunique()),
        'pitch_classification_counts': dict(sorted(Counter(data.pitch_type.fillna('UNCLASSIFIED')).items())),
        'missing_value_counts': {k: int(data[k].isna().sum()) for k in ('pitch_date', 'pitch_type', *NUMERIC_FIELDS.values())},
        'rejected_record_count': len(rejected), 'rejected_reasons': dict(sorted(Counter(r['reason'] for r in rejected).items())),
        'rejected_records': rejected, 'duplicate_record_count': int(data.duplicate_of_record.notna().sum()),
        'warnings': warnings, 'unmapped_source_columns': unknown_columns,
        'classification_disagreement_count': sum(
            bool(str(r['TaggedPitchType']).strip() and str(r.get('AutoPitchType', '')).strip()) and
            str(r['TaggedPitchType']).strip().casefold() != str(r.get('AutoPitchType', '')).strip().casefold()
            for r in ({mapping[k]: v for k, v in original.items()} for original in rows)
        ),
        'pdf_validation': {'status': 'not_requested', 'reports': [], 'discrepancies': []},
        'limitations': ['Source measurement units/conventions except release speed are unverified.',
                       'Name-derived IDs cannot distinguish namesakes or reconcile spelling changes.',
                       'Identical records are retained; source has no unique pitch key.',
                       'No Statcast equivalence or completeness is asserted.'],
    }
    validate_dataset(data, summary)
    return PreparationResult(data, summary)


def validate_dataset(data: pd.DataFrame, summary: dict | None = None) -> None:
    """Fatal standardized-contract checks; optional invalid source cells warn upstream."""
    if not data.columns.is_unique or tuple(data.columns) != COLUMNS:
        raise OBUDataError('Standardized dataset schema/order is invalid.')
    for column in (*NUMERIC_FIELDS.values(), 'source_record', 'duplicate_of_record'):
        if not pd.api.types.is_numeric_dtype(data[column]):
            raise OBUDataError(f'{column} must have numeric dtype.')
        if any(not math.isfinite(float(v)) for v in data[column].dropna()):
            raise OBUDataError(f'{column} contains nonfinite values.')
    if data.source_record.isna().any() or data.source_record.duplicated().any():
        raise OBUDataError('Missing or repeated source record numbers.')
    if data.source_record.tolist() != sorted(data.source_record.tolist()):
        raise OBUDataError('Source records must retain deterministic original order.')
    seen_rows: dict[str, int] = {}
    for row in data.to_dict('records'):
        for field in ('source_sha256', 'source_row_sha256'):
            if not isinstance(row[field], str) or not re.fullmatch(r'[0-9a-f]{64}', row[field]):
                raise OBUDataError('Invalid source digest.')
        if not isinstance(row['source_file'], str) or not row['source_file']:
            raise OBUDataError('Missing source filename.')
        previous = seen_rows.get(row['source_row_sha256'])
        pointer = row['duplicate_of_record']
        if ((previous is None and pd.notna(pointer)) or
                (previous is not None and (pd.isna(pointer) or pointer != previous))):
            raise OBUDataError('Invalid duplicate source record reference.')
        seen_rows.setdefault(row['source_row_sha256'], row['source_record'])
        name = row['pitcher_name']
        if not isinstance(name, str) or not name or normalize_name(name) != name or not isinstance(row['pitcher_id'], str) or row['pitcher_id'] != pitcher_identifier(name):
            raise OBUDataError('Invalid pitcher association or identifier.')
        if row['schema_version'] != '1':
            raise OBUDataError('Unsupported schema version.')
        if pd.notna(row['pitch_date']) != pd.notna(row['pitch_date_source']):
            raise OBUDataError('Date metadata provenance is missing or inconsistent.')
        if pd.notna(row['pitch_date_source']) and row['pitch_date_source'] != 'explicit_file_metadata':
            raise OBUDataError('Unknown date metadata provenance.')
        value = row['pitch_type']
        if pd.notna(value) and value not in PITCH_TYPES.values():
            raise OBUDataError('Unrecognized standardized pitch classification.')
        if pd.notna(row['pitch_date']):
            try:
                if date.fromisoformat(row['pitch_date']).isoformat() != row['pitch_date']:
                    raise ValueError
            except (ValueError, TypeError) as exc:
                raise OBUDataError('Invalid standardized pitch date.') from exc
        for source, target in NUMERIC_FIELDS.items():
            if pd.notna(row[target]) and _number(str(row[target]), source)[1]:
                raise OBUDataError(f'Invalid measurement in {target}.')
        if row['source_record'] < 1 or row['source_record'] != int(row['source_record']):
            raise OBUDataError('Invalid source record number.')
        if row['observation_id'] != f"{row['source_sha256']}:{row['source_record']}":
            raise OBUDataError('Invalid observation provenance.')
    if data.observation_id.duplicated().any():
        raise OBUDataError('Duplicate source observation identifiers.')
    if summary is not None:
        if (summary['duplicate_record_count'] != int(data.duplicate_of_record.notna().sum()) or
                summary['rejected_record_count'] != len(summary['rejected_records']) or
                summary['output_record_count'] != len(data) or
                summary['source_record_count'] != len(data) + summary['rejected_record_count']):
            raise OBUDataError('Source/output accounting mismatch; possible unintended row loss.')


def write_result(result: PreparationResult, output: Path) -> None:
    """Deterministic UTF-8/LF CSV and sorted JSON; no clock or absolute paths.

    CSV uses round-trip numeric representation (no measurement rounding). Empty
    cells mean unavailable; zero remains numeric zero. Source order is retained.
    """
    validate_dataset(result.data, result.summary)
    output.parent.mkdir(parents=True, exist_ok=True)
    result.data.to_csv(output, index=False, lineterminator='\n', encoding='utf-8')
    output.with_suffix('.validation.json').write_text(
        json.dumps(result.summary, ensure_ascii=False, sort_keys=True, indent=2) + '\n', encoding='utf-8')
