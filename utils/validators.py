"""Input validation for the CRUD module.

Three layers protect the data: the form (Streamlit widgets), these validators
(clear messages, ALL problems at once), and finally the database constraints
(the last line of defence). Validators never touch the database.
"""

from datetime import date
from typing import Any, Optional

ROLES = (
    "Batsman",
    "Bowler",
    "Allrounder",
    "Batting Allrounder",
    "Bowling Allrounder",
    "WK-Batsman",
)
BATTING_STYLES = ("Right-hand bat", "Left-hand bat")
PLAYER_FIELDS = (
    "full_name",
    "display_name",
    "country",
    "playing_role",
    "batting_style",
    "bowling_style",
    "date_of_birth",
    "birth_place",
)
BATTING_EDITABLE = (
    "runs",
    "balls_faced",
    "fours",
    "sixes",
    "batting_position",
    "is_not_out",
    "out_desc",
)
EARLIEST_BIRTH = date(1940, 1, 1)


class ValidationError(ValueError):
    """One or more fields are invalid. ``errors`` maps field name -> message."""

    def __init__(self, errors: dict):
        self.errors = errors
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))


def _blank(value: Any) -> bool:
    return value is None or (isinstance(value, str) and not value.strip())


def _text(data, key, errors, max_len, required=False, choices=None) -> Optional[str]:
    value = data.get(key)
    if _blank(value):
        if required:
            errors[key] = "is required"
        return None
    text = str(value).strip()
    if len(text) > max_len:
        errors[key] = f"must be at most {max_len} characters"
    elif choices is not None and text not in choices:
        errors[key] = f"must be one of: {', '.join(choices)}"
    elif required and len(text) < 2:
        errors[key] = "must be at least 2 characters"
    return text


def _int(data, key, errors, low, high, required=False) -> Optional[int]:
    value = data.get(key)
    if _blank(value):
        if required:
            errors[key] = "is required"
        return None
    if isinstance(value, bool):
        value = int(value)
    try:
        number = float(value)
    except (TypeError, ValueError):
        errors[key] = "must be a whole number"
        return None
    if number != int(number):
        errors[key] = "must be a whole number"
        return None
    number = int(number)
    if not low <= number <= high:
        errors[key] = f"must be between {low} and {high}"
        return None
    return number


def _date(data, key, errors) -> Optional[str]:
    value = data.get(key)
    if _blank(value):
        return None
    try:
        parsed = value if isinstance(value, date) else date.fromisoformat(str(value))
    except ValueError:
        errors[key] = "must be a date like 1990-04-27"
        return None
    if parsed > date.today():
        errors[key] = "cannot be in the future"
    elif parsed < EARLIEST_BIRTH:
        errors[key] = f"cannot be before {EARLIEST_BIRTH.isoformat()}"
    return parsed.isoformat()


def validate_player(data: dict, partial: bool = False) -> dict:
    """Clean a player form. ``partial=True`` checks only the keys that are present."""
    errors: dict = {}
    unknown = set(data) - set(PLAYER_FIELDS)
    for key in unknown:
        errors[key] = "is not an editable player field"
    clean: dict = {}
    for key in PLAYER_FIELDS:
        if partial and key not in data:
            continue
        if key == "full_name":
            clean[key] = _text(data, key, errors, 100, required=True)
        elif key == "display_name":
            clean[key] = _text(data, key, errors, 40)
        elif key in ("country", "bowling_style"):
            clean[key] = _text(data, key, errors, 60)
        elif key == "birth_place":
            clean[key] = _text(data, key, errors, 80)
        elif key == "playing_role":
            clean[key] = _text(data, key, errors, 30, choices=ROLES)
        elif key == "batting_style":
            clean[key] = _text(data, key, errors, 30, choices=BATTING_STYLES)
        elif key == "date_of_birth":
            clean[key] = _date(data, key, errors)
    if errors:
        raise ValidationError(errors)
    return clean


def validate_batting(data: dict, partial: bool = False) -> dict:
    """Clean a batting-performance form, including cross-field rules."""
    errors: dict = {}
    spec = {
        "match_id": (1, 10**9, True),
        "innings_no": (1, 4, True),
        "player_id": (1, 10**9, True),
        "team_id": (1, 10**9, True),
        "batting_position": (1, 11, False),
        "runs": (0, 500, True),
        "balls_faced": (0, 600, False),
        "fours": (0, 100, False),
        "sixes": (0, 100, False),
    }
    allowed = set(spec) | {"is_not_out", "out_desc"}
    for key in set(data) - allowed:
        errors[key] = "is not a batting field"
    clean: dict = {}
    for key, (low, high, required) in spec.items():
        if partial and key not in data:
            continue
        clean[key] = _int(data, key, errors, low, high, required and not partial)
    if not partial or "is_not_out" in data:
        flag = data.get("is_not_out", 0)
        if flag in (None, "", 0, 1, True, False, "0", "1"):
            clean["is_not_out"] = 1 if flag in (1, True, "1") else 0
        else:
            errors["is_not_out"] = "must be yes or no"
    if not partial or "out_desc" in data:
        clean["out_desc"] = _text(data, "out_desc", errors, 120)

    runs, fours, sixes = clean.get("runs"), clean.get("fours"), clean.get("sixes")
    balls = clean.get("balls_faced")
    if runs is not None and (fours or sixes):
        if (fours or 0) * 4 + (sixes or 0) * 6 > runs:
            errors["runs"] = "fours and sixes alone add up to more than the runs"
    if balls is not None and (fours or 0) + (sixes or 0) > balls:
        errors["balls_faced"] = "fewer balls than boundaries is impossible"
    if errors:
        raise ValidationError(errors)
    return clean
