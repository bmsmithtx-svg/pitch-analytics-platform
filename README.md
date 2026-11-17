# Pitch Analytics Platform

A professional MLB pitching analytics and scouting web application built with
Python 3.12, Streamlit, pandas, NumPy, pybaseball, and Plotly.

## Current milestone: 1.1 — Application Foundation

The dashboard includes placeholders for pitcher selection, performance metrics,
and pitch movement and usage visualizations. It does not load player data,
retrieve live Statcast data, or display invented statistics.

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
python -m py_compile app.py tests/test_app.py
python -m pytest -q
```

The smoke test uses Streamlit's `AppTest` to render the dashboard without a
browser or network access and checks the initial empty state.

## Project files

- `app.py`: Streamlit dashboard entry point.
- `requirements.txt`: Six direct runtime and test dependencies.
- `tests/test_app.py`: Offline dashboard smoke test.
- `AGENTS.md`: Architecture, statistical documentation, security, and review standards.

Data access, statistical calculations, and plotting modules will be added as
those features are implemented. See `AGENTS.md` before contributing.
