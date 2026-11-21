"""Server-side password verification and bounded, process-local login throttling.

Only throttle counters are shared between sessions. No authenticated identity is
kept here. All time intervals use monotonic seconds, independent of wall clocks.
"""

from base64 import b64decode, b64encode
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256
import re
import secrets
from threading import Lock
from time import monotonic
from typing import Callable, NoReturn

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from argon2.low_level import Type

# RFC 9106 low-memory profile: 64 MiB, 3 iterations, 4 lanes, 16-byte salt,
# 32-byte output. Pin the profile so configuration cannot request unbounded work.
PASSWORD_HASHER = PasswordHasher(
    time_cost=3, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16, type=Type.ID,
)
_HASH = re.compile(r"\$argon2id\$v=19\$m=65536,t=3,p=4\$([A-Za-z0-9+/]{22})\$([A-Za-z0-9+/]{43})")
MAX_USERNAME = 128
MAX_PASSWORD_BYTES = 1024
FAILURE_MESSAGE = "Unable to sign in. Check your credentials or try again later."


class AuthenticationConfigError(ValueError):
    """Configuration is unavailable or invalid; never include secret values."""


@dataclass(frozen=True, repr=False)
class Account:
    password_hash: str
    enabled: bool

    @property
    def revision(self) -> str:
        """Opaque server-side marker; password replacement revokes old sessions."""
        return sha256(self.password_hash.encode()).hexdigest()


def load_accounts(config: object) -> dict[str, Account]:
    """Validate the entire [credentials.users] mapping; reject partial configs.

    Usernames are case-sensitive, nonempty, at most 128 characters, and cannot
    have surrounding whitespace. Only the administrator utility's hash profile
    is accepted. Disabled accounts still require a well-formed hash. No enabled
    accounts is an unavailable configuration, rather than an anonymous mode.
    """
    def invalid() -> NoReturn:
        raise AuthenticationConfigError("Authentication configuration unavailable.")

    if not isinstance(config, Mapping) or set(config) != {"users"}:
        invalid()
    users = config["users"]
    if not isinstance(users, Mapping) or not users or len(users) > 1024:
        invalid()
    result = {}
    for username, value in users.items():
        if (not isinstance(username, str) or not username
                or username != username.strip() or len(username) > MAX_USERNAME
                or not isinstance(value, Mapping)
                or set(value) != {"password_hash", "enabled"}):
            invalid()
        encoded = value["password_hash"]
        enabled = value["enabled"]
        match = _HASH.fullmatch(encoded) if isinstance(encoded, str) else None
        if match is None or not isinstance(enabled, bool):
            invalid()
        # Reject noncanonical trailing base64 bits, not just the textual shape.
        assert match is not None
        for part in match.groups():
            decoded = b64decode(part + "=" * (-len(part) % 4), validate=True)
            if b64encode(decoded).decode().rstrip("=") != part:
                invalid()
        result[username] = Account(encoded, enabled)
    if not any(account.enabled for account in result.values()):
        invalid()
    return result


@dataclass
class _Attempts:
    failures: int
    expires: float


class LoginLimiter:
    """Serialize verification and bound failures, memory, and hashing work.

    Five failures for any supplied username within 300 seconds block that name
    until its fixed 300-second window ends. All names, including unknown ones,
    use identical counters. At most 50 verifications total per fixed 60-second
    window and 1024 tracked names. When full, new names fail closed; unexpired
    entries are never evicted. A lock covers check + verify + update to prevent
    concurrent attempts bypassing limits and to bound Argon2 memory to one hash.
    Restarts reset counters; instances do not share them. This is not durable or
    distributed brute-force protection. Anonymous traffic can deny login service.
    """

    def __init__(self, clock: Callable[[], float] = monotonic) -> None:
        self._clock = clock
        self._lock = Lock()
        self._attempts: dict[str, _Attempts] = {}
        self._global_count = 0
        self._global_expires = 0.0
        self._dummy_hash: str | None = None

    def authenticate(self, accounts: Mapping[str, Account], username: str, password: str) -> bool:
        """Verify through Argon2's API; unknown/disabled users verify a dummy hash."""
        if (not isinstance(username, str) or not isinstance(password, str)
                or len(username) > MAX_USERNAME
                or len(password.encode("utf-8")) > MAX_PASSWORD_BYTES):
            return False
        key = sha256(username.encode()).hexdigest()
        with self._lock:
            now = self._clock()
            self._attempts = {k: v for k, v in self._attempts.items() if v.expires > now}
            if now >= self._global_expires:
                self._global_count = 0
                self._global_expires = now + 60
            attempt = self._attempts.get(key)
            if (self._global_count >= 50 or (attempt is not None and attempt.failures >= 5)
                    or (attempt is None and len(self._attempts) >= 1024)):
                return False
            self._global_count += 1
            if self._dummy_hash is None:
                self._dummy_hash = PASSWORD_HASHER.hash(secrets.token_urlsafe(32))
            account = accounts.get(username)
            usable = account is not None and account.enabled
            encoded = account.password_hash if usable and account is not None else self._dummy_hash
            try:
                verified: bool = PASSWORD_HASHER.verify(encoded, password)
            except VerificationError:
                verified = False
            if usable and verified:
                self._attempts.pop(key, None)
                return True
            if attempt is None:
                attempt = _Attempts(0, now + 300)
                self._attempts[key] = attempt
            attempt.failures += 1
            return False


# Module lifetime spans Streamlit reruns; only bounded throttle state is shared.
LOGIN_LIMITER = LoginLimiter()
