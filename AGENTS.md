# Project standards

- Keep work focused, straightforward, and maintainable. Use Python 3.12.
- Keep `app.py` focused on presentation. As functionality grows, separate data
  access, statistical calculations, and plotting into focused modules with clear
  interfaces. Avoid introducing unused abstractions.
- Never fabricate player records or statistics. Clearly distinguish missing data
  from zero values. Do not retrieve live data unless the task authorizes it.
- Document every statistical definition, unit, denominator, data source, filtering
  rule, and missing-value treatment alongside its implementation. Explain any
  deviation from a published baseball metric.
- Use pytest for meaningful coverage of calculations, data transformations, and
  edge cases. Keep a lightweight Streamlit smoke test. Tests should be deterministic
  and should not require network access or live Statcast downloads.
- Keep credentials in environment variables or local Streamlit secrets, never in
  tracked source, fixtures, logs, or screenshots. Confirm that any local secrets
  file is ignored before creating it. Do not commit credentials.
- Preserve `.gitignore` and the Git repository. Do not edit files inside `.venv`.
- Before code review, run relevant syntax and pytest checks and report results.
  Review changes for correctness, statistical validity, readability, data privacy,
  and unnecessary scope. Describe behavior changes and remaining limitations.
- Leave changes available for manual review. Do not commit or push unless asked.
