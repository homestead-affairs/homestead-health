"""H6-sealed-reader / H7-floor-0.12 — health reaches an `IntegrityLog`'s
content through one seam, `ledger_seam._ledger_entries()`: never a bare
`json.loads` over a `.jsonl` path (the original bug's shape), never a caller
anywhere in the package of the now-deprecated `._entries()` alias, and never
a second caller of the public `.read_entries()` outside the seam. Each guard
is proven against a plant first — a scan that has never fired has not been
shown to check anything.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest

_PKG = Path(__file__).resolve().parent.parent / "homestead_health"
_PYPROJECT = _PKG.parent / "pyproject.toml"


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
    side, by `test_only_the_seam_calls_the_engines_public_read_entries_reader`
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


def _calls_named_reader(py_file: Path, attr: str) -> set[str]:
    """`{py_file.name}` if it reaches `<expr>.<attr>` (called or merely
    bound) or fetches it by name through `getattr(<expr>, "<attr>")`. Backs
    both `_calls_entries_underscore` (`attr="_entries"`, the engine's
    deprecated alias, E7) and `_calls_read_entries` (`attr="read_entries"`,
    its public replacement) below.

    Both spellings are checked because the attribute form is the one a
    person writes and the `getattr` form is the one they write *after* a
    guard tells them not to. A dynamically built name (`getattr(log, "_" +
    "entries")`) still escapes; that is the same literal-only limit the
    `.jsonl` guard states above, and it is not worth an interpreter to
    close."""
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == attr:
            return {py_file.name}
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "getattr"
            and len(node.args) >= 2
            and isinstance(node.args[1], ast.Constant)
            and node.args[1].value == attr
        ):
            return {py_file.name}
    return set()


def _calls_entries_underscore(py_file: Path) -> set[str]:
    """The engine's now-deprecated `_entries()` alias (E7). Nothing in this
    package may spell it: the seam moved to `read_entries()`, so
    `_entries()` -- on its way out in 0.13.0 -- has no in-package caller
    left at all, not even the one-time exception `ledger_seam.py` used to
    be."""
    return _calls_named_reader(py_file, "_entries")


def _calls_read_entries(py_file: Path) -> set[str]:
    """The engine's public `read_entries()` reader. Only `ledger_seam.py`
    may call it directly; every other file reads ledger content through
    `_ledger_entries()`, the one seam."""
    return _calls_named_reader(py_file, "read_entries")


def test_no_module_parses_a_jsonl_ledger_with_a_bare_json_loads():
    """The real tree: zero files name a `.jsonl` path and call `json.loads`
    themselves — `living.py` used to be exactly this file."""
    offenders = [
        p.relative_to(_PKG.parent).as_posix()
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


def test_nothing_spells_the_deprecated_entries_alias():
    """`_entries()` is a deprecated alias now (E7-public-log-reader, removed
    in 0.13.0), not a door `ledger_seam.py` gets a one-time exception to use
    either — the seam moved to `read_entries()`, so the real tree has zero
    callers of the old name anywhere in this package."""
    callers: dict[str, set[str]] = {}
    for p in _PKG.rglob("*.py"):
        hits = _calls_entries_underscore(p)
        if hits:
            callers[p.relative_to(_PKG.parent).as_posix()] = hits

    assert callers == {}, (
        f"a module spells the engine's deprecated ._entries() alias — call "
        f"read_entries() instead (via ledger_seam._ledger_entries()): {callers}"
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


def test_only_the_seam_calls_the_engines_public_read_entries_reader():
    """`ledger_seam.py`'s `getattr(log, "read_entries", None)` probe is the
    one call site; every other file reads content through
    `_ledger_entries()`, never the engine's reader directly."""
    callers: dict[str, set[str]] = {}
    for p in _PKG.rglob("*.py"):
        hits = _calls_read_entries(p)
        if hits:
            callers[p.relative_to(_PKG.parent).as_posix()] = hits

    assert set(callers) <= {"homestead_health/ledger_seam.py"}, (
        f"a module other than ledger_seam.py calls the engine's "
        f".read_entries() directly: {callers}"
    )


def test_the_read_entries_guard_fires_on_a_planted_violation(tmp_path):
    planted = tmp_path / "planted_direct_reader.py"
    planted.write_text(
        "def replacements(ledger, thing):\n"
        "    return [e for e in ledger.read_entries() if e.get('thing') == thing]\n",
        encoding="utf-8",
    )
    assert _calls_read_entries(planted) == {"planted_direct_reader.py"}


def test_the_engine_still_has_the_public_reader_this_seam_reaches_for():
    """The contract this bite pins, in the only direction that can break
    without anyone here touching a line: a future `homestead-affairs` inside
    the `<1.0` cap may still rename or drop `read_entries`. If that happens
    this must fail loudly here — at the seam, with the fix named — rather
    than at the first sealed household's audit.

    The refusal half of the same contract (a dropped `read_entries()`
    refuses by name, never answers `[]`) is pinned in
    `tests/test_living_sealed.py`."""
    from homestead.keep.logs import IntegrityLog

    reader = getattr(IntegrityLog, "read_entries", None)
    assert callable(reader), (
        "the installed homestead-affairs no longer exposes "
        "IntegrityLog.read_entries — homestead_health/ledger_seam.py is the "
        "one file to repoint at whatever replaced it"
    )


# ── the runtime half of the same guard: the deprecation filter (H7) ─────────

_PLANTED_CALLER = """\
\"\"\"A reintroduced call to the engine's deprecated `_entries()` alias, in a
module whose `__name__` starts with `homestead_health` — exactly what the AST
guard above forbids statically, planted here to see whether the *runtime*
guard catches it too.\"\"\"


def replacements(log):
    return list(log._entries())
"""

_PLANTED_TEST = """\
from homestead.keep import paths
from homestead.keep.logs import IntegrityLog
from homestead_health.planted_alias_caller import replacements


def test_the_plant_calls_the_deprecated_alias():
    log = IntegrityLog(
        paths.logs_dir() / "living.jsonl",
        anchor_path=paths.anchors_dir() / "living.head",
    )
    log.append({"kind": "living_replaced", "thing": "sleep"})
    assert replacements(log)
"""


def _run_planted_alias_call(tmp_path, *, config: Path) -> subprocess.CompletedProcess:
    """Run one pytest subprocess over a planted `homestead_health.*` module
    that calls `_entries()`, under `config`'s ini.

    The plant is a real package directory named `homestead_health` on a
    `PYTHONPATH` entry of its own, so the warning is filed against the module
    name `homestead_health.planted_alias_caller` — the thing the filter
    matches on — rather than against a top-level module that merely happens
    to start with those letters. It shadows the installed package for the
    length of this subprocess only; nothing in the plant imports the real
    one."""
    plant = tmp_path / "plant" / "homestead_health"
    plant.mkdir(parents=True)
    (plant / "__init__.py").write_text("", encoding="utf-8")
    (plant / "planted_alias_caller.py").write_text(_PLANTED_CALLER, encoding="utf-8")
    test_file = tmp_path / "test_planted_alias_call.py"
    test_file.write_text(_PLANTED_TEST, encoding="utf-8")

    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ)
    env["PYTHONPATH"] = str(tmp_path / "plant")
    env["HOMESTEAD_HOME"] = str(home)
    return subprocess.run(
        [
            sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
            "-c", str(config), "--rootdir", str(tmp_path), str(test_file),
        ],
        capture_output=True, text=True, cwd=str(tmp_path), env=env, timeout=300,
    )


def test_the_deprecated_alias_filter_fails_a_reintroduced_call(tmp_path):
    """`pyproject.toml`'s `filterwarnings` must actually turn a reintroduced
    `_entries()` call into a CI failure — the runtime half of
    `test_nothing_spells_the_deprecated_entries_alias`, which only reads
    source.

    This is not a detail of taste. `_entries()` warns with `stacklevel=2`,
    which files the `DeprecationWarning` against the *caller's* module, so a
    filter scoped to the engine's own `homestead.keep.logs` never matches a
    call made from here — the filter would have been decoration. The scopes
    added for it (`homestead_health`, and the message regex) are proven the
    only way a filter can be: by planting the violation and requiring the run
    to go red."""
    proc = _run_planted_alias_call(tmp_path, config=_PYPROJECT)

    assert proc.returncode != 0, (
        "the planted _entries() call passed under this repo's filterwarnings "
        f"— the filter does not cover it:\n{proc.stdout}\n{proc.stderr}"
    )
    assert "DeprecationWarning" in proc.stdout and "_entries" in proc.stdout, (
        f"the run failed, but not on the deprecation:\n{proc.stdout}\n{proc.stderr}"
    )


def test_the_same_plant_passes_without_the_filter(tmp_path):
    """The control that makes the test above mean something: under an ini
    with no `filterwarnings` at all, the identical plant *passes* with the
    deprecation as a mere warnings-summary line. So what fails it above is
    the configured filter, not the plant being broken in some other way —
    and this is precisely the state the repo was in before this bite widened
    the scope."""
    bare = tmp_path / "bare.ini"
    bare.write_text("[pytest]\n", encoding="utf-8")
    proc = _run_planted_alias_call(tmp_path, config=bare)

    assert proc.returncode == 0, f"{proc.stdout}\n{proc.stderr}"
    assert "DeprecationWarning" in proc.stdout, (
        "the plant did not even raise the deprecation — the engine's alias "
        f"may be gone:\n{proc.stdout}"
    )
