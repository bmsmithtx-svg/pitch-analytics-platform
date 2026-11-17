# Pitch Analytics Platform

A professional MLB pitching analytics and scouting web application built with
Python 3.12, Streamlit, pandas, NumPy, pybaseball, and Plotly.

## Current milestone: 1.3 — Pitch arsenal analytics (Task 1.3.3)

The dashboard retrieves pitcher-level Statcast records on explicit request and
shows a record count, the first 100 rows, and a pitch arsenal summary calculated
from the full retrieved dataset. Milestone 1.3 functionality is implemented and
prepared for final review and milestone closure. Performance metrics and pitch
visualizations remain placeholders; no baseball statistics are fabricated.

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
python -m py_compile app.py statcast_service.py statcast_validation.py pitch_arsenal.py tests/test_app.py tests/test_statcast.py tests/test_pitch_arsenal.py
python -m pytest -q
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

Plotting modules will be added as those features are implemented.
See `AGENTS.md` before contributing.
