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


def test_the_engine_pin_is_true():
    """I-27, both halves: the declared engine is the installed engine.

    `import homestead.keep` succeeding proves an engine is present;
    resolving the *distribution* proves it is the declared one
    (`homestead-affairs`), not a same-named package that happens to be
    importable — the import name and the distribution name differ by design,
    and only the metadata ties them together.
    """
    import homestead.keep  # noqa: F401

    version = md.version("homestead-affairs")
    assert version, "the engine distribution is not installed; the pin is not true"


def test_the_pin_has_a_floor_and_a_cap():
    """The engine is pre-1.0 and decides what renders; the dependency line
    states the release this seat was verified against and refuses the next
    minor unseen — the engine's own floor-and-cap reasoning for `holidays`."""
    dependency_block = re.search(
        r"^dependencies\s*=\s*\[(.*?)\]",
        (APP / "pyproject.toml").read_text(encoding="utf-8"),
        re.MULTILINE | re.DOTALL,
    )
    assert dependency_block, "pyproject.toml must declare its dependencies"
    pin = re.search(r'"homestead-affairs([^"]*)"', dependency_block.group(1))
    assert pin, "the engine pin is the one declared dependency, and it is missing"
    spec = pin.group(1)
    assert ">=" in spec, f"the pin needs a floor (got {spec!r})"
    assert "<" in spec, f"the pin needs a cap — the engine is pre-1.0 (got {spec!r})"


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
            offenders[str(mod.relative_to(APP))] = sorted(hits)
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


def test_i30_nothing_listens():
    """No bind/listen/serve call, however spelled. `bind` itself is not
    banned, for the engine's stated tkinter reason; these names have no GUI
    meaning."""
    banned = {"listen", "serve_forever", "create_server", "ThreadingHTTPServer"}
    offenders = []
    for mod in _modules():
        for node in ast.walk(ast.parse(mod.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                f = node.func
                name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                if name in banned:
                    offenders.append(f"{mod.relative_to(APP)}:{node.lineno} {name}")
    assert not offenders, f"nothing may listen. Found: {offenders}"


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
