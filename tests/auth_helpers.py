"""Synthetic credentials and real login workflow for offline AppTest regressions."""

from pathlib import Path
from functools import lru_cache

from streamlit.testing.v1 import AppTest

from authentication import PASSWORD_HASHER

# Explicitly synthetic, never valid production credentials.
TEST_USERNAME = "synthetic-coach"
TEST_PASSWORD = "synthetic-only-test-password"


@lru_cache(maxsize=1)
def test_credentials() -> dict:
    return {"credentials": {"users": {
        TEST_USERNAME: {"password_hash": PASSWORD_HASHER.hash(TEST_PASSWORD), "enabled": True},
        "synthetic-second": {"password_hash": PASSWORD_HASHER.hash("second-test-password"), "enabled": True},
    }}}


def login(app: AppTest, username: str = TEST_USERNAME, password: str = TEST_PASSWORD) -> AppTest:
    app.text_input(key="login_username").set_value(username)
    app.text_input(key="login_password").set_value(password)
    return app.button(key="sign_in").click().run(timeout=10)


def new_app() -> AppTest:
    app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / "app.py"))
    app.secrets.update(test_credentials())
    return app


def authenticated_app() -> AppTest:
    """Inject test secrets, then authenticate through the production login form."""
    app = login(new_app().run(timeout=10))
    assert not app.exception
    assert app.sidebar.button(key="logout")
    return app
