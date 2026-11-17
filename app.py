"""Streamlit entry point for the Pitch Analytics Platform."""

from datetime import date, timedelta

import streamlit as st

from statcast_service import get_pitcher_statcast
from statcast_validation import NoStatcastDataError, StatcastError


def main() -> None:
    """Render the dashboard and retrieve data only after explicit submission."""
    st.set_page_config(
        page_title="Pitch Analytics Platform",
        page_icon="⚾",
        layout="wide",
    )

    with st.sidebar:
        st.header("Pitcher selection")
        with st.form("statcast_request"):
            pitcher_id = st.text_input("MLBAM pitcher ID", key="pitcher_id")
            start_date = st.date_input("Start date", value=date.today() - timedelta(days=29))
            end_date = st.date_input("End date", value=date.today())
            submitted = st.form_submit_button("Request data")
        st.caption("Maximum 30 days, including both endpoints. Data loads only on request.")

    st.title("Pitch Analytics Platform")
    st.write(
        "Professional MLB pitching analytics and scouting insights, "
        "powered by Statcast data."
    )
    st.header("Statcast data")
    if submitted:
        # Clear the previous result so a failed request cannot show stale rows.
        st.session_state.pop("statcast_result", None)
        st.session_state.pop("statcast_message", None)
        try:
            with st.spinner("Retrieving Statcast data…"):
                data = get_pitcher_statcast(pitcher_id, start_date, end_date)
            st.session_state["statcast_result"] = (pitcher_id.strip(), start_date, end_date, data)
        except NoStatcastDataError as exc:
            st.session_state["statcast_message"] = ("info", str(exc))
        except StatcastError as exc:
            st.session_state["statcast_message"] = ("error", str(exc))

    if "statcast_message" in st.session_state:
        level, message = st.session_state["statcast_message"]
        getattr(st, level)(message)
    elif "statcast_result" in st.session_state:
        loaded_id, loaded_start, loaded_end, data = st.session_state["statcast_result"]
        st.caption(f"Loaded pitcher {loaded_id}: {loaded_start} through {loaded_end} (inclusive).")
        st.metric("Statcast records", len(data))
        st.dataframe(data.head(100), hide_index=True, alt="Preview of the first 100 retrieved Statcast records")
        st.caption("Preview limited to 100 rows. Missing measurements remain missing; no statistics are calculated.")
    else:
        st.info("No player data is loaded or retrieved. Submit a request to load Statcast records.")

    st.header("Performance metrics")
    st.caption("Pitching performance summaries will appear here once data is available.")
    st.info("No performance metrics available yet.")

    st.header("Pitch visualizations")
    movement, usage = st.columns(2)
    with movement:
        st.subheader("Pitch movement")
        st.info("Pitch movement charts will appear here.")
    with usage:
        st.subheader("Pitch usage")
        st.info("Pitch type distributions will appear here.")


if __name__ == "__main__":
    main()
