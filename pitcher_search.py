"""MLB identity lookup only; no Streamlit, Statcast or analytics dependencies.

Source: HTTPS MLB Stats API /api/v1/people/search?names=... . Verified live
2026-11-18: object containing a people list, integer id, fullName, optional
birthDate, active and primaryPosition.name (including Two-Way Player).
No active/position filters: historical and incomplete identities remain eligible.
"""

from dataclasses import dataclass
from datetime import date
import re
import unicodedata

import requests

ENDPOINT = "https://statsapi.mlb.com/api/v1/people/search"


class PitcherSearchError(Exception):
    """Actionable lookup failure, distinct from a successful empty result."""


class SearchValidationError(PitcherSearchError):
    """Invalid query or identity."""


class SearchResponseError(PitcherSearchError):
    """Unusable upstream schema or JSON; never cache."""


def normalize_query(query: str) -> str:
    """NFC names, 2–100 characters after whitespace folding; no controls.

    Unicode letters/combining marks, spaces, apostrophes, periods and hyphens
    are allowed. Case is preserved for display and casefolded only for matching.
    """
    if not isinstance(query, str) or any(unicodedata.category(c).startswith("C") for c in query):
        raise SearchValidationError("Enter a name without control characters.")
    value = " ".join(unicodedata.normalize("NFC", query).split())
    if not 2 <= len(value) <= 100 or not any(c.isalpha() for c in value):
        raise SearchValidationError("Enter a player name between 2 and 100 characters.")
    if any(not (unicodedata.category(c)[0] in "LM" or c in " '.-’") for c in value):
        raise SearchValidationError("Use letters, spaces, apostrophes, periods or hyphens in the name.")
    return value


def validate_player_id(value: object) -> int:
    """Positive ASCII integer, at most 10 digits, matching the retrieval contract."""
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise SearchValidationError("MLB player ID must be a positive integer.")
    text = str(value)
    if not re.fullmatch(r"[0-9]{1,10}", text) or int(text) <= 0:
        raise SearchValidationError("MLB player ID must be a positive integer.")
    return int(text)


@dataclass(frozen=True)
class PlayerCandidate:
    player_id: int
    full_name: str
    team_name: str | None = None
    position: str | None = None
    active: bool | None = None
    birth_date: str | None = None

    def label(self) -> str:
        """Only supplied metadata, ending with the unambiguous MLB ID."""
        parts = [self.full_name]
        parts.extend(v for v in (self.team_name, self.position) if v is not None)
        if self.active is not None:
            parts.append("Active" if self.active else "Inactive")
        if self.birth_date:
            parts.append(f"Born {self.birth_date}")
        return " · ".join(parts + [f"MLB ID {self.player_id}"])


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip() or any(
        unicodedata.category(c).startswith("C") for c in value
    ):
        raise SearchResponseError("MLB search returned invalid metadata. Retry or enter an ID manually.")
    return value.strip()


def _nested_name(record: dict, field: str) -> str | None:
    value = record.get(field)
    if value is None:
        return None
    if not isinstance(value, dict):
        raise SearchResponseError("MLB search returned invalid metadata. Retry or enter an ID manually.")
    return _optional_text(value.get("name"))


def parse_candidates(payload: object) -> tuple[PlayerCandidate, ...]:
    """Validate the whole response; never disguise malformed records as no matches.

    Duplicate IDs retain one whole record: prefer more supplied metadata, then
    lexical field order. Do not merge conflicting metadata or invent values.
    Results sort by casefolded name, original name, then numeric MLB ID.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("people"), list):
        raise SearchResponseError("MLB search returned an unexpected response. Retry or enter an ID manually.")
    candidates = []
    for record in payload["people"]:
        try:
            if not isinstance(record, dict):
                raise ValueError
            player_id = validate_player_id(record.get("id"))
            name = normalize_query(record.get("fullName"))
            active = record.get("active")
            if active is not None and not isinstance(active, bool):
                raise ValueError
            birthday = _optional_text(record.get("birthDate"))
            if birthday is not None and date.fromisoformat(birthday).isoformat() != birthday:
                raise ValueError
            candidates.append(PlayerCandidate(player_id, name, _nested_name(record, "currentTeam"),
                                               _nested_name(record, "primaryPosition"), active, birthday))
        except (ValueError, TypeError, SearchValidationError) as exc:
            raise SearchResponseError("MLB search returned an invalid player record. Retry or enter an ID manually.") from exc

    def duplicate_key(candidate: PlayerCandidate) -> tuple:
        values = (candidate.team_name, candidate.position, candidate.active, candidate.birth_date)
        return (-sum(v is not None for v in values), candidate.full_name,
                tuple("" if v is None else str(v) for v in values))

    unique: dict[int, PlayerCandidate] = {}
    for candidate in sorted(candidates, key=duplicate_key):
        unique.setdefault(candidate.player_id, candidate)
    return tuple(sorted(unique.values(), key=lambda c: (c.full_name.casefold(), c.full_name, c.player_id)))


def exact_matches(query: str, candidates: tuple[PlayerCandidate, ...]) -> tuple[PlayerCandidate, ...]:
    name = normalize_query(query).casefold()
    return tuple(c for c in candidates if normalize_query(c.full_name).casefold() == name)


def resolve_candidate(query: str, candidates: tuple[PlayerCandidate, ...]) -> PlayerCandidate | None:
    """Only a unique exact name auto-resolves; even one partial needs selection."""
    matches = exact_matches(query, candidates)
    if len(matches) == 1:
        validate_player_id(matches[0].player_id)
        return matches[0]
    return None


def fetch_candidates(query: str) -> tuple[PlayerCandidate, ...]:
    """One request, finite connect/read timeouts (5/15 seconds), no retries.

    HTTP, timeout, connection, JSON and schema failures raise distinct actionable
    messages. Empty people is a valid success; no imports perform network I/O.
    """
    query = normalize_query(query)
    try:
        response = requests.get(ENDPOINT, params={"names": query}, timeout=(5, 15))
        if response.status_code == 429:
            raise PitcherSearchError("MLB search is rate limited. Wait and retry, or enter an ID manually.")
        response.raise_for_status()
    except requests.Timeout as exc:
        raise PitcherSearchError("MLB search timed out. Retry or enter an ID manually.") from exc
    except requests.HTTPError as exc:
        raise PitcherSearchError("MLB search returned an HTTP error. Retry or enter an ID manually.") from exc
    except requests.RequestException as exc:
        raise PitcherSearchError("Cannot connect to MLB search. Retry or enter an ID manually.") from exc
    try:
        payload = response.json()
    except ValueError as exc:
        raise SearchResponseError("MLB search returned invalid JSON. Retry or enter an ID manually.") from exc
    return parse_candidates(payload)
