# Pitch Analytics Platform

A professional MLB pitching analytics and scouting web application built with
Python 3.12, Streamlit, pandas, NumPy, pybaseball, and Plotly.

## Current milestone: 1.6 — Automated pitcher scouting reports

The dashboard preserves the Statcast pipeline and Milestone 1.3 arsenal summary,
and adds movement, plate locations, reference strike zones and local pitch-type
filtering. Milestone 1.5 adds the interactive pitch usage chart. Performance
metrics beyond descriptive swing/miss indicators remain future work.
No player records or measurements are fabricated.

## Milestone 1.6 scouting reports

Submit **Request data**, then scroll to **Pitcher scouting report**. The report
uses the loaded pitcher and inclusive dates, and all retrieved rows independently
of the movement/location filter. Editing the form does not change the loaded
report until submission. Every submission clears old results, including failures.
Choose **Download scouting report (HTML)** for a self-contained, escaped,
print-friendly report (browser Print → landscape). Its UTC generation timestamp
is fixed at successful retrieval and stays separate from deterministic analytics.
No additional retrieval, AI service or dependency is introduced. Existing charts
remain in their dashboard sections; the HTML export contains tables and text.

The report reuses `aggregate_pitch_arsenal` without changing its definitions,
source-code naming, sorting or classified usage denominator. It adds minimum
velocity (`release_speed`, mph), independent mean release coordinates
(`release_pos_x/y/z`, feet, source signs retained), and per-type valid measurement
counts for speed, spin, movement and release positions. Minimum/maximum velocity
are the observed range, not estimated percentiles. Required retrieval columns
remain unchanged; `release_spin_rate`, release positions, `description`, and
`player_name` are optional. A single unique nonblank source name is shown;
otherwise the name is explicitly unavailable and MLBAM ID identifies the report.
Unknown nonblank pitch codes remain separate types, without inferred names.

Whiff percentage is 100 × misses / recognized swings. Swing descriptions are
`swinging_strike`, `swinging_strike_blocked`, `foul_tip`, `foul`, `hit_into_play`,
`foul_bunt`, `missed_bunt`, and `bunt_foul_tip`. Misses are `swinging_strike`,
`swinging_strike_blocked`, and `missed_bunt`; foul tips are swings, not misses.
Other/missing descriptions are excluded; no recognized swings yields N/A.
This is a descriptive source-event ratio, not a claim of pitch effectiveness.
No command metric or predictive model is introduced.

Each mean uses its own finite sample. Missing columns, malformed optional
measurements, booleans, infinities and conversion overflows are unavailable,
never zero-filled. The report shows valid counts per type and valid/unavailable
counts across all rows for every measurement. Required-field retrieval validation
still rejects malformed responses. Descriptions outside the swing set can be
legitimate takes, unknown values or missing; a coverage note discloses this
limitation. No rows are silently removed from pitch counts. No returned rows
does not establish zero pitches thrown. Existing data source, game-type coverage,
30-day limit and measurement definitions below apply unchanged.

Observations describe observed arsenal size, highest/next usage (ties resolved
by source code), and the difference between fastest/slowest mean velocities
among types with at least **20 valid speed measurements each**. This is a
conservative operational threshold, not a significance test; smaller samples
suppress velocity comparisons. All reports caution about sample stability.
Automated observations are descriptive, not professional scouting grades,
player comparisons, pitch-quality scores or predictive assessments.

`scouting_report.py` separates report construction and observation rules from
rendering. `report_export.py` shares the formatted table between dashboard and
HTML, explicitly shows N/A, escapes external text, and includes full methodology,
data quality, source and sample counts. `tests/test_scouting_report.py` uses only
synthetic fixtures; `tests/test_app.py` covers report identity/date changes and
failed-request clearing. Run the full offline suite with `.venv/bin/python -m pytest -q`; use the
compilation and whitespace checks in **Validation** below. No static-analysis checker
is configured. Roadmap: milestones 1.3–1.5 analytics and 1.6 descriptive reports
are implemented; broader performance/command analytics remain future work.

## Milestone 1.5 pitch usage visualization

After loading records, **Pitch visualizations → Pitch usage** shows an interactive
Plotly horizontal bar chart, sorted by descending usage with pitch code ascending
for ties. Each bar displays the source pitch type, count, and percentage; hover
shows all three. Plotly provides zoom, pan, reset, and image export. Automatic
label margins and a height that grows with the number of types keep longer names
readable. Colors are assigned consistently by sorted classified pitch type
within the loaded usage summary.

The chart reuses the same `aggregate_pitch_arsenal` result as the arsenal table:
`usage_pct = 100 × pitch_count / total classified pitch rows`. Counts include
all loaded rows, beyond the 100-row preview, regardless of measurement availability.
Nonblank string classifications are whitespace-stripped and case-preserved;
no names are inferred, substituted, or mapped to a fixed whitelist. Unclassified
rows are reported separately beside the chart and excluded from its denominator.
No additional retrieval, deduplication, or game-type filtering occurs. The
movement/location selector does not filter usage or change its denominator.

Underlying percentages remain unrounded and sum to approximately 100%; labels
and hover round to one decimal, so displayed percentages may not total exactly
100%. Empty and entirely unclassified datasets show distinct messages without
division by zero. Missing or malformed measurements do not reduce usage counts;
upstream retrieval validation remains unchanged. Source: loaded Baseball Savant
Statcast rows via pybaseball. Usage describes only the requested dataset and its
source classifications, whose accuracy and coverage are not assessed. Small
samples do not establish stable tendencies or pitch effectiveness. Very long
source labels or narrow screens can require more display space.

## Milestone 1.4 methodology and usage

After requesting data, use **Pitch Movement & Location Analysis → Pitch types**.
All available normalized codes are selected initially. Select one or several
codes, or clear the selection for an explicit empty state. The filter updates
both charts and the movement summary using the full loaded dataset, without
another request. Every submitted request clears the filter, including failed
requests; the loaded pitcher/date caption identifies the active dataset.
Classification matches the arsenal's whitespace-stripped, case-preserved codes.
Unclassified rows are labeled separately and retain valid coordinate measurements.

Source definitions: [Baseball Savant CSV documentation](https://baseballsavant.mlb.com/csv-docs).
Horizontal movement is `pfx_x × 12`, in inches. Induced vertical movement is
`pfx_z × 12`, in inches: gravity-adjusted movement, not total physical vertical
displacement. Signed catcher-view coordinates are retained: positive horizontal
is right, negative left, and positive vertical is up. Neither chart mirrors
coordinates by pitcher handedness or labels movement arm-side/glove-side.

The movement table reports arithmetic means of independently valid horizontal
and vertical observations and their counts, plus the count with both coordinates.
Chart centroids use only those paired observations for BOTH means, so they may
differ from table values. Types with no paired measurements have no centroid.
All types remain in the summary with missing means and zero coverage where
appropriate; an empty dataset has no groups. Displayed means use one decimal;
calculations remain unrounded. These descriptive measurements alone do not
measure pitch quality or effectiveness. One pitch can be plotted but does not
establish a stable trend.

Locations use recorded `plate_x` and `plate_z` unchanged in feet. Both coordinates
must be valid; all such observations appear, with transparent markers to reduce
overplotting and counts in the legend. Equal physical axis scaling preserves
geometry. Movement and location availability are independent; either chart can
remain usable when the other has no observations.

Per the [official Baseball Savant CSV documentation](https://baseballsavant.mlb.com/csv-docs),
through 2025, `plate_x` and `plate_z` represent front-of-plate locations;
beginning in 2026, they represent middle-of-plate locations aligned with ABS.
Through 2025, `sz_top` and `sz_bot` use operator-defined strike-zone boundaries;
beginning in 2026, they use ABS-defined boundaries. Historical comparisons
spanning this transition require caution. PitcherIQ preserves source measurements
without artificially adjusting historical coordinates or boundaries.

Colors and marker symbols are assigned from the full loaded arsenal and remain
stable when filtering. When the 11-color palette repeats, marker symbols change
to distinguish pitch types; legends retain pitch-type names.

The dashed representative zone spans the physical 17-inch plate width,
`-17/24` to `+17/24` feet, with no baseball-radius expansion. Its bottom/top are
the respective medians from rows with finite same-row boundaries satisfying
`0 < sz_bot < sz_top` in the selected sample, regardless of location availability.
The legend identifies the boundary-pair count. If none exist, a clearly labeled
generic 1.5–3.5 ft reference is used. This rectangle is not every batter's exact
individualized zone and does not classify pitches as called strikes.

No deduplication or additional game-type filtering is applied. Every retrieved
row is an observation. Missing columns, nulls, nonfinite values, Booleans and
malformed scalar measurements are missing independently; valid zeros and signed
values are retained. Numeric strings follow existing arsenal conventions.
Overflow in feet-to-inches conversion is missing. Existing stricter upstream
retrieval validation remains unchanged. No live data is needed by tests.

Completed scope: movement calculations and coverage, paired-centroid chart,
location chart and representative zone, stable within-dataset colors, pitch-type
filtering, empty states, offline regression coverage and documentation. Predictive scoring remains out of scope; descriptive reports are added in 1.6.

## Data retrieval usage

Enter a positive MLBAM pitcher ID (not a player name), select start/end dates,
and click **Request data**. Both endpoints are included: April 1–30 is the
maximum 30-day window. Reversed or longer ranges are rejected before retrieval.
No data is fetched on page load or while editing the form. Each loaded preview
is labeled with its submitted pitcher and dates. A failed request clears the
previous preview and arsenal summary so old records cannot be mistaken for new
results. After a successful request, scroll to **Pitch Arsenal** for the per-type
table and unclassified pitch count. Reruns reuse the loaded records; arsenal
calculations make no additional Statcast requests.

Data comes from Baseball Savant through pybaseball 2.2.7's installed
`statcast_pitcher(start_dt=None, end_dt=None, player_id=None)` API, called with
ISO date strings and an integer ID. Successful validated, nonempty responses
are cached by normalized ID and dates with Streamlit for one hour (maximum
64 entries, shared across app sessions). Empty results and errors are not
cached and can be retried by submitting again.

Required columns: `game_date`, `pitcher`, `pitch_type`, `release_speed`, `pfx_x`,
and `pfx_z`. Speed is in mph and movement in feet, as supplied by Statcast.
Missing pitch types and measurements remain missing, never zero-filled.
Missing identity/date fields, duplicate columns, invalid numeric measurements,
and rows outside the requested identity/date scope reject the response.
All extra columns and upstream row order are preserved in the retrieved data;
no deduplication or additional game-type filtering is applied. Arsenal aggregation
is performed separately without changing those records. Record count is
the number of returned rows, not a derived performance metric.

## Pitch arsenal aggregation

`pitch_arsenal.aggregate_pitch_arsenal(validated_data)` is a pure, offline
calculation layer used directly by the dashboard. It returns a
`PitchArsenalResult` with a `metrics` DataFrame and `unclassified_pitch_count`.
The table contains pitch counts, usage percentages, mean/maximum velocity
(mph), mean spin rate (rpm), and signed mean horizontal/vertical movement
(inches, converted from Statcast feet by multiplying by 12).

Nonblank string pitch codes are stripped of surrounding whitespace and grouped
without a fixed whitelist. Missing, blank, and non-string codes are counted as
unclassified and excluded from the usage denominator. Usage is each type's
count divided by all classified pitches, multiplied by 100. Each mean uses its
own available finite measurement count as its denominator;
maximum velocity uses the available finite speeds. Optional `release_spin_rate`
is supplied by Statcast in rpm. Each measurement is handled independently;
missing columns and malformed values
produce missing metrics rather than zeros. Rows sort by count descending, then
pitch code ascending. Empty inputs produce an empty table with the same schema.
Entirely unclassified data shows an explanatory message instead of an arsenal
table. Missing measurements do not reduce pitch counts or usage. No arm-side or
gravity adjustment is applied to movement; these direct `pfx_x`/`pfx_z` summaries
are not total break metrics. The function docstring documents the full statistical
and defensive-input contract.

Display formatting preserves the underlying numeric precision: counts use
thousands separators, usage uses one decimal place and a percent sign (values
already range from 0 to 100), velocity uses one decimal place, spin uses whole
rpm, and movement uses one decimal place with an explicit sign. Rounded usage
may not sum to exactly 100%. Installed Streamlit 1.67.0 supports these formats;
AppTest verifies their configuration, but final table rendering, separators,
percent signs, signed movement, and missing-value appearance need manual browser
verification.

## Known limitations

- Internet access and Baseball Savant availability are required for retrieval.
  Upstream schema changes or service errors may prevent loading; the UI provides
  a retry message without exposing raw upstream error details.
- ID validation checks syntax only (up to 10 digits), not player existence.
  Unknown IDs, future dates, off-season windows, and coverage gaps may return no
  records. Empty results do not establish that a pitcher threw zero pitches.
- pybaseball includes regular season, postseason, and spring games. Data coverage
  and measurement availability vary; this milestone does not assess completeness.
- Data may remain stale for up to one hour. There is no persistent local dataset,
  automatic retry, or application-level timeout; request duration depends on
  pybaseball and the upstream service.
- Automated validation uses synthetic fixtures and mocks, with no live downloads.

## macOS setup

Install Python 3.12 if it is not already available, then open Terminal:

```sh
cd ~/Developer/pitch-analytics-platform
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

If `.venv` already exists and uses Python 3.12, skip the environment creation
command and activate it directly. Dependencies are pinned to the versions in the
existing project environment.

## Run locally

From the project directory with the virtual environment activated:

```sh
python -m streamlit run app.py
```

Open the local URL printed by Streamlit (normally `http://localhost:8501`).
Stop the server with Control-C. Run `deactivate` to leave the virtual environment.

## Validation

```sh
python -m py_compile app.py statcast_service.py statcast_validation.py pitch_arsenal.py pitch_movement.py pitch_plots.py tests/test_app.py tests/test_statcast.py tests/test_pitch_arsenal.py tests/test_pitch_movement.py tests/test_pitch_usage.py
python -m pytest -q
python -m compileall -q -x '(^|/)(\.venv|\.git)/' .
git diff --check
```

The smoke test uses Streamlit's `AppTest` to render the dashboard without a
browser or network access. Interaction tests cover loaded summaries, repeat
requests, missing measurements, unclassified data, use of all rows beyond the
preview, and stale-data removal after failed requests. Aggregation tests cover
independent measurement denominators, signed conversions, deterministic sorting,
and input preservation. Tests block requests-based HTTP and mock retrieval.
GitHub Actions runs the same offline suite on Python 3.12.

## Project files

- `app.py`: Streamlit dashboard entry point.
- `requirements.txt`: Six direct runtime and test dependencies.
- `statcast_service.py`: Pitcher API access and successful-result caching.
- `statcast_validation.py`: Request and response validation contracts.
- `pitch_arsenal.py`: Pure per-pitch-type scouting metrics and unclassified count.
- `tests/test_pitch_arsenal.py`: Offline aggregation and validation integration tests.
- `tests/test_app.py`: Offline dashboard smoke and interaction tests.
- `tests/test_statcast.py`: Synthetic validation and mocked API/cache tests.
- `AGENTS.md`: Architecture, statistical documentation, security, and review standards.

- `pitch_movement.py`: Pure coordinate preparation, filtering, movement summary and zone reference.
- `pitch_plots.py`: Plotly usage, movement and equal-scale location figures.
- `tests/test_pitch_movement.py`: Synthetic calculation, validity and chart-geometry coverage.
- `tests/test_pitch_usage.py`: Offline usage counts, ordering, empty states and label coverage.
See `AGENTS.md` before contributing.
