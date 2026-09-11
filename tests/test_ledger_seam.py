"""H6-sealed-reader — health reaches an `IntegrityLog`'s content through one
seam, `ledger_seam._ledger_entries()`: never a bare `json.loads` over a
`.jsonl` path (the original bug's shape) and never a second caller of the
engine's private `._entries()`. Each guard is proven against a plant first —
a scan that has never fired has not been shown to check anything.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parent.parent / "homestead_health"


def _reads_a_jsonl_path_with_bare_json_loads(py_file: Path) -> bool:
    """True if `py_file` both names a `.jsonl` path (a string literal ending
    in `.jsonl`) and decodes JSON itself, anywhere in the file — the original
    bug's shape. A legitimate reader routes through `ledger_seam`, which
    decodes nothing of its own.

    **The honest claim** (a guard that overclaims is worse than none). The
    `.jsonl` half is a *literal-suffix* test: it catches the shipped bug's
    shape and the variants that still spell the name (`logs_dir() /
    "living.jsonl"`, `p.with_suffix(".jsonl")`, `Path("living.jsonl")`). The
    decode half catches `json.loads`/`json.load` and a bare `loads(`/`load(`
    from `from json import loads`. **The escape**, planted below as an
    expected miss rather than left as prose: a reader that never spells
    `.jsonl` because the path arrives as a parameter. Closing it needs value
    tracing, which an AST grep does not do — it is covered from the other
    side, by `test_only_the_seam_calls_the_engines_private_entries_reader`
    (the only in-package handle on a ledger file is `IntegrityLog`) and by
    `tests/test_living_sealed.py`'s behavioural refusals."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"))

    names_a_jsonl_path = any(
        isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and node.value.endswith(".jsonl")
        for node in ast.walk(tree)
    )
    if not names_a_jsonl_path:
        return False

    def _decodes_json(node: ast.AST) -> bool:
        if not isinstance(node, ast.Call):
            return False
        func = node.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr in ("loads", "load")
            and isinstance(func.value, ast.Name)
            and func.value.id == "json"
        ):
            return True
        # `from json import loads` — the same call, one import away.
        return isinstance(func, ast.Name) and func.id in ("loads", "load")

    return any(_decodes_json(node) for node in ast.walk(tree))


def _calls_entries_underscore(py_file: Path) -> set[str]:
    """`{py_file.name}` if it reaches the engine's private, package-internal
    `_entries` reader — spelled `<expr>._entries` (called or merely bound) or
    fetched by name through `getattr(<expr>, "_entries")`. Only
    `ledger_seam.py` may.

    Both spellings are checked because the attribute form is the one a person
    writes and the `getattr` form is the one they write *after* a guard tells
    them not to. A dynamically built name (`getattr(log, "_" + "entries")`)
    still escapes; that is the same literal-only limit the `.jsonl` guard
    states above, and it is not worth an interpreter to close."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "_entries":
            return {py_file.name}
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == "_entries"
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


@pytest.mark.parametrize(
    "name, source, caught",
    [
        ("with_suffix",
         "import json\ndef f(p):\n"
         "    return json.loads(p.with_suffix('.jsonl').read_text())\n", True),
        ("path_constructor",
         "import json\nfrom pathlib import Path\ndef f(h):\n"
         "    return json.loads((Path(h) / 'living.jsonl').read_text())\n", True),
        ("from_json_import_loads",
         "from json import loads\nfrom homestead.keep import paths\ndef f():\n"
         "    return loads((paths.logs_dir() / 'living.jsonl').read_text())\n", True),
        ("json_load_on_a_handle",
         "import json\nfrom homestead.keep import paths\ndef f():\n"
         "    with (paths.logs_dir() / 'living.jsonl').open() as fh:\n"
         "        return json.load(fh)\n", True),
        # The documented escape: the path is a parameter, so `.jsonl` is never
        # spelled and the literal-suffix half of the guard has nothing to see.
        ("path_never_spelled",
         "import json\ndef f(log):\n"
         "    return [json.loads(l) for l in log.path.read_text().splitlines()]\n", False),
    ],
)
def test_the_bare_json_loads_guard_catches_the_variants_and_misses_what_it_says(
    tmp_path, name, source, caught
):
    """A re-break would most likely be one of these shapes, so each is a
    plant — a guard shown only the exact original has not been shown to
    generalize. The last row is the escape the guard's docstring names,
    pinned as an expected *miss*: if a later edit closes it, this fails and
    the docstring gets corrected rather than quietly under-claiming."""
    planted = tmp_path / f"planted_{name}.py"
    planted.write_text(source, encoding="utf-8")
    assert _reads_a_jsonl_path_with_bare_json_loads(planted) is caught


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


@pytest.mark.parametrize(
    "name, source",
    [
        ("getattr_literal",
         "def f(log):\n    return list(getattr(log, '_entries')())\n"),
        ("bound_not_called",
         "def f(log):\n    reader = log._entries\n    return list(reader())\n"),
    ],
)
def test_the_private_entries_guard_fires_on_the_ways_around_it(tmp_path, name, source):
    """The two spellings someone reaches for once the plain call is guarded:
    `getattr` with a literal name, and binding the bound method before calling
    it. Both are the same reach and both must be caught, or the guard only
    teaches people how to phrase the violation."""
    planted = tmp_path / f"planted_{name}.py"
    planted.write_text(source, encoding="utf-8")
    assert _calls_entries_underscore(planted) == {planted.name}


def test_the_engine_still_has_the_private_reader_this_seam_reaches_for():
    """The contract this bite pins, in the only direction that can break
    without anyone here touching a line: `_entries` is underscore-private, so
    a future `homestead-affairs` inside the `<1.0` cap may rename or drop it.
    If that happens this must fail loudly here — at the seam, with the fix
    named — rather than at the first sealed household's audit.

    The refusal half of the same contract (a dropped `_entries()` refuses by
    name, never answers `[]`) is pinned in `tests/test_living_sealed.py`."""
    from homestead.keep.logs import IntegrityLog

    reader = getattr(IntegrityLog, "_entries", None)
    assert callable(reader), (
        "the installed homestead-affairs no longer exposes "
        "IntegrityLog._entries — homestead_health/ledger_seam.py is the one "
        "file to repoint at whatever replaced it"
    )
