"""Bite 1 — the seat, held to its *done when*.

`homestead/docs/PLAN-homestead-health.md` § bite 1: cold checkout installs and
the suite is green; grepping the package for network imports, `expanduser`,
and a second path resolver all come back empty (I-19/I-20/I-26/I-27/I-28).
These are the engine's own scans (`tests/test_invariants_shape.py`,
`tests/test_invariants_paths.py`) aimed at this package — the same checks
because they are the same claims, one module over.
"""
from __future__ import annotations

import ast
import importlib.metadata as md
import importlib.util
import re
import subprocess
import sys
from pathlib import Path

# `packaging` is pytest's own hard dependency, so it is present wherever this
# suite runs; it is not an ambient import the package may make (the I-27 scan
# below walks `homestead_health/`, not the tests).
from packaging.specifiers import SpecifierSet
from packaging.version import Version

APP = Path(__file__).resolve().parent.parent
PKG = APP / "homestead_health"

NET = {"socket", "ssl", "urllib", "http", "requests", "httpx",
       "aiohttp", "websockets", "urllib3", "socketserver", "ftplib",
       "telnetlib", "smtplib", "xmlrpc"}


# Modules that are *intentionally* network-facing (the localhost web UI).
# They use http.server / urllib.parse by design — the invariant guards
# data-handling code from dialing out, not the server boundary itself.
BOUNDARY = {"server.py"}


def _modules() -> list[Path]:
    return sorted(
        p for p in PKG.rglob("*.py")
        if "__pycache__" not in p.parts and p.name not in BOUNDARY
    )


def _toplevel_imports(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def _all_imports(tree: ast.Module) -> set[str]:
    """Every imported top-level name, **anywhere in the tree** — including a lazy
    import nested inside a function body.

    The H-5 audit found `_toplevel_imports` (which walks `tree.body` only) blind to
    `def f(): import socket` — a deferred dial that never shows at module scope. The
    network scan below uses this full walk instead, so 'nothing dials' means nothing,
    not nothing at the top level. (The declared-dependency scan keeps
    `_toplevel_imports`: a lazy third-party import is a different, lesser sin, and
    the network rule is the one that must be total.)"""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


# ── the pin ─────────────────────────────────────────────────────────────────────


def _dependency_block(pyproject_text: str) -> str:
    """The body of `dependencies = [...]` in a `pyproject.toml`'s text."""
    block = re.search(
        r"^dependencies\s*=\s*\[(.*?)\]", pyproject_text, re.MULTILINE | re.DOTALL
    )
    assert block, "pyproject.toml must declare its dependencies"
    return block.group(1)


def _declared_engine_spec(pyproject_text: str | None = None) -> str:
    """The version specifier `pyproject.toml` declares for the engine, e.g.
    `">=0.3.0,<1.0"` — read from the file, never from the installed metadata,
    because the whole point is to compare the two.

    Takes the file's text optionally so the plant below can hand it a pin it
    wrote itself: X7-drift-health found this parser was the one scan in this
    file no planted-violation test ever ran.
    """
    if pyproject_text is None:
        pyproject_text = (APP / "pyproject.toml").read_text(encoding="utf-8")
    pin = re.search(r'"homestead-affairs([^"]*)"', _dependency_block(pyproject_text))
    assert pin, "the engine pin is the one declared dependency, and it is missing"
    return pin.group(1)


def _pin_defects(spec: str) -> list[str]:
    """What is missing from an engine pin — the check
    `test_the_pin_has_a_floor_and_a_cap` makes, as something a plant can run
    over a pin that is not this repo's."""
    defects = []
    if ">=" not in spec:
        defects.append("floor")
    if "<" not in spec:
        defects.append("cap")
    return defects


def test_the_engine_pin_is_true():
    """I-27, all three parts: the declared engine is the installed engine.

    `import homestead.keep` succeeding proves an engine is present;
    resolving the *distribution* proves it is the declared one
    (`homestead-affairs`), not a same-named package that happens to be
    importable — the import name and the distribution name differ by design,
    and only the metadata ties them together.

    The third part is new with bite H2-cap, which raised the floor to `0.3.0`
    for a symbol this seat now spends (`Event.RECORD_ADDED`): the installed
    *version* must satisfy the declared range. Without this the pin was a
    sentence in a file — reverting the line to the old `>=0.1.0,<0.3` against
    an installed 0.3.0 left every check in this file green, which is the seat
    claiming a pin it is not holding. A deliberate out-of-range install (an
    engine checkout put in with `--no-deps` to try unreleased work) is
    supposed to fail here; that is the state being reported, not a bug.
    """
    import homestead.keep  # noqa: F401

    version = md.version("homestead-affairs")
    assert version, "the engine distribution is not installed; the pin is not true"

    spec = _declared_engine_spec()
    assert SpecifierSet(spec).contains(Version(version), prereleases=True), (
        f"the installed engine is {version}, which does not satisfy the declared "
        f"pin {spec!r} — either the pin moved without a reinstall, or an engine "
        "outside the declared range was installed by hand"
    )


def test_the_pin_has_a_floor_and_a_cap():
    """The engine decides what renders, so the dependency line carries both a
    floor — the release whose symbols this seat spends, `Event.RECORD_ADDED`
    (tests/test_invariants_release.py) — and a cap.

    ~~and refuses the next minor unseen~~: the `<0.3` cap that clause described
    was reversed on 2026-09-11 (bite **H2-cap**) in favour of `<1.0`, and this
    docstring is the seat's copy of that reversal. What replaces the tight cap
    is not faith. The engine's release-please config sets
    `bump-minor-pre-major: false`, so `1.0.0` *is* its first compatibility
    break and `<1.0` is the cap that means something; and CI installs the
    newest engine the range allows on every PR (`pip install -e .`, no lock
    file) and runs this suite against it, so a minor that changed what renders
    arrives as a red check here rather than unseen on an operator's machine.

    What this test checks is unchanged: a pin with no floor or no cap is the
    failure, whatever the numbers are. `test_the_engine_pin_is_true` is what
    holds the numbers to the engine actually installed.
    """
    spec = _declared_engine_spec()
    assert not _pin_defects(spec), (
        f"the pin needs a floor and a cap — the engine is pre-1.0 (got {spec!r}, "
        f"missing {_pin_defects(spec)})"
    )


def test_the_pin_parser_and_the_floor_cap_guard_fire_on_a_planted_pyproject(tmp_path):
    """X7-drift-health: planted. `_declared_engine_spec` had no test that ever
    handed it anything but this repo's own passing `pyproject.toml`, so a
    parser that silently returned the wrong slice — or a floor/cap check that
    accepted a bare `==` pin — would have stayed green forever.

    Three pins written by hand: a capless one, a floorless one, and one whose
    engine entry sits beside another dependency, so the parser is shown to
    pick the engine's specifier and not the neighbour's.
    """
    capless = tmp_path / "capless.toml"
    capless.write_text('dependencies = ["homestead-affairs>=0.11.0"]\n', encoding="utf-8")
    assert _declared_engine_spec(capless.read_text(encoding="utf-8")) == ">=0.11.0"
    assert _pin_defects(">=0.11.0") == ["cap"]

    floorless = tmp_path / "floorless.toml"
    floorless.write_text('dependencies = ["homestead-affairs<1.0"]\n', encoding="utf-8")
    assert _declared_engine_spec(floorless.read_text(encoding="utf-8")) == "<1.0"
    assert _pin_defects("<1.0") == ["floor"]

    neighbour = tmp_path / "neighbour.toml"
    neighbour.write_text(
        'dependencies = [\n'
        '    "holidays>=0.50,<1.0",\n'
        '    "homestead-affairs>=0.11.0,<1.0",\n'
        ']\n',
        encoding="utf-8",
    )
    assert _declared_engine_spec(neighbour.read_text(encoding="utf-8")) == ">=0.11.0,<1.0"
    assert _pin_defects(">=0.11.0,<1.0") == []


def test_the_seat_imports_clean():
    """Importing the package from a fresh interpreter works and pulls no
    network module into the process — I-26 measured on the live import, not
    just the source scan below."""
    probe = (
        "import sys; import homestead_health; "
        f"bad = sorted(set(sys.modules) & {NET!r}); "
        "print('NET:' + ','.join(bad))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=APP, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "NET:\n" in result.stdout or result.stdout.strip() == "NET:", (
        f"importing the seat pulled network modules: {result.stdout}"
    )


# ── the scans (the *done when* greps, as tests) ──────────────────────────────


def test_i30_i26_nothing_imports_the_network():
    """No network module anywhere in the package — at module scope or lazily inside
    a function body. A full-tree walk, after the H-5 audit showed a top-level-only
    scan misses a deferred `import socket`."""
    offenders = {}
    for mod in _modules():
        hits = NET & _all_imports(ast.parse(mod.read_text(encoding="utf-8")))
        if hits:
            offenders[mod.relative_to(APP).as_posix()] = sorted(hits)
    assert not offenders, (
        f"nothing in this module dials — H-5's fetch half and I-26. Found: {offenders}"
    )


def test_the_network_scan_sees_a_lazy_import(tmp_path):
    """The scan itself, held honest. A network import hidden inside a function body
    must be caught — the exact bypass the H-5 audit planted, which the old
    top-level-only walk sailed past."""
    probe = tmp_path / "lazy.py"
    probe.write_text("def dial():\n    import socket\n    return socket\n")
    tree = ast.parse(probe.read_text())
    assert NET & _all_imports(tree), "a lazy `import socket` must be caught"
    assert not (NET & _toplevel_imports(tree)), "and it is invisible to the top-level walk"


#: `bind` itself is not banned, for the engine's stated tkinter reason; these
#: names have no GUI meaning.
LISTENS = {"listen", "serve_forever", "create_server", "ThreadingHTTPServer"}


def _listen_calls(tree: ast.AST) -> list[tuple[int, str]]:
    """Every call in this tree that opens an ear, however spelled."""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            f = node.func
            name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
            if name in LISTENS:
                hits.append((node.lineno, name))
    return hits


def test_i30_nothing_listens():
    """No bind/listen/serve call, however spelled (I-30)."""
    offenders = []
    for mod in _modules():
        for lineno, name in _listen_calls(ast.parse(mod.read_text(encoding="utf-8"))):
            offenders.append(f"{mod.relative_to(APP).as_posix()}:{lineno} {name}")
    assert not offenders, f"nothing may listen. Found: {offenders}"


def test_the_listen_scan_fires_on_every_spelling(tmp_path):
    """X7-drift-health: planted. This scan had never fired — `server.py` is
    exempt as the one boundary, so no module in the package has ever tripped
    it, and a scan that only ever returns nothing is indistinguishable from a
    scan that cannot return anything. All four spellings, including the bare
    class name a name-scan on attributes alone would miss."""
    probe = tmp_path / "ears.py"
    probe.write_text(
        "def a(s): return s.listen(5)\n"
        "def b(s): return s.serve_forever()\n"
        "def c(loop): return loop.create_server(None)\n"
        "def d(): return ThreadingHTTPServer(('', 0), None)\n",
        encoding="utf-8",
    )
    caught = {name for _, name in _listen_calls(ast.parse(probe.read_text(encoding="utf-8")))}
    assert caught == LISTENS, f"the scan missed a spelling; caught only {caught}"


# ── I-19 / I-20 · no second resolver, by any mechanism ───────────────────────
#
# **Rewritten after the bite-1 audit (2026-08-11), which earned its keep the
# way the Phase 0 audit did.** The first version of this scan banned three
# call *names* and advertised itself as “the engine's own scans … the same
# checks”. It was not: the engine's `tests/test_invariants_paths.py` was
# itself rewritten after the Phase 0 audit because a call-name scan let
# `Path(os.environ["HOME"]) / "Desktop" / "Nest"` — the Desktop leak, F-1,
# in idiomatic pathlib — pass the whole suite (`os.environ[...]` is a
# Subscript, not a call; `/ "Desktop"` contains no slash). The audit planted
# the engine's own regression payload here and this file stayed green while
# the engine's caught it twice. The copy below is the engine's mechanism
# scan ported whole — home-reaching calls *and* environment subscripts *and*
# user-directory literals in path context — with the engine's regression
# test kept, so the next weakened copy is caught by its own suite.

HOME_CALLS = {"expanduser", "expandvars", "getenv"}
HOME_ENV_KEYS = {"HOME", "USERPROFILE", "HOMEPATH", "HOMEDRIVE"}
BANNED_SEGMENTS = {"desktop", "documents", "downloads", "users", "home", "~"}


def _dotted(node: ast.AST) -> str:
    """`Path.home` from a `Path.home()` call; `paths.home` from `paths.home()`."""
    if isinstance(node, ast.Attribute):
        return f"{_dotted(node.value)}.{node.attr}".lstrip(".")
    if isinstance(node, ast.Name):
        return node.id
    return ""


def _docstring_ids(tree: ast.AST) -> set[int]:
    """Docstrings are excluded from the literal scan — the engine's lesson: a
    scanner that fires on its own documentation gets switched off."""
    ids: set[int] = set()
    holders = (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
    for node in ast.walk(tree):
        if isinstance(node, holders) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                ids.add(id(first.value))
    return ids


def _home_reaches(tree: ast.AST) -> list[tuple[int, str]]:
    """Every construct in this tree that reaches a home directory."""
    hits: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        # Path.home(), os.path.expanduser(...), os.getenv("HOME"),
        # os.path.expandvars("$HOME"), and any aliased binding of them.
        # `paths.home` is exempt: that is the engine's resolver, which is the
        # one legitimate way for this module to hold a root at all.
        if isinstance(node, ast.Call):
            dotted = _dotted(node.func)
            leaf = dotted.rsplit(".", 1)[-1]
            if leaf == "home" and dotted != "paths.home":
                hits.append((node.lineno, dotted or "home"))
            elif leaf in HOME_CALLS:
                hits.append((node.lineno, dotted or leaf))
        # os.environ["HOME"] / environ.get("HOME") — a Subscript, not a call,
        # which is exactly how the Desktop leak walked through a name scan.
        elif isinstance(node, ast.Subscript):
            if "environ" in _dotted(node.value):
                key = getattr(node.slice, "value", None)
                if isinstance(key, str) and key.upper() in HOME_ENV_KEYS:
                    hits.append((node.lineno, f"environ[{key!r}]"))
    return hits


def _path_context_strings(tree: ast.AST) -> list[tuple[int, str]]:
    """String literals used to *build a path* — an operand of `/`, an argument
    to `Path(...)`, or any string carrying a separator. The engine's scoping,
    for the engine's reason: broad enough to catch `/ "Desktop"`, narrow
    enough not to fire on a symbol named "home" in `__all__`."""
    out: list[tuple[int, str]] = []
    skip = _docstring_ids(tree)

    def note(node):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in skip:
            out.append((node.lineno, node.value))

    for node in ast.walk(tree):
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
            note(node.left)
            note(node.right)
        elif isinstance(node, ast.Call) and _dotted(node.func).rsplit(".", 1)[-1] == "Path":
            for arg in node.args:
                note(arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in skip:
            if "/" in node.value or "\\" in node.value:
                out.append((node.lineno, node.value))
    return out


def test_i19_i20_nothing_here_reaches_home():
    """No module in this package may reach a home directory, by any means.

    Stricter than the engine's version of the same scan on purpose: the
    engine exempts its own resolver file, and this package has no resolver
    file to exempt — the resolver is the engine's (`homestead.keep.paths`),
    one dependency over.
    """
    offenders = []
    for mod in _modules():
        for lineno, how in _home_reaches(ast.parse(mod.read_text(encoding="utf-8"))):
            offenders.append(f"{mod.relative_to(APP).as_posix()}:{lineno} {how}")
    assert not offenders, (
        "only the engine's resolver (homestead.keep.paths) may reach a home "
        f"directory. Found: {offenders}"
    )
    # And the one resolver exists to be used: the claim is "use the engine's",
    # which is only honest while the engine has one.
    assert importlib.util.find_spec("homestead.keep.paths") is not None


def _expanduser_calls(tree: ast.AST) -> list[int]:
    """Every `expanduser(...)` call in this tree, in any spelling or position."""
    return [
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and _dotted(node.func).rsplit(".", 1)[-1] == "expanduser"
    ]


def test_i20_the_invisible_spelling_is_banned_everywhere():
    """`expanduser` is invisible to the store's vault-leak linter, so it is
    banned in every spelling and every position — the engine's rule, verbatim."""
    offenders = []
    for mod in _modules():
        for lineno in _expanduser_calls(ast.parse(mod.read_text(encoding="utf-8"))):
            offenders.append(f"{mod.relative_to(APP).as_posix()}:{lineno}")
    assert not offenders, f"expanduser() is invisible to the linter. Found: {offenders}"


def test_the_expanduser_scan_fires_on_every_spelling(tmp_path):
    """X7-drift-health: planted. Another scan with nothing in the package to
    catch, so it had never once returned a hit. Three spellings — the
    `os.path` one, a `Path` method, and a bare name bound by
    `from os.path import expanduser` — because the rule is "every spelling and
    every position" and only a plant can say whether it is."""
    probe = tmp_path / "reaches.py"
    probe.write_text(
        "import os.path\n"
        "from os.path import expanduser\n"
        "from pathlib import Path\n"
        "def a(): return os.path.expanduser('~')\n"
        "def b(): return Path('~').expanduser()\n"
        "def c(): return expanduser('~')\n",
        encoding="utf-8",
    )
    assert len(_expanduser_calls(ast.parse(probe.read_text(encoding="utf-8")))) == 3


def test_i19_no_user_directory_literals():
    """Segment-wise and in path context — `/ "Desktop" / "Nest"` contains no
    slash and a substring scan never sees it."""
    offenders = []
    for mod in _modules():
        for lineno, value in _path_context_strings(ast.parse(mod.read_text(encoding="utf-8"))):
            segments = {s.strip().lower() for s in value.replace("\\", "/").split("/")}
            hit = segments & BANNED_SEGMENTS
            if hit:
                offenders.append(
                    f"{mod.relative_to(APP).as_posix()}:{lineno} {value!r} ({sorted(hit)})"
                )
    assert not offenders, f"user-directory literals are forbidden. Found: {offenders}"


def test_i19_regression_desktop_leak(tmp_path):
    """The engine's regression payload, held against *this* file's scans.

    The bite-1 audit planted exactly this in a scratch copy of the package
    and the first version of this suite stayed green — the same defect the
    engine's Phase 0 audit found in its first path scan, reintroduced by
    copying the weaker version. Both scans must catch it, here, forever.
    """
    leak = tmp_path / "leaky.py"
    leak.write_text(
        "import os\n"
        "from pathlib import Path\n"
        '_LEAK = Path(os.environ["HOME"]) / "Desktop" / "Nest"\n'
    )
    tree = ast.parse(leak.read_text())

    assert _home_reaches(tree), "the mechanism scan must catch os.environ['HOME']"

    caught = [
        v for _, v in _path_context_strings(tree)
        if {s.lower() for s in v.split("/")} & BANNED_SEGMENTS
    ]
    assert caught, "the literal scan must catch a bare 'Desktop' segment"


def _declared_distributions(pyproject_text: str) -> set[str]:
    """Every distribution name `dependencies = [...]` declares, normalised."""
    return {
        m.lower().replace("_", "-")
        for m in re.findall(r'"([A-Za-z0-9._-]+)', _dependency_block(pyproject_text))
    }


def _undeclared_imports(tree: ast.Module, declared: set[str]) -> list[str]:
    """Every top-level import in this tree that no declared distribution ships.

    The engine's ambient-dependency scan (I-27). This repo's own package and
    the stdlib are never third-party; everything else must arrive through a
    distribution `pyproject.toml` names, not one that happens to be installed.
    """
    dist_of = md.packages_distributions()
    offenders: list[str] = []
    for name in sorted(_toplevel_imports(tree)):
        if name in ("homestead", "homestead_health") or name in sys.stdlib_module_names:
            continue
        dists = {d.lower().replace("_", "-") for d in dist_of.get(name, [])}
        if not dists & declared:
            offenders.append(f"{name} (ships in {sorted(dists) or 'nothing installed'})")
    return offenders


def test_i27_every_third_party_import_is_declared():
    """Nothing is imported that `pyproject.toml` does not name — the engine's
    ambient-dependency scan, verbatim. The engine brings `holidays`, which
    brings `python-dateutil`, which brings `six`: all three are importable
    here without being declared, which is exactly the shape this forbids."""
    declared = _declared_distributions(
        (APP / "pyproject.toml").read_text(encoding="utf-8")
    )
    offenders: list[str] = []
    for mod in _modules():
        tree = ast.parse(mod.read_text(encoding="utf-8"))
        for hit in _undeclared_imports(tree, declared):
            offenders.append(f"{mod.relative_to(APP).as_posix()} imports {hit}")
    assert not offenders, (
        "every third-party import must be a declared dependency, not one that "
        f"happens to be installed. Found: {offenders}"
    )


def test_i27_scan_fires_on_a_planted_undeclared_import(tmp_path):
    """X7-drift-health: `test_i27_every_third_party_import_is_declared` had no
    plant anywhere in this suite — the exact gap *a scan that has never fired
    has not been shown to check anything* exists to name.

    Runs the scan itself (not a copy of its logic — the X7 audit's first cut
    re-implemented the loop here, so a weakening of the real scan would have
    left this green) over two planted files: one importing a package this
    project neither declares nor ships, and one importing only the stdlib and
    the engine, which must come back clean.
    """
    declared = _declared_distributions(
        (APP / "pyproject.toml").read_text(encoding="utf-8")
    )

    planted = tmp_path / "planted_undeclared_import.py"
    planted.write_text("import numpy\n", encoding="utf-8")
    caught = _undeclared_imports(ast.parse(planted.read_text(encoding="utf-8")), declared)
    assert [hit.split(" ")[0] for hit in caught] == ["numpy"], (
        f"the scan must catch an undeclared third-party import; got {caught}"
    )

    clean = tmp_path / "clean_import.py"
    clean.write_text("import json\nfrom homestead.keep import rungs\n", encoding="utf-8")
    assert _undeclared_imports(ast.parse(clean.read_text(encoding="utf-8")), declared) == [], (
        "and it must not fire on the stdlib or on the one declared dependency"
    )


def test_i28_no_test_basename_is_shadowed():
    """The engine's check, kept for the same reason: a shadowed basename is
    how a suite stops being seen."""
    names = [p.name for p in APP.rglob("test_*.py") if ".git" not in p.parts]
    assert len(names) == len(set(names)), f"duplicate test basenames: {names}"
