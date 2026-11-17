# Pitch Analytics Platform

A professional MLB pitching analytics and scouting web application built with
Python 3.12, Streamlit, pandas, NumPy, pybaseball, and Plotly.

## Current milestone: 1.2 — Statcast pitching data pipeline

The dashboard retrieves pitcher-level Statcast records on explicit request and
shows a record count and the first 100 rows. Performance metrics and pitch
visualizations remain placeholders; no baseball statistics are fabricated.

## Data retrieval usage

Enter a positive MLBAM pitcher ID (not a player name), select start/end dates,
and click **Request data**. Both endpoints are included: April 1–30 is the
maximum 30-day window. Reversed or longer ranges are rejected before retrieval.
No data is fetched on page load or while editing the form. Each loaded preview
is labeled with its submitted pitcher and dates. A failed request clears the
previous preview so old records cannot be mistaken for new results.

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
All extra columns and upstream row order are preserved; no aggregation,
deduplication, or additional game-type filtering is applied. Record count is
the number of returned rows, not a derived performance metric.

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
python -m py_compile app.py statcast_service.py statcast_validation.py tests/test_app.py tests/test_statcast.py
python -m pytest -q
```

The smoke test uses Streamlit's `AppTest` to render the dashboard without a
browser or network access and checks the initial empty state.

## Project files

- `app.py`: Streamlit dashboard entry point.
- `requirements.txt`: Six direct runtime and test dependencies.
- `statcast_service.py`: Pitcher API access and successful-result caching.
- `statcast_validation.py`: Request and response validation contracts.
- `tests/test_app.py`: Offline dashboard smoke and interaction tests.
- `tests/test_statcast.py`: Synthetic validation and mocked API/cache tests.
- `AGENTS.md`: Architecture, statistical documentation, security, and review standards.

Statistical calculations and plotting modules will be added as those features
are implemented. See `AGENTS.md` before contributing.
