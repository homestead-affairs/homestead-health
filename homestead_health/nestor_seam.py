"""nestor_seam.py -- the ONLY place this module touches Nestor.

Nestor is Apache-2.0 with ``dependencies = []``.  Nothing here obliges a
household to install a dependency tree.

**Nestor is an OPTIONAL EXTRA** (``pyproject.toml``'s ``entity`` extra),
never a required dependency.  Every function here degrades to *feature
absent* when Nestor is not installed -- nothing here raises on import,
nothing here crashes a surface.

===========================================================================
TAKEN FROM NESTOR   (pin: nestor-meaning >=0.11.0)
===========================================================================

  EntityResolver(store, domain=..., seal_threshold=...)   nestor.entity
      .resolve(surface) -> dict      read-only; fuzzy-match a surface form
                                     against sealed aliases
      .seal(surface, canonical, verifier=...)             human-initiated write
      .add_alias(surface, canonical, verifier=...)        human-initiated write

      Domains on this face:
        "provider"   healthcare providers (clinics, practitioners, pharmacies)
        "vaccine"    immunization entities (vaccine names, manufacturers, lots)

  DecisionMemory(store, domain=..., ...)                  nestor.decision
      Sealed decisions with graph edges -- treatment and care decisions that
      carry a verifier and a reason.

      Domains on this face:
        "care"       decisions about treatment, care plans, provider choices

  Storage                                                 nestor.storage
      A Protocol.  Nestor owns no persistence -- "a concrete implementation is
      *injected* by the host."  Both ``resolver_for()`` and ``decisions_for()``
      take the store as a parameter rather than constructing one; a conforming
      adapter is this module's own build item, not this seam's.

  set_ledger_path(path)                                   nestor.cascade
      REQUIRED.  See PRECONDITIONS.  ``bind()`` calls this -- it is the only
      function in this module that changes where Nestor's audit trail lives.

  ledger.verify(path, expected_head=...)                  nestor.ledger
      Verify the chain on read/boot.  A broken chain is a refusal upstream of
      this call -- ``verify_ledger()`` reports ``False`` for the caller to act
      on, the same convention ``homestead.keep.logs.IntegrityLog.verify()``
      uses.

===========================================================================
NOT TAKEN   (deliberate -- the omissions carry as much weight as the takings)
===========================================================================

  nestor.cascade translation pipeline   translate_text, translate_segment,
      graduate_segment.  Translation is not this module's domain.

  nestor.matcher / nestor.semantic_matcher   reached only through
      EntityResolver.  Never imported directly; that is how the surface widens.

  nestor.serve / nestor.ui / nestor.ui_page   an HTTP server.  ``ui.py``
      imports ``http.server`` and ``urllib.parse`` at module level, which would
      put a network import in the import-pure core and fail
      ``test_invariants_seat.py``'s network scan the moment the extra was
      installed and this seam imported it eagerly.  It is not imported here,
      anywhere, ever.

  nestor.reconcile / nestor.answer / nestor.curator / nestor.frank /
      nestor.glossary / nestor.langid / nestor.segment / nestor.calibrate /
      nestor.portable / nestor.keyring / nestor.signing / nestor.memory /
      nestor.embedding_store / nestor.sqlite_store / nestor.engine / nestor.cli
      Not our business.  Some are excellent.  Not ours.

  THE ``cloud`` EXTRA  (``anthropic``)  -- MUST NEVER BE INSTALLED ON THIS
      MODULE.  This module's premise is that nothing leaves the device.

  THE ``semantic`` EXTRA  (``fastembed``) -- license discrepancy unresolved.
      Unused.

===========================================================================
PRECONDITIONS   -- all three MUST hold before any Nestor call in this process
===========================================================================

1.  THE LEDGER IS PINNED INSIDE ``<household root>/keep/ledger.jsonl``.

    This is the one that is easy to miss and expensive to miss.  Nestor's
    hash-chained ledger is **not part of the Storage protocol** -- injecting
    the store does not cover it.  Unbound, it resolves independently:

        _LEDGER_OVERRIDE  ->  $NESTOR_LEDGER  ->  "data/ledger.jsonl"

    So a default install writes to ``data/ledger.jsonl`` relative to the
    working directory: outside the household root, outside anything this
    module's own rules reach.  ``bind()`` exists to close that window before
    any other Nestor call in this process -- see ``SeamNotBoundError``.

    The path is not invented here.  This seam calls **only**
    ``homestead.keep.paths`` for WHERE (I-19/I-20 -- paths.py is the one
    module permitted to resolve a home directory) and never Nestor's own
    household resolver, so there is one resolver on this side of the
    boundary, not two that could drift.

    ``EntityResolver.resolve()`` appends on EVERY call (``entity.py``):

        {"kind": "entity_resolve",
         "surface_sha": sha256(surface)[:16],
         "canonical":   <resolved value>,
         "sealed": ..., "confidence": ...}

    The input is hashed; the resolved value is not.  In a health context that
    is a line recording, in the clear, that some surface form resolves to a
    named provider or a vaccine product.  Local, but recorded -- and by default
    recorded somewhere this module's own rules do not reach, until ``bind()``
    has run.

    NOTE ON RUNG SENSITIVITY: provider resolution is L3 (names a business);
    vaccine equivalence is L4 (medical act).  The seam itself does not enforce
    rungs -- that is the pack's and the gate's job -- but a reader of this seam
    should know that entity resolution here touches health data.

2.  THE STORE IS PASSED EXPLICITLY, NEVER SET GLOBALLY.

    ``nestor.storage`` offers ``set_store()`` as a process-wide global.  This
    seam does not call it.  ``resolver_for()`` and ``decisions_for()`` require
    the caller's ``store`` explicitly, so two modules can never share a
    resolver's store by accident.

3.  NESTOR IS PINNED TO A TAG.

    ``nestor-meaning >=0.11.0,<1.0``, never a branch on anything that ships.
    Never vendored.  See ``pyproject.toml``'s ``entity`` extra.

===========================================================================
FOR AGENTS AND FUTURE READERS
===========================================================================

Nestor is a PINNED DEPENDENCY consumed only through this file.  Do not modify
it, do not propose changes to it, and do not move logic from this module into
it.  If Nestor needs a change, that is an issue on Nestor's own repo.

The subject of work here is *how this module uses Nestor*, never Nestor itself.

Covenant: this seam never seals anything on its own initiative.
``EntityResolver.seal`` / ``.add_alias`` are human-initiated writes upstream of
this module (a caller passes a ``verifier=``); nothing here calls them, and
nothing here manufactures a ``verifier``.  A machine proposes; only a named
human seals.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from homestead.keep import paths

__all__ = [
    "available",
    "bind",
    "resolver_for",
    "decisions_for",
    "verify_ledger",
    "SeamNotBoundError",
]

#: What to tell an operator who reaches a Nestor-backed feature without the extra.
NOT_INSTALLED = (
    "nestor-meaning is not installed -- entity resolution and care decisions "
    "are an optional extra: pip install 'homestead-health[entity]'"
)


def available() -> bool:
    """Whether the ``entity`` extra is importable.

    Checked by name, never by importing at module load (the seam stays a no-op
    without the extra). A caller that wants a Nestor feature asks this first and
    degrades to *feature absent* on ``False`` -- the roster, the dose records and
    the Today line never depended on Nestor and keep working without it.
    """
    import importlib.util

    return importlib.util.find_spec("nestor") is not None


class SeamNotBoundError(RuntimeError):
    """A Nestor call was attempted before ``bind()`` pinned the ledger.

    Raised rather than defaulted, because the default is the leak: an unbound
    ledger writes household entity resolutions to ``data/ledger.jsonl`` in the
    working directory, outside anything this module's own rules reach.  Fail
    closed.
    """


_bound: bool = False
_ledger_path: Optional[Path] = None


def bind(household_root: Path | None = None) -> Path | None:
    """Pin Nestor's ledger inside the household root.  Call once, before use.

    ``household_root`` defaults to ``homestead.keep.paths.home()`` -- the one
    resolver this module is permitted to call (I-19/I-20) -- and should only be
    passed explicitly by a test or an operator who deliberately moved the root.

    Sets Nestor's ledger location to ``<household_root>/keep/ledger.jsonl`` --
    computed here from this repo's own resolver and passed to
    ``nestor.cascade.set_ledger_path()`` as an explicit path, so it holds
    whatever Nestor's own household root happens to be (PRECONDITION 1).
    Idempotent: calling it again with the same root re-asserts the same path;
    calling it with a different root re-binds to the new one.  Returns the
    ledger path that is now pinned.

    Nestor is imported here, not at module load, so a checkout without the
    ``entity`` extra still imports this module cleanly. **Without the extra,
    ``bind()`` returns ``None`` and binds nothing** -- the seam degrades to
    feature-absent, as its contract promises.
    """
    global _bound, _ledger_path

    if not available():
        # Feature absent, not a crash: a household that never installed the
        # ``entity`` extra still enrols members and records doses. Nothing is
        # bound, so every Nestor-backed call still refuses with
        # ``SeamNotBoundError`` rather than reaching an unpinned ledger.
        _bound = False
        _ledger_path = None
        return None

    from nestor.cascade import set_ledger_path

    root = Path(household_root) if household_root is not None else paths.home()
    ledger = root / "keep" / "ledger.jsonl"
    set_ledger_path(ledger)
    _ledger_path = ledger
    _bound = True
    return ledger


def resolver_for(domain: str, store: Any) -> Any:
    """An ``EntityResolver`` over an explicitly-injected household store.

    ``domain`` separates disjoint entity graphs within one store --
    "provider", "vaccine" -- so a clinic's aliases and a vaccine product's
    equivalences never cross-talk.

    ``store`` is required and passed straight through to Nestor -- this seam
    never calls ``nestor.storage.set_store()`` and never falls back to a global
    (PRECONDITION 2).  Raises ``SeamNotBoundError`` if ``bind()`` has not run:
    constructing a resolver with an unpinned ledger is the leak this seam
    exists to prevent, so it is refused before Nestor is even imported.
    """
    if not _bound:
        raise SeamNotBoundError(
            "resolver_for() called before bind(). Call nestor_seam.bind() "
            "once at startup -- an EntityResolver built on an unpinned ledger "
            "would write household entity resolutions to data/ledger.jsonl "
            "in the working directory, outside anything this module's own "
            "rules reach."
        )

    from nestor.entity import EntityResolver

    return EntityResolver(store, domain=domain)


def decisions_for(domain: str, store: Any) -> Any:
    """A ``DecisionMemory`` over an explicitly-injected household store.

    ``domain`` separates disjoint decision graphs within one store --
    "care" for treatment decisions, provider choices, and care plans.

    ``store`` is required and passed straight through to Nestor -- this seam
    never calls ``nestor.storage.set_store()`` and never falls back to a global
    (PRECONDITION 2).  Raises ``SeamNotBoundError`` if ``bind()`` has not run:
    constructing a DecisionMemory with an unpinned ledger is the leak this seam
    exists to prevent, so it is refused before Nestor is even imported.
    """
    if not _bound:
        raise SeamNotBoundError(
            "decisions_for() called before bind(). Call nestor_seam.bind() "
            "once at startup -- a DecisionMemory built on an unpinned ledger "
            "would write household decisions to data/ledger.jsonl "
            "in the working directory, outside anything this module's own "
            "rules reach."
        )

    from nestor.decision import DecisionMemory

    return DecisionMemory(store, domain=domain)


def verify_ledger(expected_head: Optional[str] = None) -> bool:
    """Walk the hash chain and confirm every link.  Run on read/boot.

    Returns ``True`` for an intact chain (or no ledger yet -- Nestor's own
    ``verify()`` treats absence as trivially valid, matching
    ``homestead.keep.logs.IntegrityLog.verify()``'s convention) and ``False``
    for a broken one.  The bool return, not an exception, is deliberate and
    matches this repo's own ``IntegrityLog.verify()`` convention: a broken
    chain is a refusal for the *caller* to act on -- nothing in this module
    decides what "refusal" means for a given surface.

    Raises ``SeamNotBoundError`` if ``bind()`` has not run: there is no ledger
    path to verify until this seam has pinned one.
    """
    if not _bound:
        raise SeamNotBoundError(
            "verify_ledger() called before bind(). Call nestor_seam.bind() "
            "once at startup so there is a pinned ledger path to verify."
        )

    from nestor.ledger import verify

    ok, _detail = verify(str(_ledger_path), expected_head=expected_head)
    return ok
