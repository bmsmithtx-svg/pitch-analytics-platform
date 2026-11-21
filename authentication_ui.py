"""Native Streamlit login screen and server-side authorization gate."""

import streamlit as st

from authentication import (
    Account, FAILURE_MESSAGE, LOGIN_LIMITER, load_accounts,
)


def clear_session() -> None:
    """Revoke identity and drop all session-owned analytics, reports and widgets.

    Shared MLB data caches retain their existing behavior; they are not rendered
    or callable through the dashboard until this session authenticates again.
    """
    for key in list(st.session_state):
        del st.session_state[key]


def submit_login(accounts: dict[str, Account]) -> None:
    """Run before widgets render; discard password fields after every attempt."""
    username = st.session_state.get("login_username", "")
    password = st.session_state.get("login_password", "")
    clear_session()
    if LOGIN_LIMITER.authenticate(accounts, username, password):
        st.session_state["_pap_identity"] = (username, accounts[username].revision)
    else:
        st.session_state["_pap_login_error"] = FAILURE_MESSAGE


def require_authentication() -> None:
    """Stop before any dashboard workflow, including on direct URL access.

    Identity is a non-widget server-side session entry, never a URL parameter or
    cookie. Revalidate enabled status and password revision on every rerun.
    """
    try:
        accounts = load_accounts(st.secrets["credentials"])
    except Exception:
        # Streamlit can raise for absent files, malformed TOML or missing keys.
        # Fail closed without rendering/logging the exception or secret material.
        clear_session()
        st.title("Pitch Analytics Platform")
        st.error("Sign in is unavailable. Please contact the application administrator.")
        st.stop()

    identity = st.session_state.get("_pap_identity")
    if isinstance(identity, tuple) and len(identity) == 2:
        username, revision = identity
        account = accounts.get(username) if isinstance(username, str) else None
        if account is not None and account.enabled and account.revision == revision:
            st.sidebar.button("Logout", key="logout", on_click=clear_session, width="stretch")
            return

    # No protected state may survive a missing, disabled or replaced identity.
    # Keep only login widget values so form submission can be processed.
    for key in list(st.session_state):
        if key not in {"login_username", "login_password", "sign_in", "_pap_login_error"}:
            del st.session_state[key]
    st.title("Pitch Analytics Platform")
    st.caption("MLB pitch analytics and scouting · Authorized coach access")
    with st.container(border=True):
        st.header("Sign in")
        with st.form("coach_sign_in", clear_on_submit=True):
            st.text_input("Username", key="login_username", max_chars=128)
            st.text_input("Password", type="password", key="login_password", max_chars=1024)
            st.form_submit_button(
                "Sign In", key="sign_in", type="primary", width="stretch",
                on_click=submit_login, args=(accounts,),
            )
        if st.session_state.pop("_pap_login_error", None):
            st.error(FAILURE_MESSAGE)
    st.caption("Use credentials issued by the administrator. Closing or refreshing "
               "the session may require signing in again.")
    st.stop()
