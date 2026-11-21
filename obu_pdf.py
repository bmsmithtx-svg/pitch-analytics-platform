"""Optional, conservative validation of the inspected single-page report layout.

Extract only explicitly printed per-type counts and speed summaries (mph per
report heading). Never turn report aggregates into pitch observations or infer
chart points. Report movement/strike/contact definitions are not machine-merged.
"""

import hashlib
from pathlib import Path
import re

from obu_data import OBUDataError, PITCH_TYPES, PreparationResult, normalize_name


def parse_report_text(text: str) -> dict:
    """Strict layout contract: title + per-type table + count sequencing boundary.

    Reject incomplete or ambiguous tables rather than guessing. Means/maxima are
    printed to one decimal; comparisons allow 0.0500001 mph rounding tolerance.
    """
    title = re.findall(r'^([^\n]+) · PITCHER REPORT\s*$', text, re.M)
    tables = re.findall(r'PITCH METRICS — PER PITCH TYPE\s*\n(.*?)\nCOUNT SEQUENCING', text, re.S)
    if len(title) != 1 or len(tables) != 1:
        raise OBUDataError('Unsupported PDF text layout: expected one pitcher and one metrics table.')
    metrics: list[dict] = []
    for line in tables[0].splitlines():
        match = re.fullmatch(r'([A-Za-z]+) (\d+) (\d+\.\d) (\d+\.\d) \d+% .+', line.strip())
        if not match or match[1].casefold() not in PITCH_TYPES:
            raise OBUDataError('Unsupported or incomplete PDF pitch metrics row.')
        metrics.append({'pitch_type': PITCH_TYPES[match[1].casefold()], 'pitch_count': int(match[2]),
                        'mean_speed_mph': float(match[3]), 'max_speed_mph': float(match[4])})
    if not metrics or len({m['pitch_type'] for m in metrics}) != len(metrics):
        raise OBUDataError('Missing or duplicate PDF pitch metrics.')
    # Total in the surname/count line, cross-checked against table counts.
    prefix = text.split('PITCH METRICS')[0]
    totals = re.findall(r'^([^\n]+?) (\d+)\s*$', prefix, re.M)
    totals = [(name, int(n)) for name, n in totals if normalize_name(name).upper() in title[0]]
    if len(totals) != 1 or totals[0][1] != sum(m['pitch_count'] for m in metrics):
        raise OBUDataError('PDF total does not reconcile with pitch metrics.')
    dates = re.findall(r'\b([A-Z]+ \d{1,2}, \d{4})\b', text)
    return {'pitcher_name_report': normalize_name(title[0]), 'total_pitches': totals[0][1],
            'date_text': sorted(set(dates)), 'metrics': metrics, 'level': 'pitcher_pitch_type_summary',
            'context': 'Printed metrics table; release speed mph; no chart extraction.'}


def _report_name(csv_name: str) -> str:
    parts = csv_name.split(',')
    if len(parts) == 2:
        return normalize_name(parts[1] + ' ' + parts[0]).upper()
    return normalize_name(csv_name).upper()


def validate_pdf_reports(result: PreparationResult, directory: Path) -> None:
    """Read all supplied PDFs with optional pypdf; attach separate validation only.

    CSV speed mean is sum / finite-speed count within each tagged type; maximum
    uses the same finite sample. Empty samples are unavailable, not zero. Counts
    include all records of the type independently of speed coverage. These are
    validation comparisons only, not new application analytics.
    Association requires exact reversed-comma name matching, ignoring case and
    whitespace. No nickname/fuzzy inference. CSV dates remain unavailable unless
    explicitly supplied; matching names do not establish matching sample scope.
    """
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise OBUDataError('PDF validation requires requirements-obu-pdf.txt; omit --pdf-dir for CSV-only preparation.') from exc
    paths = sorted(directory.glob('*.pdf'))
    if not paths:
        raise OBUDataError('No PDF reports found in --pdf-dir.')
    reports: list[dict] = []
    differences: list[dict] = []
    for path in paths:
        try:
            reader = PdfReader(path)
            if len(reader.pages) != 1:
                raise OBUDataError('Expected a single-page pitcher report.')
            report = parse_report_text(reader.pages[0].extract_text())
            report.update(source_file=path.name, source_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        except OBUDataError:
            raise
        except Exception as exc:
            raise OBUDataError(f'Cannot extract PDF report: {path.name}') from exc
        names = [name for name in result.data.pitcher_name.unique() if _report_name(name) == report['pitcher_name_report']]
        if len(names) != 1:
            raise OBUDataError(f'PDF pitcher association is missing or ambiguous: {path.name}')
        name = names[0]
        rows = result.data[result.data.pitcher_name == name]
        report['pitcher_id'] = rows.pitcher_id.iloc[0]
        report['csv_pitch_count'] = len(rows)
        if len(rows) != report['total_pitches']:
            differences.append({'source_file': path.name, 'field': 'total_pitches',
                                'csv': len(rows), 'pdf': report['total_pitches']})
        reported_types = {metric['pitch_type'] for metric in report['metrics']}
        for extra in sorted(set(rows.pitch_type.dropna()) - reported_types):
            differences.append({'source_file': path.name, 'pitch_type': extra,
                                'field': 'pitch_count', 'csv': int((rows.pitch_type == extra).sum()), 'pdf': None})
        for metric in report['metrics']:
            group = rows[rows.pitch_type == metric['pitch_type']]
            speeds = group.obu_release_speed_mph.dropna()
            comparisons = [('pitch_count', len(group), 0),
                           ('mean_speed_mph', float(speeds.mean()) if len(speeds) else None, .0500001),
                           ('max_speed_mph', float(speeds.max()) if len(speeds) else None, .0500001)]
            for field, actual, tolerance in comparisons:
                if actual is None or abs(actual - metric[field]) > tolerance:
                    differences.append({'source_file': path.name, 'pitch_type': metric['pitch_type'],
                                        'field': field, 'csv': actual, 'pdf': metric[field]})
        if any(prior['pitcher_id'] == report['pitcher_id'] for prior in reports):
            raise OBUDataError('Multiple PDF reports associate with the same pitcher; review sample scope.')
        reports.append(report)
    covered = {r['pitcher_id'] for r in reports}
    result.summary['pdf_validation'] = {
        'status': 'validated_with_discrepancies' if differences else 'validated',
        'reports': reports, 'discrepancies': differences,
        'pitchers_without_reports': sorted(set(result.data.pitcher_id) - covered),
        'limitations': ['CSV has no source date; name association does not establish equivalent sample scope.',
                       'Only printed counts and speed summaries compared; all other report metrics remain references.'],
    }
