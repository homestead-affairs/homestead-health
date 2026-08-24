"""`homestead_health.nestor_seam` -- the one place this module touches Nestor.

Nestor is an OPTIONAL EXTRA (``pyproject.toml``'s ``[project.optional-
dependencies] entity``), pinned to ``nestor-meaning >=0.11.0,<1.0``, never a
required dependency.  Two properties carry that, each a test:

* **The seam is a no-op without the extra.**  Nothing in ``nestor_seam.py``
  imports ``nestor`` at module load -- an AST scan, the same trick the
  engine's ``test_invariants_nestor_seam.py`` uses -- so a checkout that never
  installs ``[entity]`` still imports this module and runs the rest of the
  suite.  Every test in this file that *does* exercise Nestor's own machinery
  skips (not fails) when ``nestor`` is not importable, so a cold checkout
  without the extra keeps ``pytest -q`` bare and green (I-28).

* **Nothing crosses before ``bind()``.**  ``resolver_for()``,
  ``decisions_for()``, and ``verify_ledger()`` all refuse --
  ``SeamNotBoundError`` -- before a ledger path is pinned, which is the leak
  PRECONDITION 1 in the module docstring names: an unbound Nestor ledger
  writes household entity resolutions to ``data/ledger.jsonl`` relative to
  the working directory, outside anything this module's own rules reach.  All
  refusal tests run unconditionally (they never reach an ``import nestor``),
  so they hold even on a checkout without the extra installed.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from homestead_health import nestor_seam
from homestead_health.nestor_seam import SeamNotBoundError

PKG = Path(__file__).resolve().parent.parent / "homestead_health"
SEAM = PKG / "nestor_seam.py"


class _FakeStore:
    """The minimum ``nestor.storage.Storage`` surface ``EntityResolver`` and
    ``DecisionMemory`` touch when there is nothing sealed yet:
    ``memory_init`` (constructor) and ``memory_candidates`` (an empty domain,
    reached by ``.resolve()``'s fallback to ``memory.lookup``).  Real
    persistence is this module's own build item -- this seam only requires
    that *a* conforming store be passed in (PRECONDITION 2: never a
    process-wide global)."""

    def __init__(self) -> None:
        self.memory_init_calls = 0

    def memory_init(self) -> None:
        self.memory_init_calls += 1

    def memory_candidates(self, source_lang: str, target_lang: str) -> list:
        return []


@pytest.fixture(autouse=True)
def _reset_seam_state():
    """``nestor_seam`` holds module-level ``_bound``/``_ledger_path``, so one
    test's ``bind()`` must not leak into the next.  Also resets Nestor's own
    process-wide ledger-verification cache when Nestor is installed, so a
    tampered-chain test in one case cannot be masked by another test's
    already-verified cache entry."""
    nestor_seam._bound = False
    nestor_seam._ledger_path = None
    try:
        import nestor.cascade as cascade
    except ImportError:
        cascade = None
    if cascade is not None:
        cascade._LEDGER_OVERRIDE = None
        cascade.reset_ledger_session()
    yield
    nestor_seam._bound = False
    nestor_seam._ledger_path = None
    if cascade is not None:
        cascade._LEDGER_OVERRIDE = None
        cascade.reset_ledger_session()


# -- the seam is a no-op without the extra ------------------------------------

def test_nestor_seam_imports_no_nestor_at_module_load():
    """``import homestead_health.nestor_seam`` must succeed on a checkout that
    never installed ``[entity]``.  ``bind``/``resolver_for``/``decisions_for``/
    ``verify_ledger`` each import ``nestor`` locally, inside the function --
    never at module scope."""
    tree = ast.parse(SEAM.read_text(encoding="utf-8"))
    top_level: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            top_level |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module.split(".")[0])
    assert "nestor" not in top_level, (
        "nestor_seam.py imports `nestor` at module load -- this makes the "
        "optional extra ambient: a checkout without [entity] would fail to "
        "import this module, and every other test in the suite with it."
    )


# -- nothing crosses before bind() -- unconditional, no nestor import reached -

def test_resolver_for_refuses_before_bind():
    with pytest.raises(SeamNotBoundError):
        nestor_seam.resolver_for("provider", _FakeStore())


def test_decisions_for_refuses_before_bind():
    with pytest.raises(SeamNotBoundError):
        nestor_seam.decisions_for("care", _FakeStore())


def test_verify_ledger_refuses_before_bind():
    with pytest.raises(SeamNotBoundError):
        nestor_seam.verify_ledger()


# -- bound behavior -- skips (not fails) without the `entity` extra -----------
#
# `importorskip` is called *inside* each test below, not at module scope.
# A module-level `importorskip` failing aborts collection of the *entire file*,
# taking the four unconditional tests above down with it -- exactly the
# "no nestor at load" and "refuses before bind" proofs that must hold on a
# checkout *without* the extra.


def test_bind_pins_the_ledger_under_household_root_keep(tmp_path):
    """The path contract: ``<household_root>/keep/ledger.jsonl``, computed from
    ``homestead.keep.paths``-shaped input -- never a literal, never Nestor's own
    household resolver (PRECONDITION 1: one resolver on this side)."""
    pytest.importorskip("nestor", reason="the `entity` extra is not installed")
    ledger = nestor_seam.bind(tmp_path)
    assert ledger == tmp_path / "keep" / "ledger.jsonl"

    from nestor.cascade import _ledger_path as resolved

    assert resolved() == ledger


def test_resolver_for_after_bind_returns_a_scoped_entity_resolver(tmp_path):
    pytest.importorskip("nestor", reason="the `entity` extra is not installed")
    nestor_seam.bind(tmp_path)
    store = _FakeStore()
    resolver = nestor_seam.resolver_for("provider", store)

    from nestor.entity import EntityResolver

    assert isinstance(resolver, EntityResolver)
    assert resolver.domain == "provider"
    assert resolver.store is store
    assert store.memory_init_calls == 1


def test_decisions_for_after_bind_returns_a_scoped_decision_memory(tmp_path):
    pytest.importorskip("nestor", reason="the `entity` extra is not installed")
    nestor_seam.bind(tmp_path)
    store = _FakeStore()
    dm = nestor_seam.decisions_for("care", store)

    from nestor.decision import DecisionMemory

    assert isinstance(dm, DecisionMemory)
    assert dm.domain == "care"
    assert dm.store is store


def test_verify_ledger_true_for_an_unwritten_chain(tmp_path):
    """No ledger yet is not a broken one -- matches
    ``homestead.keep.logs.IntegrityLog.verify()``'s convention for absence."""
    pytest.importorskip("nestor", reason="the `entity` extra is not installed")
    nestor_seam.bind(tmp_path)
    assert nestor_seam.verify_ledger() is True
