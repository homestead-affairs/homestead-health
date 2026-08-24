"""homestead-health's entry point.

Three ways in, plus ``--help``:
  * ``--help`` / ``-h`` — print this usage and exit 0.
  * ``--smoke`` — start, prove every import survived packaging, exit without a
    display.
  * a CLI command (resolve, decisions, put, roster, verify, ui) — real work on
    real data, wired through Nestor's entity resolution and decision memory.
    Operates on the household root, not a throwaway.
"""
from __future__ import annotations

import sys

USAGE = """\
usage: python -m homestead_health [--help] [--smoke]
       homestead-health <command> [args...]

  --help, -h   show this message and exit
  --smoke      prove every import survived packaging; exit without a display

commands (real data, requires nestor-meaning):
  resolve      resolve <domain> <surface> — entity resolution
  decisions    decisions <propose|check|list> — care decisions
  put          put <field> <value> — store an immunization record
  roster       roster <add|list> — household members
  verify       verify — check the Nestor ledger chain
  ui           ui [--port N] — intake and dashboard in the browser
"""

_CLI_COMMANDS = {"resolve", "decisions", "put", "roster", "verify", "ui"}


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
