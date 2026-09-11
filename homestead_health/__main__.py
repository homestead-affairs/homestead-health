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
        from homestead_health import nestor_seam  # noqa: F401
        from homestead_health.packs import immunizations  # noqa: F401
        from homestead_health.reference import SCHEDULE  # noqa: F401
        from homestead_health.roster import Roster  # noqa: F401
        print("homestead-health: smoke ok")
        return 0

    if argv and argv[0] in _CLI_COMMANDS:
        from homestead_health.cli import run_cli
        return run_cli(argv)

    print(USAGE, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
