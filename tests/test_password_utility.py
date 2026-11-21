"""The administrator utility never accepts a password in arguments or echo mode."""

from getpass import GetPassWarning
from unittest.mock import Mock

import pytest

from authentication import PASSWORD_HASHER
from scripts import generate_password_hash as utility


@pytest.mark.parametrize("password,confirmation", [
    ("", ""), ("one-test-password", "different-test-password"), ("é" * 513, "é" * 513),
])
def test_rejects_empty_mismatched_or_oversized_passwords(monkeypatch, capsys, password, confirmation):
    monkeypatch.setattr("sys.argv", ["generate_password_hash.py"])
    monkeypatch.setattr(utility, "getpass", Mock(side_effect=[password, confirmation]))
    assert utility.main() == 1
    output = capsys.readouterr()
    assert not output.out
    assert "$argon2" not in output.err
    if password:
        assert password not in output.err


def test_rejects_command_line_password_without_prompt(monkeypatch, capsys):
    prompt = Mock()
    monkeypatch.setattr("sys.argv", ["generate_password_hash.py", "synthetic-password"])
    monkeypatch.setattr(utility, "getpass", prompt)
    assert utility.main() == 1
    prompt.assert_not_called()
    assert "synthetic-password" not in capsys.readouterr().err


@pytest.mark.parametrize("error", [GetPassWarning, EOFError, KeyboardInterrupt])
def test_no_unsafe_stdin_fallback(monkeypatch, capsys, error):
    monkeypatch.setattr("sys.argv", ["generate_password_hash.py"])
    monkeypatch.setattr(utility, "getpass", Mock(side_effect=error))
    assert utility.main() == 1
    output = capsys.readouterr()
    assert not output.out
    assert "secure interactive terminal" in output.err


def test_generates_distinct_salted_argon2id_hashes(monkeypatch, capsys):
    password = "synthetic-password-for-utility-test"
    monkeypatch.setattr("sys.argv", ["generate_password_hash.py"])
    monkeypatch.setattr(utility, "getpass", Mock(return_value=password))
    hashes = []
    for _ in range(2):
        assert utility.main() == 0
        encoded = capsys.readouterr().out.strip()
        assert encoded.startswith("$argon2id$v=19$m=65536,t=3,p=4$")
        assert PASSWORD_HASHER.verify(encoded, password)
        assert password not in encoded
        hashes.append(encoded)
    assert hashes[0] != hashes[1]
