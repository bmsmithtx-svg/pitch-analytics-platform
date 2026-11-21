# OBU data preparation (Milestone 3.3)

This is a local, offline preparation pipeline, separate from the MLB application.
No application imports these modules. No dashboards, selection controls, scouting
formulas, authentication, Statcast processing or deployment settings change.
Milestone 3.4 application integration is deferred.

## Privacy and source inventory

The repository was verified PUBLIC through GitHub during implementation. The user
explicitly confirmed school/data-owner authorization for public publication of
these supplied records. Only the cleaned CSV and its validation JSON are allowed
through `data/.gitignore`; raw inputs remain outside the repository. This approval
does not extend automatically to future datasets or source reports. Review future
inputs independently. Do not put school data in the public Pages `docs/` directory.
Application authentication does not protect Git files. Name-derived UUIDs and
content hashes are provenance, not anonymization. A custom `--output` elsewhere
needs the same privacy review. The JSON includes PDF aggregates for validation;
these are public under the same supplied-record authorization, not pitch records.

All explicitly named sources were found in the accessible `Downloads/Pitcher Stats`
directory: the CSV `OBU Pitchers 10-28-2026_03-02PM_Oklahoma Baptist University Baseball x ECU Fall 2026-2027 (5).csv`
and nine `oklaho-*-pitcher.pdf` files. The local validation JSON records the
individual report basenames and exact source associations, not a verified roster.
No additional unspecified “other supplied” reports can be verified without an
inventory. Nothing explicitly named in the request is missing.

## Regenerate locally

Use the existing Python 3.12 environment and existing requirements. There is no
network access or live Statcast retrieval in preparation. From the project root:

```sh
python scripts/prepare_obu_data.py --source /path/to/original.csv
```

The default output is `data/obu_pitching_cleaned.csv` plus
`data/obu_pitching_cleaned.validation.json`. Paths are configurable with `--output`;
no machine-specific source path is hardcoded. Inputs and outputs must differ.
Optional PDF validation uses one additional, isolated optional dependency:

```sh
python -m pip install -r requirements-obu-pdf.txt
python scripts/prepare_obu_data.py --source /path/to/original.csv --pdf-dir /path/to/reports
```

`pypdf==7.1.1` provides reproducible text extraction; it is not an application
runtime dependency. PDF extraction needs no OCR or plotting libraries. Missing
files, duplicate normalized headers, missing required columns, malformed CSV,
unsupported PDF layouts and ambiguous report association are fatal (CLI exit 2).
Validation finishes before output writing; failed validation leaves prior outputs
untouched. Filesystem write failures can leave partial artifacts; check exit status.

Do not infer a game date from a filename/export timestamp. CSV dates are missing
by default. The reports print October 28, 2026, but matching names alone do not
prove the CSV's full scope. After independently verifying file-wide event scope,
`--pitch-date YYYY-MM-DD` explicitly records reviewed file-level metadata. It is
not an original per-pitch date observation.

## Schema, types and source mappings

Schema version is `1`. All 30 inspected CSV columns are accounted for. Header
matching ignores case, spaces and punctuation; colliding headers are fatal.
`Pitcher`, `TaggedPitchType`, `RelSpeed` columns are required, even when optional
cell values are missing. Other absent columns are represented by missing values.
Unknown extra columns are listed in the validation JSON; original file hash and
record numbers retain traceability, but unknown values are not guessed into schema.

String columns are pandas nullable strings, numeric measurements nullable Float64,
and source/duplicate record numbers nullable Int64. Dates are validated ISO calendar
date strings (CSV has no date dtype or timezone). CSV empty cells mean unavailable,
never zero. Strings such as literal `NA` are preserved as text, not guessed nulls.
Read exported CSV with explicit dtypes/NA rules if literal source strings matter.

| Output | Source / definition |
| --- | --- |
| `schema_version` | Literal schema version, not an observation |
| `source_file`, `source_sha256` | Original basename and SHA256 of exact input bytes |
| `source_record` | 1-based CSV data-record ordinal, excluding header (not physical line number) |
| `observation_id` | File SHA256 plus colon and record ordinal; distinct even for repeated rows |
| `source_row_sha256` | SHA256 of sorted, compact Unicode JSON of the original header/value mapping |
| `pitcher_name_source`, `pitcher_name` | Original `Pitcher`; normalized NFC and collapsed whitespace; spelling/order/case preserved |
| `pitcher_id` | `obu-` + UUID5 URL namespace of `pap:obu:pitcher:` + normalized name; never MLBAM |
| `pitch_date`, `pitch_date_source` | Missing, or explicit reviewed ISO file date and `explicit_file_metadata` |
| `pitch_type` | Explicit standardized tagged classification, or missing |
| `duplicate_of_record` | First identical complete original record, or missing; duplicate is retained |
| `batter_name_source` | `Batter`, unchanged |
| `inning_half_source` | `Top/Bottom`, unchanged |
| `tagged_pitch_type_source`, `auto_pitch_type_source` | `TaggedPitchType`, `AutoPitchType`, independently preserved |
| `pitch_call_source`, `hit_type_source`, `play_result_source` | `PitchCall`, `HitType`, `PlayResult`; not translated to Statcast event codes |
| `obu_tilt_source` | `Tilt`, original clock-like text; not converted to degrees |

Numeric fields below preserve original numbers without rounding or conversion:

| Source | Output | Unit / interpretation |
| --- | --- | --- |
| `PAofInning` | `pa_of_inning` | count / inning ordinal |
| `PitchofPA` | `pitch_of_pa` | count / inning ordinal |
| `Inning` | `inning` | count / inning ordinal |
| `Outs` | `outs` | count / inning ordinal |
| `Balls` | `balls` | count / inning ordinal |
| `Strikes` | `strikes` | count / inning ordinal |
| `RelSpeed` | `obu_release_speed_mph` | mph, report heading corroborates scale; release plane unverified |
| `VertRelAngle` | `obu_vertical_release_angle_source` | original source units; definition/convention unverified |
| `HorzRelAngle` | `obu_horizontal_release_angle_source` | original source units; definition/convention unverified |
| `SpinRate` | `obu_spin_rate_source` | original source units; definition/convention unverified |
| `SpinAxis` | `obu_spin_axis_source` | original source units; definition/convention unverified |
| `RelHeight` | `obu_release_height_source` | original source units; definition/convention unverified |
| `RelSide` | `obu_release_side_source` | original source units; definition/convention unverified |
| `VertBreak` | `obu_vertical_break_source` | original source units; definition/convention unverified |
| `InducedVertBreak` | `obu_induced_vertical_break_source` | original source units; definition/convention unverified |
| `HorzBreak` | `obu_horizontal_break_source` | original source units; definition/convention unverified |
| `PlateLocHeight` | `obu_plate_height_source` | original source units; definition/convention unverified |
| `PlateLocSide` | `obu_plate_side_source` | original source units; definition/convention unverified |
| `ZoneSpeed` | `obu_zone_speed_source` | original source units; definition/convention unverified |
| `VertApprAngle` | `obu_vertical_approach_angle_source` | original source units; definition/convention unverified |
| `HorzApprAngle` | `obu_horizontal_approach_angle_source` | original source units; definition/convention unverified |

The source lacks a unique event/pitch key, a date, extension, release y-coordinate,
exit velocity and launch angle. Do not synthesize them from PDF summaries/charts.
Source inning/PA/pitch counters provide context but are not guaranteed unique.
IDs are stable for the same normalized name across row ordering and source files;
namesakes and spelling changes require a reviewed institutional identity crosswalk.
No names are fuzzy-matched or silently corrected.

## Classification and compatibility decisions

The explicit tagged mapping accepts only Fastball, Sinker, Cutter, Slider,
Curveball, Changeup and Splitter, ignoring case and surrounding whitespace.
Generic Fastball does not imply four-seam (`FF`). Unknown types remain in the raw
source column, standard type is missing, and a warning is recorded. Missing tagged
types remain unclassified; AutoPitchType never supplies a fallback. Tagged/auto
disagreements are counted independently. No usage statistics are calculated.

No current field is asserted Statcast-compatible. RelSpeed is on an mph scale
supported by the reports, but its release measurement plane/definition is not
verified equivalent to Savant release_speed. SpinRate is commonly rpm in tracking
exports, angles commonly degrees, release/location commonly feet and break commonly
inches; these are hypotheses, not source documentation. They deliberately retain
`_source` names. Obtain the exporter/vendor data dictionary before assigning units.

In particular, VertBreak and InducedVertBreak are distinct. Report movement is
labeled **pitcher's view**, location **catcher's view**; source CSV signs, coordinate
origin, gravity treatment and plate-reference plane remain unverified. No sign
flip or inches-to-feet conversion creates `pfx_x`, `pfx_z` or `plate_x/z`.
Statcast's 2026 plate-reference changes further prevent assuming equivalence.
No unit conversion is currently defensible or performed; tests assert exact numeric
preservation, including signed values/zero. Future conversions require independent
unit/convention evidence and dedicated accuracy tests. No new analytics formulas.

## Validation and reproducibility

Original source order is the deterministic output order; file hashes and ordinals
provide traceability. Repeated runs with identical bytes, metadata and PDF inputs
produce byte-identical CSV/JSON (no timestamps or absolute paths). Reordering or
renaming source input changes provenance as documented, not athlete identity.

Completely blank records and missing pitcher associations are rejected with ordinal
and reason; source count = output count + rejected count. Optional blanks remain
missing. Malformed/nonfinite numeric cells, nonpositive speeds, negative spin, and
invalid integral baseball counts become missing with field/record/reason warnings.
Counts: PA/pitch/inning >=1; outs 0–2, balls 0–3, strikes 0–2. No speculative upper
bounds on speeds or movement, no zero filling, and no deletion for missing metrics.
Duplicate detection compares complete original records, never just measurements;
identical candidates are marked and retained. This cannot establish duplication
across separately exported files. Repeated equal measurements are legitimate.

`validate_dataset` checks schema/order, numeric dtypes, finite/physical domains,
name-derived IDs, associations, classifications, ISO dates, SHA256 syntax, ordered
source records, unique observation IDs, duplicate pointers and row accounting.
The JSON reports actual counts: source/output/rejected records, distinct pitchers,
pitch classifications (including UNCLASSIFIED), missing values, duplicate count,
classification disagreement count, cell warnings, unmapped columns and PDF findings.
No aggregate denominator excludes missing optional measurements from pitch counts.
Review warnings/rejections and report scope before using output in analysis.

## PDF policy

All nine single-page reports were inspected by text extraction and rendering.
They contain pitcher/per-type counts, speed mean/max, strike/contact/count summaries,
spin/movement ranges and charts. These are aggregates, not additional pitch records.
A strict parser extracts only a single supported title and printed per-type count
and speed table. The total must reconcile with the table; each type must be unique.
Names associate only by exact case-insensitive, whitespace-normalized full name
(after reversing CSV `Last, First`). Unsupported/ambiguous reports fail explicitly.

Parsed summary values retain PDF basename, SHA256, printed date text, measurement
level and units/context in the validation JSON, never the pitch CSV. CSV per-type
counts and finite speed means/maxima are compared with printed values; speed
tolerance is 0.0500001 mph because PDFs print one decimal. Missing CSV types or
measurements are discrepancies. No deduplication, imputation, summary replication
or CSV enrichment follows. PDF-only aggregate metrics are not recalculated or
endorsed: their denominators/definitions are undocumented (one printed fly-ball
percentage even exceeds 100%). Charts are never sampled for exact values.

Actual reports have broader counts for eight of nine pitchers and differing speed
summaries; only one pitcher's total matches the CSV. The local JSON enumerates the
comparisons. These are unresolved sample-scope discrepancies, not proof of erroneous
CSV rows. No statistical equivalence or full outing coverage is asserted. Resolve
source export filters, missing classifications, identity/date scope and units before
Milestone 3.4. Public distribution of this supplied set is authorized. The current output is
ready for source review and a future OBU-specific adapter, not direct use with
the existing Statcast analytics contract. Review access/cache/export policies
for future restricted datasets before application integration.
