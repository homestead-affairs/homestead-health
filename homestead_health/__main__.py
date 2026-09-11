"""homestead-health's entry point.

Three ways in, plus ``--help``:
  * ``--help`` / ``-h`` — print this usage and exit 0.
  * ``--smoke`` — start, prove every import survived packaging, exit without a
    display.
  * a CLI command (roster, dose, today, export, ui; and with the `entity`
    extra, resolve, decisions, verify) — real work on real data in the
    household root, not a throwaway. Entering and reading records needs only
    the engine; the Nestor-backed commands say so when the extra is missing.
"""
from __future__ import annotations

import sys

USAGE = """\
usage: python -m homestead_health [--help] [--smoke]
       homestead-health <command> [args...]

  --help, -h   show this message and exit
  --smoke      prove every import survived packaging; exit without a display

commands (real data, in the household root — $HOMESTEAD_HOME or ~/.homestead):
  roster       roster <add|list> — household members (opaque ids, names gated)
  dose         dose add <subject> <vaccine> <date> [--next-due D] [--provider P]
                        [--lot L] [--source S] [--notes N]
               dose list <subject> · dose show <dose-id>
  today        today [--today YYYY-MM-DD] — the Today line, k ≥ 2 gated
  export       export <subject> — the school form, to exports/
  ui           ui [--port N] — entry forms, intake and records in the browser

commands that need the `entity` extra (pip install 'homestead-health[entity]'):
  resolve      resolve <domain> <surface> — entity resolution
  decisions    decisions <propose|check|list> — care decisions
  verify       verify — check the Nestor ledger chain
"""

_CLI_COMMANDS = {
    "resolve", "decisions", "put", "roster", "dose", "today", "export", "verify", "ui",
}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv

    if "--help" in argv or "-h" in argv:
        print(USAGE, end="")
        return 0

    if "--smoke" in argv:
        # **Every module in the package, by name.** The claim on the tin is
        # "prove every import survived packaging", and a smoke test that imports
        # four of sixteen modules does not make it: a wheel missing `server`,
        # `cli`, `doses`, `intake` or `school_form` printed "smoke ok" and
        # shipped. `tests/test_invariants_smoke.py` scans this branch against
        # the package's own file list, so a module added without a line here is
        # a build failure — the list cannot rot quietly.
        #
        # Import-only, and that is the whole of it: no module below reads a
        # clock, touches the household root, or dials on import (I-26/I-17), so
        # importing them all is exactly as inert as importing one.
        from homestead_health import _egress
        from homestead_health import cli
        from homestead_health import doses
        from homestead_health import due
        from homestead_health import emergency
        from homestead_health import intake
        from homestead_health import ledger_seam
        from homestead_health import living
        from homestead_health import nestor_seam
        from homestead_health import nestor_store
        from homestead_health import reference
        from homestead_health import reference_lane
        from homestead_health import roster
        from homestead_health import school_form
        from homestead_health import server
        from homestead_health.packs import immunizations

        # Bound, not discarded: an import whose name nothing reads is one a
        # linter offers to delete, and this list is the test.
        imported = (_egress, cli, doses, due, emergency, intake, ledger_seam,
                    living, nestor_seam, nestor_store, reference, reference_lane,
                    roster, school_form, server, immunizations)
        print(f"homestead-health: smoke ok ({len(imported)} modules)")
        return 0

    if argv and argv[0] in _CLI_COMMANDS:
        from homestead_health.cli import run_cli
        return run_cli(argv)

    print(USAGE, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
