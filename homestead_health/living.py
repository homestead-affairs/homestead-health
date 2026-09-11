"""The living lane — a memory that forgets on purpose (bite 7, H-8).

The records track holds things that must stand: a dose, a provider, what is due,
kept append-only so a record once written cannot be quietly changed (I-36). A
family's living concerns are the opposite object. A worry over a bodily change is
true now, something else next month, and *its whole point is that it leaves no
record to be held against the person it is about* — the safety turn, in the one
place it bites hardest: a parent (holder) and a child (subject) across a power gap.
A living entry that accreted into a pinned per-child history would be exactly the
weapon this lane refuses to build.

So the living lane **forgets on purpose, and proves it** (H-8). It is two pieces,
and only the first is new:

1. **A forgetting cell.** Overwrite-in-place, only-latest, keyed by the *thing*.
   `remember(thing, value)` replaces whatever the cell held; the prior plaintext is
   genuinely gone on the write, the inverse of the records store's never-overwrite
   rule (I-9). This is the one new primitive, and it is small. It is **not a `keep`
   record** — `keep`'s append-only spine (I-36) is untouched.

2. **The audit, reused from `keep` as it stands.** Each replacement appends one
   line to a `keep` `IntegrityLog` — `{"kind": "living_replaced", "thing": …,
   "prior_sha256": …}` — carrying the thing's ref and the **hash** of the value it
   replaced, never the value. A hash commits to the prior without keeping it
   readable, so the operator can prove *"this cell was replaced four times, in
   order, un-forged"* (walk the chain, `verify(expected_head=…)` against an
   off-machine head) while the four priors are unrecoverable. Auditable *that* it
   forgot, without recording *what*. `DECISION-living-lane-ledger.md` records why
   `IntegrityLog` suffices as-is (the Nestor read) and why the audit uses it alone
   rather than `keep`'s `VisibleLog` (whose closed `Event` enum has no
   living-replaced member, an engine change this app must not make).

## The thing is never the subject (H-8)

Even a content-free log leaks by *shape*: "subj-02's cell was replaced nine times"
is a signal about a person with zero content in it. So the cell is keyed by the
**thing** — a household concern (`sleep`, `growth`) — and the audit lines ref the
thing, never the subject. The same rule H-1 applies to record keys, now applied to
motion. A key shaped like a roster subject id (`subj-NN`) is refused outright, so a
subject cannot be smuggled in as a thing, and grepping the cell store and the ledger
for any subject id comes back empty.

## L5, and no egress at all

A living entry is `L5` — sealed, served on no surface — and this lane exposes **no
egress**, purposed or otherwise. There is no `serve`, no `export`, no `Classified`
here: the cell holds raw text that never crosses a boundary. Forgetting is the only
thing that leaves, and it leaves nothing behind.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from pathlib import Path

from homestead.keep import paths
from homestead.keep.logs import IntegrityKeyError, IntegrityLog, IntegritySealError

from homestead_health.ledger_seam import LedgerUnreadable, _ledger_entries

__all__ = ["LivingLane", "LIVING_KIND", "LivingLaneRefused"]

#: The `IntegrityLog` entry kind for a forgetting. Not one of `keep`'s closed
#: `Event` members (that enum is the `VisibleLog`'s, and shut); the `IntegrityLog`
#: takes an arbitrary dict, so the lane tags its own lines and reads them back by
#: this kind. See `DECISION-living-lane-ledger.md`.
LIVING_KIND = "living_replaced"

#: A roster subject id. A thing key that matches this is a subject wearing a
#: thing's clothes, and H-8 forbids it — the living lane holds the thing, never the
#: subject.
_SUBJECT_SHAPE = re.compile(r"^subj-\d+$")


def _living_dir() -> Path:
    # A tree of its own, under the household root — not the records store, not the
    # sidecar. `paths.home()` is the engine's one resolver (the only reach to a home
    # directory this module is allowed); the segment is the lane's own.
    return paths.home() / "living"


def _validate_thing(thing: object) -> str:
    """A thing key, validated as one clean segment that is not a subject.

    It becomes a filename, so it must be a single safe path segment — no separator,
    no `..`, no control/format/whitespace character (the egress guard's discipline,
    for the same reason: a key is a path). And it must not be a roster subject id:
    the living lane is keyed by the thing, never the subject (H-8), so a `subj-NN`
    here is refused rather than filed.
    """
    if not isinstance(thing, str) or not thing.strip():
        raise ValueError("a living entry names a thing (a non-empty string)")
    if _SUBJECT_SHAPE.match(thing):
        raise ValueError(
            f"{thing!r} is a subject id; the living lane is keyed by the thing, "
            "never the subject (H-8). Name the concern, not the person."
        )
    for ch in thing:
        if ch in "/\\" or ch == "\x00" or ch.isspace() or unicodedata.category(ch)[0] == "C":
            raise ValueError(
                f"thing {thing!r} carries a separator, control, or whitespace "
                "character — a thing key is one clean path segment"
            )
    if thing in (".", ".."):
        raise ValueError(f"thing {thing!r} is not a usable key")
    return thing


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LivingLaneRefused(Exception):
    """The audit could not be answered -- refused by name, never as `[]`.

    Raised by `replacements()` whenever the ledger cannot be read: a sealed
    segment without the key or the `sealed` extra, a keyed segment without
    the key, a corrupt or truncated line, a sealed line that fails to
    authenticate, or an engine that no longer exposes the reader the seam
    reads through. Wraps the engine's `IntegritySealError`/
    `IntegrityKeyError`, or the seam's `LedgerUnreadable`, as `__cause__`,
    message carried through unchanged
    (H6-sealed-reader: this used to answer `[]` here instead — I-11).

    **Not** raised for a ledger that has never been written: no file, or a
    file with no matching lines, is the true answer `[]`, and the difference
    between "nothing was ever forgotten" and "I cannot tell" is the whole
    point of this class existing.
    """


class LivingLane:
    """The household's living concerns — a cell per thing, forgetting on replace.

    Handed nothing, it keeps its cells under `paths.home()/living` and its audit in
    a `keep` `IntegrityLog` (`logs/living.jsonl`, anchor off-tree under
    `anchors/living.head`). A caller may inject a ledger for testing.
    """

    def __init__(self, ledger: IntegrityLog | None = None) -> None:
        self._ledger = ledger if ledger is not None else IntegrityLog(
            paths.logs_dir() / "living.jsonl",
            anchor_path=paths.anchors_dir() / "living.head",
        )

    # ── the forgetting cell ──────────────────────────────────────────────────

    def _cell(self, thing: str) -> Path:
        return _living_dir() / f"{thing}.txt"

    def remember(self, thing: str, value: str) -> None:
        """Set the living value for `thing`, forgetting whatever it held.

        If a prior exists, its hash is recorded to the ledger **before** the cell is
        overwritten — so the forgetting is provable, and a failed write never loses a
        prior the ledger already claimed was replaced. The overwrite is in place: the
        prior plaintext is gone, recoverable from nowhere, its hash the only trace.
        """
        thing = _validate_thing(thing)
        if not isinstance(value, str):
            raise TypeError(f"a living value is text, not {type(value).__name__}")

        cell = self._cell(thing)
        prior = cell.read_text(encoding="utf-8") if cell.exists() else None
        if prior is not None:
            # Record that we forgot it — the thing's ref and the prior's hash, never
            # its content and never a subject. This is the whole audit.
            self._ledger.append(
                {"kind": LIVING_KIND, "thing": thing, "prior_sha256": _sha256(prior)}
            )

        paths.ensure(cell.parent)
        cell.write_text(value, encoding="utf-8")   # overwrite-in-place — the prior is gone

    def recall(self, thing: str) -> str | None:
        """The current living value for `thing`, or `None` — only ever the latest.

        The cell holds one value; a superseded one is not here and not anywhere. This
        is the read side of forgetting: there is no history to ask for, by design."""
        thing = _validate_thing(thing)
        cell = self._cell(thing)
        return cell.read_text(encoding="utf-8") if cell.exists() else None

    def things(self) -> tuple[str, ...]:
        """The things currently held, by key — never a value, never a subject."""
        base = _living_dir()
        if not base.is_dir():
            return ()
        return tuple(sorted(p.stem for p in base.glob("*.txt")))

    # ── the audit (read back from the ledger, content-free) ──────────────────

    def replacements(self, thing: str) -> list[dict]:
        """The `living_replaced` ledger lines for `thing`, oldest first.

        The operator-visible motion: how many times, in what order, with the hash of
        each forgotten value — and no value, no subject.

        Read through `ledger_seam._ledger_entries()` — the engine's own reader —
        never a bare `json.loads` over `self._ledger.path` (H6-sealed-reader): once
        `homestead integrity seal` has run, a sealed line is `{"sealed": 1, ...}`,
        which a bare `json.loads` reads as a dict with no `kind` field and silently
        drops, so the sealed case used to answer `[]` — "never replaced" — when the
        honest answer is "cannot tell without the key." The seam decrypts what it
        can and raises by name the moment it cannot; wrapped here as
        `LivingLaneRefused` so this refuses rather than answering empty (I-11).

        The same refusal covers every other way the read can fail — a corrupt
        or truncated line, a sealed line that does not authenticate, an
        engine that dropped the reader (`ledger_seam.LedgerUnreadable`) — so
        a caller has exactly one exception to catch and never a bare
        `JSONDecodeError` or `AttributeError` out of a stdlib frame. A ledger
        that was never written still answers `[]`: absent is not corrupt.
        """
        thing = _validate_thing(thing)
        try:
            entries = list(_ledger_entries(self._ledger))
        except (IntegritySealError, IntegrityKeyError, LedgerUnreadable) as exc:
            raise LivingLaneRefused(str(exc)) from exc
        return [
            entry for entry in entries
            if entry.get("kind") == LIVING_KIND and entry.get("thing") == thing
        ]

    def verify(self, expected_head: str | None = None) -> bool:
        """The forgetting is un-forged. Walks the chain; `expected_head` (a head the
        operator recorded off the machine) closes the last-line gap."""
        return self._ledger.verify(expected_head)

    def head(self) -> str:
        """The ledger tip — the value to record off the machine so `verify` means
        something later."""
        return self._ledger.head()
