"""Dose records — an immunization the household enters itself, keyed by subject.

This is the record the rest of the module was built to consume and nothing had
yet written: the school form composes *"that subject's immunization records,
already gathered"*, the Today line counts *next dose* dates, and the pack
classifies the fields — but until now the only writer was a `put` that filed one
field under a random id, which no reader could find. This module is the writer,
and the reader that finds them by subject.

## One record per dose, composed to its hottest rung (I-12)

A dose is stored as **one** `Classified` — `(immunizations, "dose", <dose id>)` —
whose payload is the mapping of the fields the operator gave (`subject`,
`vaccine`, `dose_date`, and any of `provider`, `lot_number`, `source`, `notes`)
and whose rung is the `compose()` of those fields' declared rungs. `vaccine` is
`L4`, so a dose is always `L4`: on an ambient list it shows only its derived form
(*"An immunization dose is on file"* — never the vaccine, never the date beside
the subject) and it renders in full only in the detail pane, where opening it is
the purpose declaration. That is the same crossing the school form already
relies on — `export_history` takes exactly these records.

`next_due` is stored **separately**, as the `L2` date it is declared to be —
`(immunizations, "next_due", <dose id>)` — so the Today line can read it on a
list surface, parse it with the engine's one strict parser, and count it,
without the dose it belongs to ever being served below its rung.

## The key carries the subject id and nothing else (H-1)

A dose id is `<subject id>-<NN>`, minted by counting that subject's doses —
`subj-01-01`, `subj-01-02` — so *finding a subject's doses is a key-prefix
scan*, reaching no payload (the chokepoint holds package-wide here), and a log
line about a dose carries an opaque reference and no fragment of a name.

## Refusals happen before anything is written

An unknown subject, an empty vaccine, or a dose date the engine will not read
(BUG-1: never guessed) raise before `put`. Dates go through `parse_deadline`
and are stored in their ISO form.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from homestead.keep.dates import parse_deadline
from homestead.keep.logs import Event, VisibleLog
from homestead.keep.record import Sidecar
from homestead.keep.rungs import Classified, Disposition, Rung, Surface, compose, serve

from homestead_health import due
from homestead_health._egress import validate_subject
from homestead_health.packs.immunizations import FIELDS, MATTER
from homestead_health.roster import Roster

__all__ = ["DoseRef", "DERIVED", "DOSE_ITEM", "NEXT_DUE_ITEM", "add_dose", "doses_of",
           "next_due_of", "dose_ref", "list_row", "next_due_text", "today_line"]

DOSE_ITEM = "dose"
NEXT_DUE_ITEM = "next_due"

#: The one sentence an ambient surface may show for a dose. A count, a date or a
#: vaccine name in this string would put L4/L2 content on an L3 surface beside
#: the subject's id; there is deliberately nothing to fill in.
DERIVED = "An immunization dose is on file"

#: The optional fields a dose may carry beyond subject, vaccine and dose date.
_OPTIONAL = ("provider", "lot_number", "source", "notes")

#: A dose id is a roster id (`subj-NN`, the roster's own minted shape) and a
#: two-digit-or-more counter. Anchored on both halves so `subj-03` alone, or a
#: vaccine name, is never read as a dose.
_DOSE_ID = re.compile(r"^(?P<subject>subj-\d+)-(?P<n>\d{2,})$")


@dataclass(frozen=True)
class DoseRef:
    """An opaque handle to one dose: its id and the subject it belongs to — both
    references (I-15), never a name and never a vaccine."""

    id: str
    subject: str

    def __str__(self) -> str:
        return self.id


def dose_ref(dose_id: str) -> DoseRef:
    """The `DoseRef` for a dose id, or `ValueError` if it is not one."""
    m = _DOSE_ID.match(dose_id or "")
    if not m:
        raise ValueError(f"{dose_id!r} is not a dose id (subject-NN)")
    return DoseRef(id=dose_id, subject=m.group("subject"))


def _clean(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _subject_id(roster: Roster, subject: object) -> str:
    sid = validate_subject(subject)
    if sid not in roster:
        raise ValueError(
            f"{sid!r} is not on the roster — enrol the household member first "
            "(`homestead-health roster add <name> [--minor]`)"
        )
    return sid


def _next_number(store: Sidecar, sid: str) -> int:
    highest = 0
    prefix = f"{sid}-"
    for (_, item_type, item_id), _record in store.records(MATTER):
        if item_type != DOSE_ITEM or not item_id.startswith(prefix):
            continue
        m = _DOSE_ID.match(item_id)
        if m and m.group("subject") == sid:
            highest = max(highest, int(m.group("n")))
    return highest + 1


def add_dose(
    store: Sidecar,
    roster: Roster,
    *,
    subject: object,
    vaccine: str,
    dose_date: str,
    next_due: str | None = None,
    provider: str | None = None,
    lot_number: str | None = None,
    source: str | None = None,
    notes: str | None = None,
    log: VisibleLog | None = None,
) -> DoseRef:
    """Record one dose for an enrolled subject. Returns its reference.

    Refuses — before writing — a subject not on the roster, an empty vaccine,
    and a dose or next-due date the engine cannot read. Writes the composed
    dose (L4) and, if given, the next-due date (L2), then one `VisibleLog`
    line carrying the dose id alone.

    **Every refusal a caller must handle, by type** — the list is here because a
    surface that catches three of the four turns the fourth into a traceback,
    which is what both surfaces did before the W0 audit:

    * `ExportRefused` (a `PermissionError`, from `_egress.validate_subject`) —
      the subject is not one clean reference segment. This is the *likely*
      operator mistake: typing the person's name where the id goes.
    * `ValueError` — the subject is not on the roster, or the vaccine is empty.
    * `UnparseableDate` (a `ValueError`) — a date the engine will not guess at.
    * `FileExistsError` — the id this call minted was taken between the count
      and the write, by a second process adding a dose for the same subject.
      The store refuses to clobber (I-9) and **nothing is written**; the id is
      not reused, because the next call recounts. Retrying is the whole fix.
    """
    sid = _subject_id(roster, subject)
    vaccine_name = _clean(vaccine)
    if vaccine_name is None:
        raise ValueError("a dose names its vaccine")
    date_iso = parse_deadline(dose_date).iso
    next_iso = parse_deadline(next_due).iso if _clean(next_due) else None

    payload: dict[str, str] = {"subject": sid, "vaccine": vaccine_name, "dose_date": date_iso}
    for name, value in (("provider", provider), ("lot_number", lot_number),
                        ("source", source), ("notes", notes)):
        cleaned = _clean(value)
        if cleaned is not None:
            payload[name] = cleaned

    rung = compose(*(FIELDS[name] for name in payload))
    record = Classified(rung, payload, derived=DERIVED)

    dose_id = f"{sid}-{_next_number(store, sid):02d}"
    # No overwrite: a racing second writer is refused by the store (I-9), and
    # the id it lost is not reused because the next call recounts.
    store.put(MATTER, DOSE_ITEM, dose_id, record)
    if next_iso is not None:
        store.put(MATTER, NEXT_DUE_ITEM, dose_id, Classified(FIELDS["next_due"], next_iso))

    visible = log if log is not None else VisibleLog()
    # RECORD_SYNCED is the closest closed-enum act the pinned engine has for "a
    # record was stored" — it has no RECORD_ADDED, and the enum is closed, so
    # there is nothing truer to say here yet. Plan bite **H2-cap** raises the
    # engine floor to the release that adds `Event.RECORD_ADDED` and switches
    # this one line to it; the roster (`roster.add`) carries the same debt.
    visible.record(Event.RECORD_SYNCED, ref=(dose_id,))
    return DoseRef(id=dose_id, subject=sid)


def _of(store: Sidecar, subject: object, item_type: str) -> list[tuple[DoseRef, Classified]]:
    sid = validate_subject(subject)
    prefix = f"{sid}-"
    out: list[tuple[DoseRef, Classified]] = []
    for (_, kind, item_id), record in store.records(MATTER):
        if kind != item_type or not item_id.startswith(prefix):
            continue
        m = _DOSE_ID.match(item_id)
        if m and m.group("subject") == sid:
            out.append((DoseRef(id=item_id, subject=sid), record))
    out.sort(key=lambda pair: pair[0].id)
    return out


def doses_of(store: Sidecar, subject: object) -> list[tuple[DoseRef, Classified]]:
    """A subject's dose records, by id, as the `Classified`s to serve or export.
    Found by key prefix — no payload is read — so an unenrolled or unknown
    subject simply has none."""
    return _of(store, subject, DOSE_ITEM)


def next_due_of(store: Sidecar, subject: object) -> list[tuple[DoseRef, Classified]]:
    """A subject's next-due records (L2 dates), keyed by the dose they follow."""
    return _of(store, subject, NEXT_DUE_ITEM)


def list_row(record: Classified) -> tuple[Rung, str] | None:
    """What an ambient list row may carry for one dose — or `None`, drawn as nothing.

    Both surfaces (the CLI's `dose list` and the browser's `/api/doses`) go
    through here, so the rule cannot hold in one and not the other — the
    `_egress` lesson: do not keep two validators for the same rule.

    The rule is that **a list row carries the derived sentence, never the
    record**. A dose composes to `L4` (the vaccine), so the gate derives here
    by construction and `Served.value` already *is* `DERIVED`. The `RENDER`
    branch is refused anyway rather than printed: a dose that renders on a list
    surface is a record whose stored rung did not survive as `L4` — a
    hand-edit, a restore of a half-written tree, a future writer that skipped
    `add_dose` — and printing `Served.value` there would put the vaccine, the
    dose date and the operator's notes on an ambient row beside the subject id,
    which is exactly what the pack's `dose_date` declaration promises cannot
    happen ("the declaration is per-field, the protection is per-record").
    Failing closed to the one sentence costs nothing: the detail pane is one
    click away and is where a dose is meant to be read.

    `DENY` (an `L5`, or a rung that did not read at all) is `None` — dropped
    with no count left behind, the way `serve_all` drops a denial.
    """
    served = serve(record, Surface.S1_LIST)
    if served.disposition is Disposition.DENY:
        return None
    return served.rung, DERIVED


def next_due_text(record: Classified) -> str | None:
    """The next-due date an ambient row may carry, or `None`.

    `next_due` is declared `L2` — a date naming nobody by itself — and `L2`
    renders on a list surface, so the served value *is* the stored ISO date.
    Anything else (a rung that did not survive as `L2`, so the gate derives or
    denies) is not a date and is not put where a date goes.
    """
    served = serve(record, Surface.S1_LIST)
    if served.disposition is not Disposition.RENDER:
        return None
    return str(served.value)


def today_line(store: Sidecar, roster: Roster, *, today: object) -> str | None:
    """The Today line over the whole household, or `None` (drawn as nothing).

    Reads every subject's next-due dates on the list surface — `L2` renders
    there, so the served value *is* the stored date — counts the ones falling in
    `today`'s calendar month, and hands the count to `due.today_line`, which
    applies the engine's k ≥ 2 check over the roster before a digit is rendered.
    A date that will not parse counts as nothing rather than as a guess (I-8).
    """
    deadlines = []
    for ref in roster.subjects():
        for _dose, record in next_due_of(store, ref):
            text = next_due_text(record)
            if text is None:
                continue
            try:
                deadlines.append(parse_deadline(text))
            except ValueError:
                continue
    count = due.due_this_month(deadlines, today=today)
    return due.today_line(roster.subjects(), due=count)
