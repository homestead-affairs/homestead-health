"""ledger_seam.py -- the ONLY place this module reaches into an `IntegrityLog`'s
own reader rather than the file it keeps.

**The finding (H6-sealed-reader, E6 audit).** `living.py` used to read
`IntegrityLog.path` with a bare per-line `json.loads`, filtering on
`entry.get("kind")`. Once a log has been through `homestead integrity seal`,
every line from the sealed boundary on is `{"sealed": 1, "nonce": ..., "ct":
...}` -- a dict with no `kind` field -- so that reader silently found zero
matches and answered "this value was never replaced" instead of refusing.

**Why this reaches a private method.** 0.11.0's `IntegrityLog` exposes no
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
(`tests/test_ledger_seam.py` scans for both, each proven against a plant).

**When the engine names this publicly, this file is the only edit** --
`_ledger_entries()` becomes a one-line pass-through to it.
"""
from __future__ import annotations

from typing import Any, Iterator

from homestead.keep.logs import IntegrityLog

__all__ = ["_ledger_entries"]


def _ledger_entries(log: IntegrityLog) -> Iterator[dict[str, Any]]:
    """Every entry `log` actually recorded, plaintext, oldest first.

    Boundary rows (`{"act": "keyed"}` / `{"act": "sealed"}`) are never
    yielded. A sealed line is decrypted when the log holds the key and the
    `sealed` extra is installed; when it cannot be, this raises
    `IntegritySealError` (or `IntegrityKeyError`, for a keyed segment read
    without the key) by name rather than silently skipping the line -- a
    caller asking "what did this get replaced with" must never be told
    "nothing" when the honest answer is "cannot tell without the key."
    """
    yield from log._entries()
