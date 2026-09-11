"""`--smoke` proves every import survived packaging — measured, not asserted.

`python -m homestead_health --smoke` says on the tin that it *"proves every
import survived packaging"*. Before the W0 audit it imported just four:
`nestor_seam`, `packs.immunizations`, `reference` and `roster`. The
package has sixteen modules today (it had fifteen then, before H6-sealed-reader
added `ledger_seam`) — `tests/test_docs_drift.py` holds that number and the one
in `__main__.py`'s own comment to the file list, because a count written in
prose is the thing this file exists to stop anyone writing.
A wheel that shipped without `server`, `cli`, `doses`, `intake`,
`school_form`, `due`, `emergency`, `living`, `reference_lane`, `nestor_store`
or `_egress` — a `packages = [...]` typo, a missing file, an import that only
resolves from a checkout — printed `smoke ok` and went out the door. The claim
was true of a quarter of the package and stated over all of it.

**So the list is scanned, not trusted.** The scan below reads the `--smoke`
branch of `homestead_health/__main__.py` and compares the modules it imports
against the package's own files on disk. A module added tomorrow without a line
in that branch fails here, by name. And because *a scan that has never fired
has not been shown to check anything*, the second test plants the omission —
deletes one import from a copy of the source — and asserts the scan names the
module that went missing.

The third test runs the real thing in a subprocess: the AST scan proves the
*names* are listed, and only an actual interpreter proves they import.
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from pathlib import Path

APP = Path(__file__).resolve().parent.parent
PKG = APP / "homestead_health"
MAIN = PKG / "__main__.py"

#: Not modules of the package in the sense that matters here: an `__init__` is
#: imported by importing anything beneath it (`packs.immunizations` pulls
#: `packs`), and `__main__` is the file doing the importing.
_NOT_A_MODULE = {"__init__", "__main__"}


def _package_modules() -> set[str]:
    """Every module in the package, dotted relative to it — `cli`,
    `packs.immunizations`. Read off the filesystem, so the expectation cannot
    drift from what is actually shipped."""
    out: set[str] = set()
    for path in PKG.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        if path.stem in _NOT_A_MODULE:
            continue
        rel = path.relative_to(PKG).with_suffix("")
        out.add(".".join(rel.parts))
    return out


def _smoke_branch(source: str) -> ast.If:
    """The `if "--smoke" in argv:` branch of `main()`."""
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.If):
            for sub in ast.walk(node.test):
                if isinstance(sub, ast.Constant) and sub.value == "--smoke":
                    return node
    raise AssertionError("__main__.py has no --smoke branch")


def _smoke_modules(source: str) -> set[str]:
    """The package modules the `--smoke` branch imports, dotted relative to the
    package.

    Only the *module* import forms count — `from homestead_health import cli`,
    `from homestead_health.packs import immunizations`, `import
    homestead_health.cli`. Deliberately: `from homestead_health.reference import
    SCHEDULE` (what the branch used to say) imports a **symbol**, and a symbol
    import proves nothing about the module next to it having survived
    packaging — it is the shape that let this scan be needed.
    """
    out: set[str] = set()
    branch = _smoke_branch(source)
    for node in ast.walk(branch):
        if isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            if node.module == "homestead_health":
                prefix = ""
            elif node.module.startswith("homestead_health."):
                prefix = node.module[len("homestead_health."):]
            else:
                continue
            for alias in node.names:
                out.add(f"{prefix}.{alias.name}" if prefix else alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.startswith("homestead_health."):
                    out.add(alias.name[len("homestead_health."):])
    return out


def test_smoke_imports_every_module_in_the_package():
    """The claim on the tin, measured against the package's own file list."""
    expected = _package_modules()
    imported = _smoke_modules(MAIN.read_text(encoding="utf-8"))
    missing = sorted(expected - imported)
    assert not missing, (
        "`--smoke` says it proves every import survived packaging, and these "
        f"modules are not in its branch: {missing}. Add a line for each in "
        "homestead_health/__main__.py, or the claim is false for them."
    )
    # And nothing listed that does not exist — a stale line is a name that
    # would fail at run time and a scan that passes for the wrong reason.
    stale = sorted(imported - expected)
    assert not stale, f"`--smoke` imports modules that are not in the package: {stale}"


def test_the_scan_catches_a_planted_omission(tmp_path):
    """A scan that has never fired has not been shown to check anything.

    Delete one import from a copy of `__main__.py` — the exact edit a future
    module addition makes by *omission* — and the scan must name it.
    """
    source = MAIN.read_text(encoding="utf-8")
    planted = re.sub(r"^ +from homestead_health import doses\n", "", source,
                     count=1, flags=re.MULTILINE)
    assert planted != source, "the plant did not apply; the import line moved"

    still_imported = _smoke_modules(planted)
    assert "doses" not in still_imported
    missing = sorted(_package_modules() - still_imported)
    assert missing == ["doses"], (
        f"the scan must name the omitted module and nothing else; got {missing}"
    )


def test_smoke_actually_runs_and_imports_them_for_real():
    """The AST scan proves the names are listed. Only an interpreter proves
    they import — a module named in the branch and broken on disk would sail
    past a scan that reads source alone."""
    result = subprocess.run(
        [sys.executable, "-m", "homestead_health", "--smoke"],
        cwd=APP, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "smoke ok" in result.stdout


def test_the_console_script_the_docs_tell_the_operator_to_run_is_declared():
    """`homestead-health <command>` — what `--help` prints and every line of the
    README's entry recipe begins with — must be a command `pip install` creates.

    It was not declared at all: `pyproject.toml` had no `[project.scripts]`, so
    a household that installed the package got one whose own usage text named a
    command that did not exist. Read from the file rather than from installed
    metadata, so the check holds on a cold checkout too.
    """
    pyproject = (APP / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"^\[project\.scripts\]\s*$(.*?)^\[", pyproject,
                      re.MULTILINE | re.DOTALL)
    assert block, "pyproject.toml declares no console script"
    entry = re.search(r'^homestead-health\s*=\s*"([^"]+)"', block.group(1), re.MULTILINE)
    assert entry, f"the `homestead-health` script is missing: {block.group(1)!r}"

    module, _, attribute = entry.group(1).partition(":")
    import importlib
    target = getattr(importlib.import_module(module), attribute, None)
    assert callable(target), f"{entry.group(1)} does not resolve to a callable"

    # And the name is the one the docs use, in both places.
    usage = (PKG / "__main__.py").read_text(encoding="utf-8")
    assert "homestead-health <command>" in usage
    assert "homestead-health dose add" in (APP / "README.md").read_text(encoding="utf-8")
