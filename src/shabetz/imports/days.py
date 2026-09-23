"""Reading working days as people actually write them in a spreadsheet.

Weekdays use Python's numbering, which the rest of the system stores: Monday
is 0 and Sunday is 6.

Accepted, in English or Hebrew, in any mix:

- full names and common abbreviations: ``Sunday``, ``Sun``, ``Su``, ``ראשון``
- Hebrew day letters, with or without a geresh: ``א``, ``א'``, ``יום א``
- ranges with a dash or a word: ``Sun-Thu``, ``א-ה``, ``ראשון עד חמישי``
- the whole week: ``all``, ``every day``, ``כל השבוע``

Plain numbers are refused on purpose. Whether ``1`` means Sunday (as in Israel
and Excel's default) or Monday (as in ISO) depends on who typed it, and
guessing wrong silently gives everyone the wrong days.
"""

from __future__ import annotations

import re

MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY, SATURDAY, SUNDAY = range(7)

_NAMES: dict[str, int] = {}


def _register(day: int, *names: str) -> None:
    for name in names:
        _NAMES[name] = day


_register(MONDAY, "monday", "mon", "mo", "שני", "ב")
_register(TUESDAY, "tuesday", "tue", "tues", "tu", "שלישי", "ג")
_register(WEDNESDAY, "wednesday", "wed", "we", "רביעי", "ד")
_register(THURSDAY, "thursday", "thu", "thur", "thurs", "th", "חמישי", "ה")
_register(FRIDAY, "friday", "fri", "fr", "שישי", "ו")
_register(SATURDAY, "saturday", "sat", "sa", "שבת", "ש")
_register(SUNDAY, "sunday", "sun", "su", "ראשון", "א")

_WHOLE_WEEK = {"all", "every day", "everyday", "daily", "כל השבוע", "כל יום", "כל הימים", "הכל"}

# Geresh and gershayim, typographic and ASCII, as in א' or יום א׳.
_GERESH = re.compile("[\"'׳״’`]")
_RANGE = re.compile(r"\s*(?:-|–|—|\bto\b|\bעד\b)\s*")
# A lone "ו" is Friday, so Hebrew "and" is only recognised as a prefix ("ושני").
_SEPARATORS = re.compile(r"\s+and\s+|\s+")


class DaysError(ValueError):
    """The text could not be read as working days."""


def _day(token: str) -> int:
    token = _GERESH.sub("", token).strip().lower().removesuffix(".")
    # "יום א" and "יום ראשון" are both natural; the word adds nothing.
    token = token.removeprefix("יום").strip()
    if token in _NAMES:
        return _NAMES[token]
    # A leading ו is "and" when what follows is a day on its own ("ושני").
    if token.startswith("ו") and token[1:] in _NAMES and len(token) > 2:
        return _NAMES[token[1:]]
    raise DaysError(token)


def _span(first: int, last: int) -> list[int]:
    """Days from ``first`` to ``last`` inclusive, wrapping past the week's end."""
    return [(first + offset) % 7 for offset in range((last - first) % 7 + 1)]


def parse_weekdays(text: str) -> list[int]:
    """Parse ``text`` into sorted weekday numbers.

    Raises ``DaysError`` for anything unrecognised rather than dropping it:
    a silently ignored day is a person scheduled when they cannot come.
    """
    cleaned = " ".join(text.split()).strip()
    if not cleaned:
        raise DaysError(text)
    if cleaned.lower() in _WHOLE_WEEK:
        return list(range(7))

    days: set[int] = set()
    # "יום" before a letter is a prefix, never a separator; join it first so
    # "יום א, יום ב" splits into two days rather than four tokens.
    joined = re.sub(r"יום\s+", "יום", cleaned)
    for part in re.split(r"[,;/|+&\n]+", joined):
        part = part.strip()
        if not part:
            continue
        pieces = _RANGE.split(part)
        if len(pieces) == 2 and pieces[0] and pieces[1]:
            days.update(_span(_day(pieces[0]), _day(pieces[1])))
            continue
        for token in _SEPARATORS.split(part):
            if token:
                days.add(_day(token))
    return sorted(days)
