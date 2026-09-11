"""ledger_seam.py -- the ONLY place this module reaches into an `IntegrityLog`'s
own reader rather than the file it keeps.

**The finding (H6-sealed-reader, E6 audit).** `living.py` used to read
`IntegrityLog.path` with a bare per-line `json.loads`, filtering on
`entry.get("kind")`. Once a log has been through `homestead integrity seal`,
every line from the sealed boundary on is `{"sealed": 1, "nonce": ..., "ct":
...}` -- a dict with no `kind` field -- so that reader silently found zero
matches and answered "this value was never replaced" instead of refusing.

~~**Why this reaches a private method.** 0.11.0's `IntegrityLog` exposes no
public door onto its own plaintext entries (`export.ledger()` returns the log
object itself, still a raw `.path`; `verify()` answers a bool, not entries).
The one reader that already does this right is `IntegrityLog._entries()` --
underscore-private by the engine's F-6 naming guard, and named in its own
docstring as "the one door for a log's content": it skips the keyed/sealed
boundary rows, decrypts a sealed line when it can, and raises
`IntegritySealError`/`IntegrityKeyError` by name when it cannot --
`homestead.keep.sync._already_delivered` is the engine's own in-package
caller of it. This module is not in that package, so this file is the one
deliberate exception: every other file in `homestead_health` reads ledger
content through `_ledger_entries()` below, never `._entries` directly and
never a raw `json.loads` over a `.jsonl` log path
(`tests/test_ledger_seam.py` scans for both, each proven against a plant).~~

**H7-floor-0.12: the engine named this publicly (E7-public-log-reader).**
0.12.0's `IntegrityLog.read_entries(*, decrypt=True)` is the public door the
paragraph above went looking for -- `_entries()` is now only a deprecated
alias for it (removed in 0.13.0, per `homestead`'s own
`docs/DECISION-integrity-key-management.md` §9), and this seam calls
`read_entries()` directly. This file is now the one-line pass-through its
docstring always promised: `_ledger_entries()` below does nothing this
module could not have asked the engine to do itself, in its own name.

**Every way this read can fail has a name here.** `read_entries` may still be
renamed or dropped by a future engine inside the `<1.0` cap; a log may be
half-written by a crash, hand-edited to garbage, unreadable, or *shorter
than the anchor says it should be* (`IntegrityIncompleteError` -- a
truncated or deleted log with a surviving anchor); a sealed line may fail to
authenticate (`SealTamperError`). None of those mean "never replaced," and
none should reach a caller as a bare `AttributeError`, `JSONDecodeError` or
`OSError` either. The engine's own named refusals (`IntegritySealError`,
`IntegrityKeyError`) pass through unchanged; everything else becomes
`LedgerUnreadable` (I-11). `living.LivingLane.replacements()` turns all of
these into `LivingLaneRefused`.
"""
from __future__ import annotations

import json
from typing import Any, Iterator

from homestead.keep.logs import (
    IntegrityIncompleteError,
    IntegrityKeyError,
    IntegrityLog,
    IntegritySealError,
)
from homestead.keep.sealed import SealTamperError

__all__ = ["_ledger_entries", "LedgerUnreadable"]


class LedgerUnreadable(Exception):
    """This ledger cannot be read, and the honest answer is not `[]`.

    Raised for the failures the engine has no named refusal of its own for:
    the `read_entries()` reader gone from an upgraded engine, a log shorter
    than its anchor says it should be (`IntegrityIncompleteError` -- a
    truncated or deleted log with a surviving anchor), a corrupt or
    truncated log line (`json.JSONDecodeError`), a sealed line that fails to
    authenticate (`SealTamperError`), or the file being unreadable (`OSError`).
    The original is kept as `__cause__`; `IntegritySealError` and
    `IntegrityKeyError` are *not* wrapped, because they already name what is
    missing and callers pin them.
    """


def _ledger_entries(log: IntegrityLog) -> Iterator[dict[str, Any]]:
    """Every entry `log` actually recorded, plaintext, oldest first.

    Boundary rows (`{"act": "keyed"}` / `{"act": "sealed"}`) are never
    yielded. A sealed line is decrypted when the log holds the key and the
    `sealed` extra is installed; when it cannot be, this raises
    `IntegritySealError` (or `IntegrityKeyError`, for a keyed segment read
    without the key) by name rather than silently skipping the line -- a
    caller asking "what did this get replaced with" must never be told
    "nothing" when the honest answer is "cannot tell without the key."

    Never yields a short answer: `IntegritySealError`/`IntegrityKeyError`
    propagate unchanged and every other failure -- a dropped `read_entries`,
    a log shorter than its anchor (`IntegrityIncompleteError`), a corrupt
    line, a sealed line that does not authenticate, an unreadable file --
    becomes `LedgerUnreadable`. A log that does not exist, or one that was
    never written to (no anchor), is not a failure: nothing yielded is the
    true answer "nothing was ever written."

    A surviving log whose *anchor* alone is gone still answers, and that is
    the engine's rule rather than a choice made here: the anchor is the only
    witness to a log's length, so with no anchor there is no claim to fall
    short of and `IntegrityLog._require_whole` returns quietly -- the same
    posture `verify()` takes for `anchor is None`. The asymmetry with the
    deleted-*log* case (which does refuse, by `IntegrityIncompleteError`) is
    deliberate; both are pinned in `tests/test_living_sealed.py`, and the
    operator's off-machine head (`LivingLane.verify(expected_head)`) is what
    closes the remaining gap.
    """
    reader = getattr(log, "read_entries", None)
    if not callable(reader):
        raise LedgerUnreadable(
            "the installed engine's IntegrityLog no longer exposes the "
            "read_entries() reader this seam reads through; homestead-health "
            "cannot read a ledger's content until this seam is pointed at "
            "whatever replaced it (see homestead_health/ledger_seam.py)"
        )
    try:
        yield from reader()
    except (IntegritySealError, IntegrityKeyError):
        raise
    except IntegrityIncompleteError as exc:
        raise LedgerUnreadable(
            f"this ledger is shorter than its anchor says it should be -- "
            f"truncated or deleted with the anchor surviving: {exc}"
        ) from exc
    except SealTamperError as exc:
        raise LedgerUnreadable(
            f"a line in this ledger failed to authenticate: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise LedgerUnreadable(
            f"this ledger has a line that is not readable JSON -- truncated "
            f"or hand-edited, not empty: {exc}"
        ) from exc
    except OSError as exc:
        raise LedgerUnreadable(
            f"this ledger could not be read from disk: {exc}"
        ) from exc
