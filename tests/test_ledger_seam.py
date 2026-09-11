"""H6-sealed-reader — health reaches an `IntegrityLog`'s content through one
seam, `ledger_seam._ledger_entries()`: never a bare `json.loads` over a
`.jsonl` path (the original bug's shape) and never a second caller of the
engine's private `._entries()`. Each guard is proven against a plant first —
a scan that has never fired has not been shown to check anything.
"""
from __future__ import annotations

import ast
from pathlib import Path

_PKG = Path(__file__).resolve().parent.parent / "homestead_health"


def _reads_a_jsonl_path_with_bare_json_loads(py_file: Path) -> bool:
    """True if `py_file` both names a `.jsonl` path (a string literal ending
    in `.jsonl`) and calls `json.loads` directly, anywhere in the file — the
    original bug's shape. A legitimate reader routes through `ledger_seam`,
    which never calls `json.loads` itself."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"))

    names_a_jsonl_path = any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.endswith(".jsonl")
        for node in ast.walk(tree)
    )
    if not names_a_jsonl_path:
        return False

    return any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "loads"
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "json"
        for node in ast.walk(tree)
    )


def _calls_entries_underscore(py_file: Path) -> set[str]:
    """`{py_file.name}` if it spells out `<expr>._entries(` anywhere — the
    engine's private, package-internal reader. Only `ledger_seam.py` may."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_entries"
        ):
            return {py_file.name}
    return set()


def test_no_module_parses_a_jsonl_ledger_with_a_bare_json_loads():
    """The real tree: zero files name a `.jsonl` path and call `json.loads`
    themselves — `living.py` used to be exactly this file."""
    offenders = [
        str(p.relative_to(_PKG.parent))
        for p in _PKG.rglob("*.py")
        if _reads_a_jsonl_path_with_bare_json_loads(p)
    ]
    assert offenders == [], (
        f"reads a .jsonl ledger with a bare json.loads instead of the engine's "
        f"reader (route through ledger_seam._ledger_entries instead): {offenders}"
    )


def test_the_bare_json_loads_guard_fires_on_a_planted_violation(tmp_path):
    planted = tmp_path / "planted_raw_reader.py"
    planted.write_text(
        "import json\n"
        "from homestead.keep import paths\n"
        "\n"
        "def replacements(thing):\n"
        "    path = paths.logs_dir() / 'living.jsonl'\n"
        "    out = []\n"
        "    for raw in path.read_text(encoding='utf-8').splitlines():\n"
        "        entry = json.loads(raw)\n"
        "        if entry.get('thing') == thing:\n"
        "            out.append(entry)\n"
        "    return out\n",
        encoding="utf-8",
    )
    assert _reads_a_jsonl_path_with_bare_json_loads(planted) is True, (
        "the guard did not fire on a planted copy of the original bug"
    )


def test_only_the_seam_calls_the_engines_private_entries_reader():
    """`._entries()` is underscore-private by the engine's own F-6 naming
    guard — a one-time, documented exception `ledger_seam.py` contains, not
    a door every file in this package gets to use on its own."""
    callers: dict[str, set[str]] = {}
    for p in _PKG.rglob("*.py"):
        hits = _calls_entries_underscore(p)
        if hits:
            callers[str(p.relative_to(_PKG.parent))] = hits

    assert set(callers) <= {"homestead_health/ledger_seam.py"}, (
        f"a module other than ledger_seam.py calls the engine's private "
        f"._entries() directly: {callers}"
    )


def test_the_private_entries_guard_fires_on_a_planted_violation(tmp_path):
    planted = tmp_path / "planted_private_reader.py"
    planted.write_text(
        "def replacements(ledger, thing):\n"
        "    return [e for e in ledger._entries() if e.get('thing') == thing]\n",
        encoding="utf-8",
    )
    assert _calls_entries_underscore(planted) == {"planted_private_reader.py"}
