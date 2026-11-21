"""Generate an Argon2id hash without accepting passwords in arguments or stdin."""

from getpass import GetPassWarning, getpass
from pathlib import Path
import sys
import warnings

# Allow `python scripts/generate_password_hash.py` from the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from authentication import MAX_PASSWORD_BYTES, PASSWORD_HASHER  # noqa: E402


def main() -> int:
    if len(sys.argv) != 1:
        print("Run without arguments; passwords must be entered at the hidden prompt.", file=sys.stderr)
        return 1
    try:
        with warnings.catch_warnings():
            # getpass normally falls back to echoed stdin if no terminal exists.
            warnings.simplefilter("error", GetPassWarning)
            password = getpass("New coach password: ")
            confirmation = getpass("Confirm password: ")
        if not password or len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
            print("Use a nonempty password of at most 1024 UTF-8 bytes.", file=sys.stderr)
            return 1
        if password != confirmation:
            print("Passwords did not match.", file=sys.stderr)
            return 1
        print(PASSWORD_HASHER.hash(password))
    except (EOFError, KeyboardInterrupt, GetPassWarning):
        print("A secure interactive terminal is required; generation cancelled.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
