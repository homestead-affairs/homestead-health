"""X7-drift-health — grep guards for the sentences the drift sweep found
stale and rewrote, so a reintroduction (a copy-paste from an old commit, a
docstring reverted by hand) fails here by name rather than misleading the
next reader.

**Two fixed, not a general staleness detector.** The sweep read every claim
in README.md, the module docstrings and docs/ against the code as it stands
today (2026-09-11) and found most of them still true — the engine-cap
reversal note, the `RECORD_ADDED`-not-`RECORD_SYNCED` prose, the living-log
"reads through the engine's reader" sentence, and the `_entries()` seam
commentary are all correct as written; H2-cap and H6-sealed-reader already
did that work. Two sentences had drifted past what the code now does, and
those two are what this file guards — one per the house rule that a scan
without a planted-violation test has not been shown to check anything.

1. **README.md's pinned test count.** "Suite: 128 passed / 0 xfailed" was
   true once; four optional-extra legs and two bites later the number moved
   and the sentence did not. Replaced with a description that does not name
   a count that goes stale on the next added test.
2. **`homestead_health/packs/immunizations.py`'s advisory-matcher note.** It
   said no immunizations detail pane existed to host `keep.advise` — true
   when bite 3 shipped, false since the records-entry bite added one
   (`server.py`'s `_get_dose`, `cli.py`'s `dose show`, both `S1_DETAIL`). The
   real debt (nothing calls `advise()` from that pane yet) is unchanged and
   still named; only the false "no surface" justification is corrected.
"""
from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
PKG = APP / "homestead_health"
README = APP / "README.md"
IMMUNIZATIONS = APP / "homestead_health" / "packs" / "immunizations.py"

#: Package-scaffolding files: no capability of their own, so the module-status
#: table (below) does not name them and does not need to.
_STATUS_TABLE_EXCLUSIONS = ("__init__.py", "__main__.py")

#: The exact sentences that were true once and are not now. Kept as the
#: literal strings that were actually in the files (not a paraphrase), so the
#: guard fires on a byte-for-byte reintroduction and nothing weaker.
STALE_TEST_COUNT = "128 passed / 0 xfailed"
STALE_NO_DETAIL_PANE = (
    "there is no\nimmunizations detail pane to host it, matching the engine's "
    "own wiring order."
)


def _contains(path: Path, needle: str) -> bool:
    return needle in path.read_text(encoding="utf-8")


def test_readme_does_not_reassert_the_stale_test_count():
    """A literal test count in prose is a number nothing derives — the exact
    failure mode `pyproject.toml`'s own version-pin comment names for a
    different number. It went stale once already; it must not come back."""
    assert not _contains(README, STALE_TEST_COUNT), (
        f"README.md must not re-assert the stale {STALE_TEST_COUNT!r} test "
        "count — describe the suite qualitatively (as the sentence that "
        "replaced it does), not with a literal that the next added test "
        "makes false again."
    )


def test_the_test_count_guard_fires_on_a_planted_regression(tmp_path):
    """The stale sentence, written back into a copy of the real file — the
    guard above must catch it."""
    planted = tmp_path / "README.md"
    planted.write_text(
        README.read_text(encoding="utf-8")
        + f"\n\nSuite: **{STALE_TEST_COUNT}**.\n",
        encoding="utf-8",
    )
    assert _contains(planted, STALE_TEST_COUNT), "the plant did not apply"


def test_immunizations_pack_does_not_reassert_the_missing_detail_pane():
    """The records-entry bite gave dose records a detail pane; the pack's own
    docstring said none existed. Fixed once; must not regress to the old
    justification even if the `advise()` wiring debt it describes is still
    open (it is — see the docstring's current wording)."""
    assert not _contains(IMMUNIZATIONS, STALE_NO_DETAIL_PANE), (
        "homestead_health/packs/immunizations.py must not re-assert that no "
        "detail pane exists to host the advisory matcher — one does "
        f"(server.py's _get_dose, cli.py's dose show): {STALE_NO_DETAIL_PANE!r}"
    )


def test_the_detail_pane_guard_fires_on_a_planted_regression(tmp_path):
    """The stale sentence, written into a copy of the real module — the guard
    above must catch it."""
    planted = tmp_path / "immunizations.py"
    planted.write_text(
        IMMUNIZATIONS.read_text(encoding="utf-8")
        + "\n\n_PLANTED_REGRESSION = '''"
        + STALE_NO_DETAIL_PANE
        + "'''\n",
        encoding="utf-8",
    )
    assert _contains(planted, STALE_NO_DETAIL_PANE), "the plant did not apply"


# ── README's "## Module status" table names every module or excludes it ──────


def _module_status_section(readme_text: str) -> str:
    match = re.search(r"^## Module status\n(.*?)(?=^## |\Z)", readme_text,
                       re.MULTILINE | re.DOTALL)
    assert match, "README.md has no '## Module status' section"
    return match.group(1)


def _package_basenames() -> list[str]:
    """Every `.py` file's bare name under `homestead_health/` — basenames
    only, never a path, so this holds the same on Windows and POSIX."""
    return sorted(p.name for p in PKG.rglob("*.py") if "__pycache__" not in p.parts)


def _modules_missing_from_status_table(readme_text: str) -> list[str]:
    section = _module_status_section(readme_text)
    return [
        name for name in _package_basenames()
        if name not in _STATUS_TABLE_EXCLUSIONS and name not in section
    ]


def test_every_module_is_named_in_the_status_table_or_excluded():
    """Every shipped module is either a row's evidence or a named exclusion —
    never simply forgotten. A module added without either fails here, named."""
    missing = _modules_missing_from_status_table(README.read_text(encoding="utf-8"))
    assert not missing, (
        "these homestead_health/*.py modules are named in neither README.md's "
        f"'## Module status' table nor _STATUS_TABLE_EXCLUSIONS: {missing} — "
        "give each a row, or add it to the exclusion tuple with a reason."
    )


def test_the_status_table_guard_fires_on_a_planted_omission():
    """A module the table forgets, planted by blanking every mention of one
    real, non-excluded module's name inside the table section only — the
    guard must name exactly that module."""
    readme_text = README.read_text(encoding="utf-8")
    section = _module_status_section(readme_text)
    assert "roster.py" in section, "the plant assumes roster.py is currently listed"
    gutted = readme_text.replace(section, section.replace("roster.py", "ROSTER_REMOVED"))
    missing = _modules_missing_from_status_table(gutted)
    assert missing == ["roster.py"], f"the guard must name exactly roster.py; got {missing}"
