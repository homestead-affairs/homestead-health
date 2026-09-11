"""X7-drift-health — the meta-scan: every AST/grep-guard helper this suite
carries has been shown to catch something.

*A scan that has never fired has not been shown to check anything* is the
repo's own rule (README's engine-cap note and every `_offenders`/`_reaches`
helper here cites it). This file is that rule turned into a test that reads
the *other* test files: it finds every module-level helper in ``tests/`` that
looks like a violation-scanner — either its name says so
(``_record_synced_offenders``, ``_reads_a_jsonl_path_with_bare_json_loads``,
``_calls_entries_underscore``) or its body walks source with ``ast.parse``/
``ast.walk`` the way ``_payload_reaches``, ``_home_reaches`` and
``_smoke_modules`` do — and asserts that the *same file* also holds a test
proving the scan fires on a planted violation.

**The convention, read off the repo rather than invented.** Every existing
plant test either names it outright (`test_the_scan_catches_every_bypass_
spelling`, `test_the_bare_json_loads_guard_fires_on_a_planted_violation`,
`test_the_record_synced_scan_fires_on_a_plant`) or says "planted" in its
docstring while the *name* reads differently (`test_i19_regression_desktop_
leak`, `test_the_network_scan_sees_a_lazy_import`) — so the check below reads
name **and** docstring together, and looks for any of ``plant``, ``fires``,
``catches``. A check that only read test names would call two real, already-
verified guards (`_home_reaches`, `_all_imports`) unplanted and be wrong.

**Honest about what it cannot see**, the same way `_reads_a_jsonl_path_with_
bare_json_loads` says so of itself: a helper that reaches for `ast.parse`
through an alias (`from ast import parse as p`), or one named for what it
does rather than how (`_toplevel_imports`, used by the undeclared-import scan
with no plant of its own until this bite — see
`tests/test_invariants_seat.py::test_i27_scan_fires_on_a_planted_undeclared_
import`), is outside the literal-name-or-literal-call test below. Closing
those needs either more names or an interpreter; this scan is the AST-grep
half, not a promise it sees everything a scan could be shaped like.
"""
from __future__ import annotations

import ast
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent

#: Word-stems the repo's own scan helpers already use, split on "_" so
#: `_record_synced_offenders` (offenders is the *last* word) and
#: `_reads_a_jsonl_path_with_bare_json_loads` (reads is the *first*) both
#: match without over-firing on unrelated names.
_NAME_TOKENS = frozenset({"scan", "scans", "reads", "calls", "offenders", "uses"})

#: The convention this repo actually uses for "this scan was shown to fire on
#: a planted violation" — read off the real test names and docstrings above,
#: not guessed.
_PLANT_WORDS = ("plant", "fires", "catches")


def _calls_ast_parse_or_walk(node: ast.AST) -> bool:
    """True if `node`'s body anywhere calls `ast.parse(...)` or `ast.walk(...)`
    — the shape of a scan that reads source rather than trusting a caller's
    already-parsed tree."""
    for sub in ast.walk(node):
        if (
            isinstance(sub, ast.Call)
            and isinstance(sub.func, ast.Attribute)
            and isinstance(sub.func.value, ast.Name)
            and sub.func.value.id == "ast"
            and sub.func.attr in ("parse", "walk")
        ):
            return True
    return False


def _is_scan_helper(name: str, node: ast.FunctionDef) -> bool:
    """A private, module-level helper counts as a scan/guard if its name
    carries one of the repo's own tokens, or it starts with `_is_` (the third
    named pattern), or it walks source itself via `ast.parse`/`ast.walk`."""
    if not name.startswith("_") or name.startswith("__"):
        return False
    if name.startswith("_is_"):
        return True
    if _NAME_TOKENS & set(name.strip("_").split("_")):
        return True
    return _calls_ast_parse_or_walk(node)


def _scan_helpers(source: str) -> list[str]:
    """Every module-level scan-helper function name in one tests module."""
    tree = ast.parse(source)
    return sorted(
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and _is_scan_helper(node.name, node)
    )


def _has_plant_test(source: str) -> bool:
    """True if some `test_*` function in this module names the plant/fires/
    catches convention — in its own name, or (the `regression_desktop_leak`
    shape) in its docstring."""
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            haystack = f"{node.name} {ast.get_docstring(node) or ''}".lower()
            if any(word in haystack for word in _PLANT_WORDS):
                return True
    return False


def _offenders() -> list[str]:
    """Every tests/*.py file that defines a scan helper with no companion
    plant test in the same file."""
    offenders = []
    for path in sorted(TESTS_DIR.glob("test_*.py")):
        if path.name == "test_scans_fire.py":
            continue  # this file's own helpers are proven below, not here
        source = path.read_text(encoding="utf-8")
        helpers = _scan_helpers(source)
        if helpers and not _has_plant_test(source):
            offenders.append(f"{path.name}: {helpers}")
    return offenders


def test_every_scan_helper_has_a_planted_violation_test():
    """The house rule, run for real: no `tests/*.py` file may carry an
    AST/grep-guard helper that nothing in the same file has planted a
    violation against."""
    offenders = _offenders()
    assert not offenders, (
        "these test files define a scan helper (name matches "
        f"{sorted(_NAME_TOKENS)} or _is_, or it calls ast.parse/ast.walk) "
        "with no test in the same file naming plant/fires/catches in its "
        "name or docstring — a scan that has never fired has not been "
        f"shown to check anything: {offenders}"
    )


def test_the_meta_scan_fires_on_a_planted_unguarded_scan(tmp_path):
    """Itself planted. A fake tests module with a scan helper (walks
    `ast.parse`/`ast.walk`, named the way this repo names one) and no plant
    test anywhere in it must be named by the checks above — proven directly
    against the helper functions, the way `_offenders()` would see it if the
    file lived under `tests/`."""
    planted = tmp_path / "test_planted_unguarded_scan.py"
    planted.write_text(
        "import ast\n"
        "\n"
        "def _offenders_of_something(root):\n"
        "    tree = ast.parse(root.read_text())\n"
        "    return [n for n in ast.walk(tree)]\n"
        "\n"
        "def test_something_holds():\n"
        "    assert True\n",
        encoding="utf-8",
    )
    source = planted.read_text(encoding="utf-8")

    helpers = _scan_helpers(source)
    assert helpers == ["_offenders_of_something"], (
        "the plant's own scan helper must be detected by name and by its "
        f"ast.parse/ast.walk call; got {helpers}"
    )
    assert not _has_plant_test(source), (
        "the plant's only test must NOT read as a planted-violation test — "
        "otherwise this proves nothing about the real scan above"
    )


def test_the_plant_word_check_does_not_fire_on_a_real_guarded_file():
    """The other half of the same honesty: a file that *does* carry a plant
    test (this repo's own `tests/test_ledger_seam.py`) must not be reported,
    or the meta-scan would be crying wolf on the very files it exists to
    clear."""
    source = (TESTS_DIR / "test_ledger_seam.py").read_text(encoding="utf-8")
    assert _scan_helpers(source), "test_ledger_seam.py is expected to define scan helpers"
    assert _has_plant_test(source)
