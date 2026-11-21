"""Regenerate local OBU data without network access or changes to the application."""

import argparse
from pathlib import Path
import sys

# Support execution by path from any working directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from obu_data import OBUDataError, prepare_csv, write_result  # noqa: E402
from obu_pdf import validate_pdf_reports  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path, help='Original OBU UTF-8 pitch CSV')
    parser.add_argument('--output', type=Path, default=Path(__file__).resolve().parents[1] / 'data/obu_pitching_cleaned.csv')
    parser.add_argument('--pitch-date', help='Optional reviewed file-level date (YYYY-MM-DD); never inferred from filename')
    parser.add_argument('--pdf-dir', type=Path, help='Optional directory of single-page SmartPark pitcher reports')
    args = parser.parse_args()
    try:
        output = args.output.resolve()
        summary = output.with_suffix('.validation.json')
        protected = [args.source.resolve()]
        if args.pdf_dir:
            protected.extend(p.resolve() for p in args.pdf_dir.glob('*.pdf'))
        if output in protected or summary in protected or output == summary:
            raise OBUDataError('Output paths must not overwrite input files or each other.')
        result = prepare_csv(args.source, pitch_date=args.pitch_date)
        if args.pdf_dir:
            validate_pdf_reports(result, args.pdf_dir)
        write_result(result, output)
    except (OBUDataError, OSError) as exc:
        parser.exit(2, f'OBU preparation failed: {exc}\n')
    print(f"Prepared {len(result.data)} observations; {result.summary['distinct_pitchers']} pitchers; "
          f"{result.summary['rejected_record_count']} rejected records; "
          f"{len(result.summary['warnings'])} cell warnings. Validation: {summary}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
