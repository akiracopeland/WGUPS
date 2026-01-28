"""util.py

Small, shared helpers used across the project.

This project intentionally uses the Python standard library only.
"""

from __future__ import annotations

from datetime import datetime, timedelta, time
import re


def parse_deadline(s: str) -> time | None:
    """Parse the deadline field from the packages CSV.

    - Returns a `datetime.time` for concrete deadlines (e.g., '10:30', '10:30 AM').
    - Returns None for 'EOD' / 'End of Day' style deadlines.

    We keep the parsing forgiving because the input CSVs are often exported from Excel.
    """
    s = (s or '').strip().upper()
    if s in {'EOD', 'END OF DAY'}:
        return None

    try:
        if 'AM' in s or 'PM' in s:
            return datetime.strptime(s, '%I:%M %p').time()
        return datetime.strptime(s, '%H:%M').time()
    except Exception:
        # If a deadline can't be parsed, treat it like EOD.
        return None


def hhmm(dt: datetime) -> str:
    """Format a datetime as HH:MM (24-hour)."""
    return dt.strftime('%H:%M')


def miles_to_minutes(miles: float, mph: float) -> int:
    """Convert miles at mph to whole minutes (rounded).

    The rubric allows approximations. Rounding keeps the simulation deterministic.
    """
    return int(round((miles / mph) * 60.0))


def add_minutes(dt: datetime, mins: int) -> datetime:
    """Return dt + mins minutes."""
    return dt + timedelta(minutes=mins)


def time_to_minutes(t: time) -> int:
    """Convert a `time` to minutes since midnight."""
    return t.hour * 60 + t.minute


# -------------------------
# Input normalization helpers
# -------------------------

_NON_ALNUM = re.compile(r'[^a-z0-9 ]+')


def normalize_text(s: str) -> str:
    """Normalize a string for loose matching.

    We use this to match package addresses to location names in the distance table.
    """
    s = (s or '').lower()
    s = s.replace('\n', ' ').replace('\r', ' ')
    s = _NON_ALNUM.sub(' ', s)           # drop punctuation (commas, periods, etc.)
    s = re.sub(r'\s+', ' ', s).strip()  # collapse whitespace
    return s


def address_key(address: str) -> str:
    """Create a normalized key from a street address string."""
    return normalize_text(address)
