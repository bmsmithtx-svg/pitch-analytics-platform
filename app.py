"""Streamlit entry point for the Pitch Analytics Platform."""

import streamlit as st


def main() -> None:
    """Render the application foundation without retrieving player data."""
    st.set_page_config(
        page_title="Pitch Analytics Platform",
        page_icon="⚾",
        layout="wide",
    )

    with st.sidebar:
        st.header("Pitcher selection")
        st.selectbox(
            "Pitcher",
            options=[],
            placeholder="Pitcher selection coming soon",
            disabled=True,
        )
        st.caption("Pitcher and date filters will be available when data is connected.")

    st.title("Pitch Analytics Platform")
    st.write(
        "Professional MLB pitching analytics and scouting insights, "
        "powered by Statcast data."
    )
    st.info("Application foundation • No player data is loaded or retrieved.")

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
