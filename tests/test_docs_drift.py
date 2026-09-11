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

#: The *shape* of the stale sentence, not just the one number it happened to
#: carry. An exact-string guard is only as good as the literal it was written
#: against: it would have cleared a README that said "131 passed / 0 xfailed"
#: — a fresh pin of exactly the thing that went stale. `docs/promotion/
#: README.md` still carries the 128 as part of a dated promotion snapshot and
#: is deliberately not scanned: that file records what was true on a day, and
#: rewriting a dated record is a different wrong.
_PINNED_COUNT_RE = re.compile(r"\b\d+\s+(?:passed|failed|xfailed|skipped)\b")


def _pinned_test_counts(text: str) -> list[str]:
    """Every "N passed"-shaped literal in a piece of prose."""
    return _PINNED_COUNT_RE.findall(text)
STALE_NO_DETAIL_PANE = (
    "there is no\nimmunizations detail pane to host it, matching the engine's "
    "own wiring order."
)


def _contains(path: Path, needle: str) -> bool:
    return needle in path.read_text(encoding="utf-8")


def test_readme_does_not_pin_a_test_count():
    """A literal test count in prose is a number nothing derives — the exact
    failure mode `pyproject.toml`'s own version-pin comment names for a
    different number. It went stale once already; it must not come back, in
    that spelling or in a freshly-counted one."""
    pinned = _pinned_test_counts(README.read_text(encoding="utf-8"))
    assert not pinned, (
        f"README.md pins a suite count ({pinned}) — describe the suite "
        "qualitatively (as the sentence that replaced the stale "
        f"{STALE_TEST_COUNT!r} does), not with a literal that the next added "
        "test makes false again."
    )


def test_the_test_count_guard_fires_on_the_old_number_and_on_a_fresh_one(tmp_path):
    """The stale sentence written back into a copy of the real file, and — the
    half an exact-string guard would have missed — the same sentence with
    today's number in it. Both are the drift; only the shape catches both."""
    for pin in (STALE_TEST_COUNT, "304 passed / 0 xfailed"):
        planted = tmp_path / "README.md"
        planted.write_text(
            README.read_text(encoding="utf-8") + f"\n\nSuite: **{pin}**.\n",
            encoding="utf-8",
        )
        caught = _pinned_test_counts(planted.read_text(encoding="utf-8"))
        assert caught, f"the guard must catch a pinned {pin!r}"

    # And it does not fire on the sentence that replaced it, or the README
    # could never say anything about its own suite again.
    assert not _pinned_test_counts(
        "Suite: green on `pytest -q`, on every leg the optional `entity` "
        "extra and the engine's `sealed` extra cross."
    )


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


# ── "fifteen modules", in a sixteen-module package ──────────────────────────
#
# The W0 audit's narration — "a smoke test that imports four of fifteen
# modules does not make it" — was written when the package had fifteen
# modules. H6-sealed-reader added `ledger_seam.py` and neither sentence moved.
# `docs/audits/*.md` keeps its "fifteen": an audit is a dated record of what
# was found on a day, and editing one is not drift-fixing. These two are live
# code — the comment a reader hits while editing `--smoke`, and the docstring
# of the test that guards it — so they say what is true now, and this guard
# holds them to the file list rather than to a number someone retyped.

MAIN = PKG / "__main__.py"
SMOKE_TEST = Path(__file__).resolve().parent / "test_invariants_smoke.py"

#: Files that are scaffolding rather than modules — the same two names
#: `tests/test_invariants_smoke.py::_package_modules` excludes, for the same
#: reason (an `__init__` comes in with anything beneath it; `__main__` is the
#: file doing the importing).
_NOT_A_MODULE = ("__init__.py", "__main__.py")

_NUMBER_WORDS = (
    "zero one two three four five six seven eight nine ten eleven twelve "
    "thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty "
    "twenty-one twenty-two twenty-three twenty-four twenty-five twenty-six "
    "twenty-seven twenty-eight twenty-nine thirty"
).split()

_SPELLED_MODULE_COUNT_RE = re.compile(
    r"\b(" + "|".join(_NUMBER_WORDS) + r")\s+modules\b"
)


def _module_count() -> int:
    """How many modules the package actually ships."""
    return len([n for n in _package_basenames() if n not in _NOT_A_MODULE])


def _wrong_module_counts(text: str, actual: int) -> list[str]:
    """Every spelled-out "<N> modules" in this text that is not `actual`."""
    correct = _NUMBER_WORDS[actual] if actual < len(_NUMBER_WORDS) else None
    return [word for word in _SPELLED_MODULE_COUNT_RE.findall(text) if word != correct]


def test_no_live_file_names_a_module_count_the_package_does_not_have():
    """`homestead_health/__main__.py` and `tests/test_invariants_smoke.py` are
    read by whoever next edits the `--smoke` branch. A count in either that
    disagrees with the file list is the same drift as the README's pinned
    suite total, one file over."""
    actual = _module_count()
    wrong = {
        path.name: _wrong_module_counts(path.read_text(encoding="utf-8"), actual)
        for path in (MAIN, SMOKE_TEST)
    }
    wrong = {name: words for name, words in wrong.items() if words}
    assert not wrong, (
        f"the package ships {actual} modules ({_NUMBER_WORDS[actual]}), and "
        f"these files say otherwise: {wrong} — say the live number, or say "
        "none at all. Dated audit records under docs/audits/ are exempt by "
        "design and are not read here."
    )


def test_the_module_count_guard_fires_on_a_planted_stale_count(tmp_path):
    """The pre-H6 sentence, written back into a copy of the real file — the
    guard must name the word that went stale, and must not fire on the
    derived `{len(imported)} modules` the same file prints at run time."""
    actual = _module_count()
    planted = tmp_path / "__main__.py"
    planted.write_text(
        MAIN.read_text(encoding="utf-8").replace(
            f"four of {_NUMBER_WORDS[actual]} modules", "four of fifteen modules"
        ),
        encoding="utf-8",
    )
    caught = _wrong_module_counts(planted.read_text(encoding="utf-8"), actual)
    assert caught == ["fifteen"], f"the guard must name the stale word; got {caught}"
    assert not _wrong_module_counts('print(f"ok ({len(imported)} modules)")', actual), (
        "a count the code computes is not a count anyone can get wrong"
    )


# ── the status table's "Since" column names releases that happened ──────────

CHANGELOG = APP / "CHANGELOG.md"

_RELEASED_RE = re.compile(r"^## \[(\d+\.\d+\.\d+)\]", re.MULTILINE)
_VERSION_RE = re.compile(r"\d+\.\d+\.\d+")


def _released_versions() -> set[str]:
    """Every version `CHANGELOG.md` records as released."""
    return set(_RELEASED_RE.findall(CHANGELOG.read_text(encoding="utf-8")))


def _unreleased_since_versions(readme_text: str) -> list[str]:
    """Every version named in the status table that was never released.

    Catches an invented or mistyped number, not a merely *wrong* one: the
    entity seam's row said 0.1.0 when `nestor_seam.py` landed after v0.1.0
    was cut, and 0.1.0 is a real release, so only reading `git log` finds
    that. The README says where the column's numbers come from for exactly
    that reason; this guard is the cheap half.
    """
    section = _module_status_section(readme_text)
    released = _released_versions()
    return sorted(
        {v for v in _VERSION_RE.findall(section) if v not in released}
    )


def test_every_since_version_is_a_release_that_happened():
    """A "Since" that names a version this repo never cut is a claim with
    nothing behind it."""
    unreleased = _unreleased_since_versions(README.read_text(encoding="utf-8"))
    assert not unreleased, (
        "README.md's '## Module status' table names these versions, and "
        f"CHANGELOG.md records no such release: {unreleased}"
    )


def test_the_since_version_guard_fires_on_a_planted_phantom_release():
    """A version nobody ever cut, planted in the table — the guard must name
    it, and must still clear the real ones beside it."""
    readme_text = README.read_text(encoding="utf-8")
    section = _module_status_section(readme_text)
    assert "| `roster.py` | 0.1.0 |" in section, "the plant assumes the roster row's shape"
    planted = readme_text.replace(
        "| `roster.py` | 0.1.0 |", "| `roster.py` | 9.9.9 |", 1
    )
    assert _unreleased_since_versions(planted) == ["9.9.9"], (
        "the guard must name exactly the phantom release; got "
        f"{_unreleased_since_versions(planted)}"
    )
