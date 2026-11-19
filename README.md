# Pitch Analytics Platform

A professional MLB pitching analytics and scouting web application built with
Python 3.12, Streamlit, pandas, NumPy, pybaseball, and Plotly.

## Current milestone: 2.5 — Responsive design and accessibility

The dashboard preserves the Statcast pipeline and Milestone 1.3 arsenal summary,
and adds movement, plate locations, reference strike zones and local pitch-type
filtering. Milestone 1.5 adds the interactive pitch usage chart. Performance
metrics beyond descriptive swing/miss indicators remain future work.
No player records or measurements are fabricated.

## Navigation and analysis workflow

Use the shared sidebar to select a pitcher and analysis dates, then choose
**Generate analysis**. The active name (when available), MLB ID and inclusive
dates appear above four native Streamlit tabs:

1. **Pitcher Analysis**: workflow guidance, record count and an
   expandable preview of the first 100 rows.
2. **Pitch Arsenal**: the per-type metric table and unclassified pitch count.
3. **Visualizations**: movement, locations, pitch-type filtering and pitch usage.
4. **Scouting Report**: choose **Generate scouting report**, review the preview
   with observations, sample/data-quality notes and methodology, then choose
   **Download scouting report (HTML)**.

Navigation preserves the pitcher, loaded rows, chart filter, report timestamp
and selected tab without another MLB lookup or Statcast request. Presentations
use the same loaded dataset. The movement/location filter does not change usage,
arsenal metrics or reports. The sidebar remains accessible from every tab;
on narrow screens Streamlit collapses it behind its sidebar toggle, and the
native tab strip can scroll horizontally. Charts use available container width.
No custom frontend or new dependency is introduced.

**Changed in 2.2:** date edits now immediately clear prior results and reports,
just like pitcher changes. Editing controls never downloads data; choose
**Generate analysis** to load the new request. Failed and empty requests clear
previous results and offer a retry path. Missing data is never displayed as zero.
Initial and selected-but-not-generated states explain the next action; spinners
identify name lookup and Statcast retrieval, and successful analysis is labeled.
The former placeholder performance sections have been removed.

## Pitcher search by name

Choose **Name search**, enter a name, and click **Search**. A single exact full-name
match (ignoring case and normalized whitespace) resolves its MLB ID automatically.
Duplicate full names and all partial matches require an explicit choice from
**Matching players**, even if there is only one partial result. Labels show only
available team, position, activity and birth-date metadata, ending with MLB ID.
Historical, inactive and two-way players are included; results are people, not a
verified list of pitchers. Select the intended identity before requesting data.

Names accept Unicode letters, accents, spaces, apostrophes, periods and hyphens;
use 2–100 characters. After selection, choose dates and click **Generate analysis**.
Search and selection never download Statcast data. Changing the query, selection
mode or effective pitcher clears prior analytics and reports to prevent stale
identity displays. Date edits clear the loaded analysis and report immediately.

For the independent fallback, choose **Manual ID**, expand
**Advanced: Enter MLB Player ID manually**, and enter the numeric ID. This works
without a successful search. If MLB search is unavailable, retry, wait after a
rate-limit message, or use manual entry. No API key is needed. A resolved name ID
uses the same validated retrieval path as manual entry: analytics definitions,
charts, scouting rules, HTML export and the inclusive 30-day limit are unchanged.

Lookup source: MLB Stats API `https://statsapi.mlb.com/api/v1/people/search`, using
encoded `names` query parameters. An isolated live check on 2026-11-18 returned
HTTP 200 and a `people` array including integer `id`, `fullName`, `birthDate`,
`active`, and `primaryPosition.name` (verified with a two-way player). Team metadata
is optional and not guaranteed. No active-only or primary-position filter is used.
Malformed records fail the entire lookup rather than silently hiding candidates.
Repeated IDs retain one deterministic whole record, preferring more metadata;
distinct IDs with the same name remain separate choices.

Successful searches (including empty results) use a shared one-hour cache bounded
to 64 normalized names. Network/HTTP failures, rate limits, invalid JSON and invalid
records are never cached. Each lookup makes at most one request with 5-second
connection and 15-second read timeouts; retries are explicit. Lookup metadata may
be stale for up to an hour and does not guarantee Statcast coverage. Automated
lookup and selection tests use deterministic identity fixtures and mocked HTTP.

## Milestone 1.6 scouting reports

Submit **Generate analysis**, then open **Scouting Report** and choose
**Generate scouting report**. Review the **Report preview**, including identity,
dates, arsenal, observations and coverage disclosures. The report
uses the loaded pitcher and inclusive dates, and all retrieved rows independently
of the movement/location filter. Editing dates or changing pitcher identity
clears the loaded report immediately. Every submission clears old results,
including failures.
Choose **Download scouting report (HTML)** for a self-contained, escaped,
print-friendly report (browser Print → landscape). Its UTC generation timestamp
is fixed at successful report generation and stays separate from deterministic analytics.
The download section appears only after report generation and HTML export succeed.
Filenames include the available source name, MLBAM ID and inclusive dates, using
filesystem-safe characters. Generation failures remove the preview/download and
allow retry from the same valid analysis. New or failed analysis requests, invalid
inputs, pitcher changes and date edits remove the report and download; generate
a new analysis and report for the new selection. Tab navigation and chart filters
preserve the completed report without recalculation.

At least one retrieved row is required. Missing classifications or measurements
retain the existing limited-data report and coverage warnings; they are never
filled with zero or used to invent observations. Names appear only when the source
contains a single unambiguous name; otherwise the report identifies the pitcher
by MLBAM ID. No additional retrieval, AI service or dependency is introduced. Existing charts
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

After loading records, **Visualizations → Pitch usage** shows an interactive
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

After requesting data, open **Visualizations → Pitch Movement & Location Analysis → Pitch types**.
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

Use name search or enter a positive MLBAM pitcher ID in Manual ID mode, select dates,
and click **Generate analysis**. Both endpoints are included: April 1–30 is the
maximum 30-day window. Reversed or longer ranges are rejected before retrieval.
No data is fetched on page load, during navigation or while editing controls.
Each loaded preview is labeled with its submitted pitcher and dates. A failed request clears the
previous preview and arsenal summary so old records cannot be mistaken for new
results. After a successful request, open **Pitch Arsenal** for the per-type
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
python -m py_compile *.py tests/*.py
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

- `app.py`: Streamlit dashboard entry point and bounded identity-search cache.
- `pitcher_search.py`: Independent MLB identity validation, lookup, parsing and resolution.
- `tests/test_pitcher_search.py`: Offline query, response, resolution, HTTP and cache coverage.
- `tests/test_pitcher_selection.py`: Offline identity workflow and stale-selection coverage.
- `requirements.txt`: Pinned direct runtime and test dependencies (including requests for MLB identity lookup).
- `statcast_service.py`: Pitcher API access and successful-result caching.
- `statcast_validation.py`: Request and response validation contracts.
- `pitch_arsenal.py`: Pure per-pitch-type scouting metrics and unclassified count.
- `tests/test_pitch_arsenal.py`: Offline aggregation and validation integration tests.
- `tests/test_app.py`: Offline dashboard smoke and interaction tests.
- `tests/test_navigation.py`: Offline navigation persistence, date invalidation, expired selections and request-provenance tests.
- `tests/test_statcast.py`: Synthetic validation and mocked API/cache tests.
- `AGENTS.md`: Architecture, statistical documentation, security, and review standards.

- `pitch_movement.py`: Pure coordinate preparation, filtering, movement summary and zone reference.
- `pitch_plots.py`: Plotly usage, movement and equal-scale location figures.
- `tests/test_pitch_movement.py`: Synthetic calculation, validity and chart-geometry coverage.
- `tests/test_pitch_usage.py`: Offline usage counts, ordering, empty states and label coverage.
See `AGENTS.md` before contributing.

## Milestone 2.3 dashboard presentation

The existing four tabs and sidebar workflow are preserved. Bordered record and
unclassified-count cards clarify their denominators. **Pitch Arsenal → Arsenal
metrics** offers All metrics, Usage, Velocity and spin, and Movement views of the
same unrounded aggregate. Focused column views reduce table width on smaller
screens; empty measurement cells indicate unavailable values, while valid zeros
remain zero. The complete table remains the default.

Movement and location charts now stack in separate panels, giving each the full
available width. A labeled movement coverage table distinguishes independent
measurement means from paired chart centroids. Plotly charts share readable
hover text, sentence-case axes with explicit units, automatic axis margins, and
horizontal legends. Usage bars retain count/percentage text in addition to color.
All charts use the same full-dataset pitch-code color map, including when
unclassified rows have coordinates; movement/location symbols and labels remain
available alongside colors. Source pitch codes are preserved without inferred
pitch names. Tables may still scroll internally when the full metric view or
long source codes exceed the available width.

These are presentation changes only: retrieval, caching, 30-day validation,
statistical definitions, chart filtering, report generation/HTML export and
stale-result guards remain unchanged. No new dependency or live-data request is
introduced by presentation controls.

## Milestone 2.5 responsive design and accessibility

The four native tabs retain their state and use a shorter **Pitcher Analysis**
label. On narrow screens, open the top-left sidebar toggle for pitcher/date
controls and scroll the tab strip (or use its arrow controls) for later sections.
Search, analysis, report generation and download buttons fill their available
width. Arsenal metric choices stack vertically; pitch-code columns stay pinned
while the arsenal and movement tables scroll internally. The complete arsenal
view remains the default, with focused metric views available on smaller screens.

Charts explicitly stretch to their containers, retain 14px base/hover text and
automatic axis margins, and reserve more space for wrapping legends. Large
legends scroll within a bounded area. Usage labels keep a 12px minimum; labels
that cannot fit are hidden rather than shrunk, with exact counts/percentages
available in tooltips and the arsenal table. Pitch-code labels, legends and the
existing symbols supplement consistent colors. The report preview uses a
360px-high native table with sticky headers and internal scrolling; observations,
notes and downloads remain outside it. Exported HTML is unchanged.

Native labeled widgets, heading structure, accessible chart/table names and
default keyboard focus styling are preserved. No custom CSS, frontend or new
dependency is added. Retrieval, caching, calculations, report generation and
stale-result invalidation are unchanged.

Manual Chrome responsive inspection on 2026-11-19 used synthetic offline UI
fixtures at 1440px, 768px and 390px widths in the existing dark theme. Navigation,
context, charts, tables and report previews were readable without observed
page-wide overflow; mobile sidebar controls and the download button were usable.
Arrow-key tab navigation and a visible focus indicator were checked. AppTest and
the running Streamlit agent API cover report persistence and invalidation.
This is a limited visual review, not a WCAG evaluation: screen-reader operation,
all keyboard paths, other browsers/themes, physical touch devices and unusually
long source labels or large arsenals have not been exhaustively evaluated.
Dense tables still require internal scrolling, and Plotly tooltips remain
pointer-oriented; chart names alone are not full text alternatives for every
individual pitch location.

## Milestone 3.1 — Web Deployment

**Repository implementation is prepared; production application deployment is
pending.** The launch action intentionally remains unavailable until a verified
hosted URL is configured. No analytics, report content, or data rules changed.

Architecture: coaching staff → GitHub Pages (`docs/`) → Streamlit Community Cloud
(`app.py`, Python 3.12) → existing PAP modules → MLB Stats API / Baseball Savant.
Pages serves static files only; Python runs on Community Cloud. The two sites
are linked directly, with no iframe, proxy, database, or frontend framework.

### Compatibility and runtime requirements

The 3.1 audit started from clean `main` at `e077144` with annotated tag `v2.5`
incorporated and 302 offline tests passing on Python 3.12.16. There was no GitHub
Release entry for that tag. The repository was already public. GitHub Pages was
already enabled from `main` `/`; use `/docs` for this milestone.

Community Cloud supports Python 3.12 and root `requirements.txt` installation.
Keep the existing exact dependency pins; no additional runtime dependency or
OS package was identified. Linux installation is checked by GitHub Actions;
actual Cloud dependency installation remains a deployment acceptance check.
No environment variables, secrets, credentials, local datasets, or external
storage are required for the current public MLB workflows. Do not add a
`runtime.txt`: select Python **3.12** in the Cloud deployment form.

Outbound HTTPS is required to `statsapi.mlb.com` for name search and
`baseballsavant.mlb.com` through pybaseball for Statcast. Deployment does not
prove either endpoint is reachable from the hosting region. MLB search retains
its connection/read timeouts; Statcast retains upstream-dependent request
duration without an application timeout. Existing error messages, manual ID
fallback, inclusive 30-day limit, and validation remain intact.

Session state is per browser session; reloads, disconnects, service restarts, or
sleep/wake can discard selections and reports. Successful results are cached
in memory for one hour, bounded to 64 entries per existing cache, shared across
users. Caches are not persistent storage. Reports and HTML downloads are built
in memory and downloaded to the coach's device, without writing report files
on the server. No application feature requires a persistent writable filesystem.
The pinned dependency stack may use temporary runtime files; do not treat those
as durable storage. Community Cloud resources are limited and apps may sleep;
concurrent workloads and upstream delays can affect availability. This is not
an availability-guaranteed hosting service.

### Deploy the Python application (administrator)

1. Sign in at [Streamlit Community Cloud](https://share.streamlit.io/) using
   an account authorized for this repository. Complete any GitHub account
   authorization yourself; do not paste tokens into the repository or site.
2. In the `bmsmithtx-svg` workspace choose **Create app**, then the existing-app
   option. Set repository `bmsmithtx-svg/pitch-analytics-platform`, branch `main`,
   main file path `app.py`. Do this after the milestone PR is merged.
3. In **Advanced settings**, select Python **3.12**. Leave secrets empty for
   current functionality. Deploy and watch the build logs for dependency errors.
4. Open the assigned app URL. Verify name search, player confirmation, Manual ID,
   an available historical date window of at most 30 days, analysis, all four
   tabs, chart filters, scouting report preview and HTML download. Confirm
   changing pitcher/dates invalidates stale analysis. Live retrieval is a
   deliberate acceptance check, separate from offline tests; a successful page
   load alone does not validate it.
5. Copy the actual HTTPS URL only after these checks. No Streamlit deployment
   URL is assumed in this repository.

Official maintenance references: [deployment and Python selection](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy),
[dependency installation](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies),
[sharing and privacy](https://docs.streamlit.io/deploy/streamlit-community-cloud/share-your-app).

### Configure and publish the entry website

1. Edit **only** `globalThis.PAP_APP_URL` in `docs/config.js` to the verified
   HTTPS app URL, preserving the quotes. Do not use a URL containing credentials,
   query parameters, or a fragment. This file is public configuration, never a
   place for secrets. Commit through a reviewed PR to `main`.
2. In GitHub **Settings → Pages → Build and deployment**, choose **Deploy from a
   branch**, branch **main**, folder **/docs**, then **Save**. Preserve repository
   visibility and existing HTTPS/security settings. No Actions write permissions
   or custom domain are needed. See [GitHub publishing source instructions](https://docs.github.com/en/pages/getting-started-with-github-pages/configuring-a-publishing-source-for-your-github-pages-site).
3. Wait for Pages deployment to finish. The existing Pages URL is
   <https://bmsmithtx-svg.github.io/pitch-analytics-platform/>. Verify that it
   displays the PAP entry page and the launch link reaches the verified app.
4. Share the Pages URL with coaches. They need a browser and internet access,
   with no Python installation or GitHub use. For a private app, they also need
   the hosting service's viewer sign-in and an administrator-issued invitation.

An empty, malformed, non-HTTPS, or credential-bearing configuration leaves the
launch control without an `href` and displays the unavailable message. Script
load failures also leave it disabled. Without JavaScript, the page explains
how to obtain the app URL from the administrator. The URL check validates
format, not remote availability: the administrator must verify the destination.
No URL may be overridden by a query string or visitor input.

### Security and access

Only `index.html`, `styles.css`, `config.js`, `launch.js`, and `.nojekyll` belong
in `docs/`. Do not copy Python source, reports, secrets, CSVs, school datasets,
or local files into that directory. Tests enforce this publishing boundary.
The Streamlit server does not enable static file serving or the development
agent API. CORS and XSRF protections retain their defaults. Local
`.streamlit/secrets.toml` is ignored; confirm with `git check-ignore` before
creating one. No secrets file is required or provided.

The current repository and Pages site are public. A public repository's
Community Cloud app is public by default. The landing page is not an access
control, and hiding a launch URL does not secure an app. Community Cloud can
restrict an app to specific invited viewers who sign in; its documented limit
is one private app at a time. Account access and school requirements must
be assessed before selecting a restricted setup. No visibility, viewer access,
or security setting should be changed without owner approval. Public MLB data
is the only data in scope here; Oklahoma Baptist University records are excluded.
Before later school-data work, independently review repository exposure,
shared caches, report downloads, hosting authorization, and school policy.

### Updates, troubleshooting, and acceptance

Merge tested application changes into `main`; Community Cloud redeploys the
connected branch automatically. Dependency changes trigger installation. Use
its logs to investigate failures and reboot from its management interface if
needed. Select a supported Python version when deploying; changing it later
requires redeployment under the provider's current instructions. Pages rebuilds
from `main` `/docs`; URL changes require editing `docs/config.js` and merging.
Roll back through a reviewed Git revert rather than rewriting release history.

- **Unavailable launch:** inspect `docs/config.js`, ensure an HTTPS URL without
  credentials/query/fragment, and check that both scripts load successfully.
- **Old page or 404:** verify Pages source is `main` `/docs`, the Pages build
  completed, and refresh the browser cache. Keep `.nojekyll` in the directory.
- **Cloud build failure:** verify repository/branch/entrypoint, Python 3.12,
  pinned dependency installation, and logs. Do not silently upgrade packages.
- **Sleeping or slow app:** wait for startup; inspect Cloud resource usage and
  logs. Retry an upstream failure or narrow the date window. Manual ID avoids
  name-search failures, but still requires Statcast availability.
- **Empty records:** verify pitcher ID, dates, and upstream coverage; missing
  data does not establish zero pitches. Existing user-facing errors apply.
- **Lost session/report:** reselect inputs and regenerate after a restart or
  disconnect. Save downloaded reports locally when needed.
- **Access denied:** have the owner review the Cloud sharing configuration and
  viewer invitation; changing the Pages page does not grant app access.

Run the existing Python validation commands above plus `node tests/deployment.cjs`
(Node 22; built-in modules only). CI runs offline pytest and those JavaScript
checks. Deployment tests inspect the intended static files, local references,
unique anchors, disabled initial link, HTTPS destination handling, and server
configuration. Existing AppTest workflows retain search, retrieval, charts,
reports, state and invalidation coverage. There is no configured mypy project
check; an optional checker invocation should report its flags and limitations.

Before announcing production availability, inspect desktop/tablet/mobile layouts,
keyboard navigation, the configured launch destination, and the full hosted
workflow above. Also verify an unauthorized viewer is denied if a restricted
app is chosen. Hosting account setup, actual app URL configuration, live MLB
connectivity, report download behavior remotely, and coach access remain manual
acceptance tasks until explicitly recorded as verified. Repository release/tag
publication alone does not mean the service is deployed.
