"""Text intake — extract structure from raw immunization text, no agent in the loop.

Takes raw text (clinic cards, portal printouts, shot records, pediatrician
notes) and pulls out vaccine names, dates, provider names, lot numbers, and
dose info using anchored regex against a closed vaccine set from
``reference.py``.  Pure extraction — never stores, never proposes, never
seals.  The caller decides what to keep.

The vaccine-name set is closed: only abbreviations from the CDC/ACIP pinned
snapshot (``reference.SCHEDULE.vaccines()``) are recognized.  This prevents
false positives from common English words ("flu", "shot") while catching the
standard abbreviations a clinic card or portal uses.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from homestead_health.reference import SCHEDULE

__all__ = ["Extracted", "extract"]


@dataclass(frozen=True)
class Extracted:
    """One item pulled from raw text."""

    kind: str
    text: str
    value: str
    start: int
    end: int
    field: str | None = None


# ── vaccine names (closed set from reference.py) ──────────────────────

_VACCINE_NAMES: tuple[str, ...] = SCHEDULE.vaccines()

_VACCINE_FULL: dict[str, str] = {
    "hepatitis b": "HepB",
    "hepatitis a": "HepA",
    "hep b": "HepB",
    "hep a": "HepA",
    "diphtheria": "DTaP",
    "tetanus": "Tdap",
    "pertussis": "DTaP",
    "rotavirus": "RV",
    "haemophilus influenzae": "Hib",
    "polio": "IPV",
    "pneumococcal": "PCV",
    "measles": "MMR",
    "mumps": "MMR",
    "rubella": "MMR",
    "chickenpox": "Varicella",
    "varicella": "Varicella",
    "human papillomavirus": "HPV",
    "meningococcal": "MenACWY",
    "influenza": "Influenza",
    "flu": "Influenza",
}

_ABBREV_RE = re.compile(
    r"\b(" + "|".join(re.escape(v) for v in sorted(_VACCINE_NAMES, key=len, reverse=True)) + r")\b"
)
_FULL_RE = re.compile(
    r"\b(" + "|".join(re.escape(k) for k in sorted(_VACCINE_FULL, key=len, reverse=True)) + r")\b",
    re.IGNORECASE,
)


# ── date patterns ───────────────────────────────────────────────

_MONTHS: dict[str, str] = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "jan": "01", "feb": "02", "mar": "03", "apr": "04",
    "jun": "06", "jul": "07", "aug": "08",
    "sep": "09", "sept": "09", "oct": "10", "nov": "11", "dec": "12",
}
_MONTH_RE = "|".join(sorted(_MONTHS, key=len, reverse=True))

_DATE_WRITTEN = re.compile(
    rf"\b(?P<month>{_MONTH_RE})\.?\s+(?P<day>\d{{1,2}}),?\s+(?P<year>\d{{4}})\b",
    re.IGNORECASE,
)
_DATE_ISO = re.compile(
    r"\b(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})\b",
)
_DATE_US = re.compile(
    r"\b(?P<month>\d{1,2})/(?P<day>\d{1,2})/(?P<year>\d{4})\b",
)


# ── provider patterns ──────────────────────────────────────────────

_PROVIDER_DR = re.compile(
    r"\b(?:Dr\.?|Doctor)[ \t]+([A-Z][a-zA-Z'-]+(?:[ \t]+[A-Z][a-zA-Z'-]+){0,2})\b"
)
_PROVIDER_CLINIC = re.compile(
    r"\b([A-Z][a-zA-Z'-]+(?:[ \t]+[A-Za-z'-]+){0,4})[ \t]+"
    r"(?:Clinic|Hospital|Medical[ \t]+Center|Pediatrics|Pharmacy|Health[ \t]+Center|"
    r"Medical[ \t]+Group|Children'?s[ \t]+Hospital)\b"
)
_PROVIDER_LABEL = re.compile(
    r"(?:Provider|Clinic|Administered[ \t]+by|Given[ \t]+at|Site)"
    r":?[ \t]([A-Z][a-zA-Z'.,-]*(?:[ \t][a-zA-Z'.,-]+)*)",
)


# ── lot number ───────────────────────────────────────────────────────────

_LOT = re.compile(
    r"(?:Lot|LOT)[ \t]*(?:#|No\.?|Number)?:?[ \t]([A-Z0-9][A-Z0-9-]{2,14})\b",
    re.IGNORECASE,
)


# ── dose info ──────────────────────────────────────────────────────────────

_DOSE_OF = re.compile(
    r"\b(?:dose|shot)[ \t]+(\d)[ \t]+(?:of|/)[ \t]+(\d)\b",
    re.IGNORECASE,
)
_DOSE_NTH = re.compile(
    r"\b(\d)(?:st|nd|rd|th)[ \t]+(?:dose|shot)\b",
    re.IGNORECASE,
)
_DOSE_BOOSTER = re.compile(
    r"\b(booster|annual|yearly)\b",
    re.IGNORECASE,
)


# ── extraction ─────────────────────────────────────────────────────────────

def _valid_date(year: int, month: int, day: int) -> bool:
    return 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100


def extract(text: str) -> list[Extracted]:
    """Extract structured items from raw immunization text, sorted by position."""
    items: list[Extracted] = []
    seen: set[tuple[int, int, str]] = set()

    def _add(
        kind: str, matched: str, value: str,
        start: int, end: int, field: str | None = None,
    ) -> None:
        key = (start, end, kind)
        if key not in seen:
            seen.add(key)
            items.append(Extracted(kind, matched, value, start, end, field))

    # Vaccine abbreviations (closed set)
    for m in _ABBREV_RE.finditer(text):
        _add("vaccine", m.group(), m.group(), m.start(), m.end(), "vaccine")

    # Vaccine full names → mapped to abbreviation
    for m in _FULL_RE.finditer(text):
        canonical = _VACCINE_FULL[m.group().lower()]
        _add("vaccine", m.group(), canonical, m.start(), m.end(), "vaccine")

    # ISO dates
    for m in _DATE_ISO.finditer(text):
        y, mo, d = int(m["year"]), int(m["month"]), int(m["day"])
        if _valid_date(y, mo, d):
            _add("date", m.group(), f"{y:04d}-{mo:02d}-{d:02d}",
                 m.start(), m.end(), "dose_date")

    # Written dates
    for m in _DATE_WRITTEN.finditer(text):
        mo_num = int(_MONTHS[m["month"].lower()])
        d, y = int(m["day"]), int(m["year"])
        if _valid_date(y, mo_num, d):
            _add("date", m.group(), f"{y:04d}-{mo_num:02d}-{d:02d}",
                 m.start(), m.end(), "dose_date")

    # US dates
    for m in _DATE_US.finditer(text):
        mo, d, y = int(m["month"]), int(m["day"]), int(m["year"])
        if _valid_date(y, mo, d):
            _add("date", m.group(), f"{y:04d}-{mo:02d}-{d:02d}",
                 m.start(), m.end(), "dose_date")

    # Provider — Dr. LastName
    for m in _PROVIDER_DR.finditer(text):
        _add("provider", m.group(), m.group(1), m.start(), m.end(), "provider")

    # Provider — Named Clinic/Hospital
    for m in _PROVIDER_CLINIC.finditer(text):
        _add("provider", m.group(), m.group().strip(), m.start(), m.end(), "provider")

    # Provider — label: Name
    for m in _PROVIDER_LABEL.finditer(text):
        _add("provider", m.group(), m.group(1).strip(), m.start(), m.end(), "provider")

    # Lot numbers
    for m in _LOT.finditer(text):
        _add("lot", m.group(), m.group(1), m.start(), m.end(), "lot_number")

    # Dose info — "dose 2 of 3"
    for m in _DOSE_OF.finditer(text):
        _add("dose", m.group(), f"dose {m.group(1)} of {m.group(2)}",
             m.start(), m.end())

    # Dose info — "1st dose"
    for m in _DOSE_NTH.finditer(text):
        _add("dose", m.group(), f"dose {m.group(1)}",
             m.start(), m.end())

    # Dose info — booster/annual
    for m in _DOSE_BOOSTER.finditer(text):
        _add("dose", m.group(), m.group().lower(),
             m.start(), m.end())

    items.sort(key=lambda e: e.start)
    return items
