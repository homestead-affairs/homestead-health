"""CLI commands for homestead-health — entity resolution, care decisions, roster, intake.

Every command here operates on a real household root (``$HOMESTEAD_HOME`` or
``~/.homestead``), not a throwaway.  Nestor's seam is bound and a SqliteStore
is opened at ``<root>/nestor-health.db`` before any command runs.

**Covenant**: no command here seals anything.  ``resolve`` proposes; ``decisions
propose`` proposes.  Sealing is a human act, done through ``nestor ui`` or a
caller that passes a ``verifier=`` — never through this CLI.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Sequence

from homestead.keep import paths

from homestead_health import nestor_seam
from homestead_health.nestor_store import get_store
from homestead_health.packs.immunizations import FIELDS, MATTER

__all__ = ["run_cli"]

# ── bootstrap ───────────────────────────────────────────────────────────────

def _boot(household_root: Path | None = None) -> None:
    """Bind the seam and ensure the household root exists."""
    root = Path(household_root) if household_root is not None else paths.home()
    root.mkdir(parents=True, exist_ok=True)
    (root / "keep").mkdir(parents=True, exist_ok=True)
    nestor_seam.bind(root)


# ── resolve ─────────────────────────────────────────────────────────────────

def _cmd_resolve(args: Sequence[str]) -> int:
    """``resolve <domain> <surface>`` — resolve an entity against sealed aliases."""
    if len(args) < 2:
        print("usage: homestead-health resolve <domain> <surface>", file=sys.stderr)
        print("  domains: provider, vaccine", file=sys.stderr)
        return 1

    domain = args[0]
    surface = " ".join(args[1:])
    valid = ("provider", "vaccine")
    if domain not in valid:
        print(f"unknown domain {domain!r} — one of {valid}", file=sys.stderr)
        return 1

    _boot()
    store = get_store()
    resolver = nestor_seam.resolver_for(domain, store)
    result = resolver.resolve(surface)

    if result["sealed"]:
        print(f"  {surface}")
        print(f"  → {result['canonical']}  (sealed, confidence {result['confidence']:.2f})")
        prov = result.get("provenance", {})
        if prov.get("verifier"):
            print(f"    verified by: {prov['verifier']}")
    elif result["provenance"].get("suggestion"):
        print(f"  {surface}")
        print(f"  ~ {result['provenance']['suggestion']}  (draft suggestion, confidence {result['confidence']:.2f})")
        print(f"    not sealed — use `nestor ui` to seal")
    else:
        print(f"  {surface}")
        print(f"  ? no match")
    return 0


# ── decisions (care memory) ─────────────────────────────────────────────────

def _cmd_decisions(args: Sequence[str]) -> int:
    """``decisions <subcommand> ...`` — care decisions."""
    if not args:
        print("usage: homestead-health decisions <propose|check|list> ...", file=sys.stderr)
        return 1

    sub = args[0]
    rest = args[1:]

    _boot()
    store = get_store()
    dm = nestor_seam.decisions_for("care", store)

    if sub == "propose":
        if len(rest) < 2:
            print("usage: homestead-health decisions propose <question> <commitment>", file=sys.stderr)
            return 1
        question = rest[0]
        commitment = " ".join(rest[1:])
        result = dm.propose(question, commitment, origin="homestead-health")
        print(f"  proposed: {question}")
        print(f"         → {commitment}")
        print(f"  pair_id: {result['id']}")
        print(f"  status:  {result['status']}  (seal with `nestor ui`)")
        return 0

    elif sub == "check":
        if not rest:
            print("usage: homestead-health decisions check <question>", file=sys.stderr)
            return 1
        question = " ".join(rest)
        result = dm.constraints_on(question, fuzzy_bar=0.45)
        print(f"  question: {question}")
        print(f"  match:    {result['match']} (similarity {result['similarity']:.2f})")
        if result["live"]:
            live = result["live"]
            seal_mark = "sealed" if live["sealed"] else "draft"
            print(f"  live:     {live['commitment']}  ({seal_mark})")
        else:
            print(f"  live:     (none)")
        return 0

    elif sub == "list":
        decisions = dm.all_decisions()
        if not decisions:
            print("  (no care decisions recorded)")
            return 0
        print(f"  {len(decisions)} decision(s):")
        for i, d in enumerate(decisions, 1):
            seal_mark = "sealed" if d.get("status") == "sealed" else "draft"
            q = d.get("source_text", "?")
            c = d.get("target_text", "?")
            print(f"  {i}. [{seal_mark}] {q}")
            print(f"     → {c}")
        return 0

    else:
        print(f"unknown subcommand {sub!r} — one of: propose, check, list", file=sys.stderr)
        return 1


# ── put (record input) ──────────────────────────────────────────────────────

def _cmd_put(args: Sequence[str]) -> int:
    """``put <field> <value>`` — store an immunization record field."""
    if len(args) < 2:
        print("usage: homestead-health put <field> <value>", file=sys.stderr)
        print(f"  fields: {', '.join(FIELDS)}", file=sys.stderr)
        return 1

    field = args[0]
    value = " ".join(args[1:])

    if field not in FIELDS:
        print(f"unknown field {field!r} — fields: {', '.join(FIELDS)}", file=sys.stderr)
        return 1

    from homestead.keep.record import Sidecar
    from homestead.keep.rungs import Classified

    rung = FIELDS[field]
    derived = None
    if rung.value in ("L3", "L4"):
        derived = f"A {field.replace('_', ' ')} is on file"

    _boot()
    sidecar = Sidecar()
    item = Classified(rung, value, derived)
    item_id = f"cli-{field}-{hash(value) & 0xFFFFFFFF:08x}"
    sidecar.put(MATTER, field, item_id, item, overwrite=True)

    print(f"  stored: {MATTER}/{field}/{item_id}")
    print(f"  rung:   {rung.value}")

    if field == "provider":
        try:
            store = get_store()
            resolver = nestor_seam.resolver_for("provider", store)
            resolver.propose(value, value, reason=f"entered as {field}")
            print(f"  proposed to provider resolver: {value}")
        except Exception:
            pass

    return 0


# ── roster ──────────────────────────────────────────────────────────────────

def _cmd_roster(args: Sequence[str]) -> int:
    """``roster <add|list> ...`` — household member management."""
    from homestead.keep.record import Sidecar
    from homestead.keep.rungs import Surface, serve

    if not args:
        print("usage: homestead-health roster <add|list> ...", file=sys.stderr)
        return 1

    sub = args[0]
    rest = args[1:]

    _boot()

    from homestead_health.roster import Roster
    sidecar = Sidecar()
    roster = Roster(sidecar)

    if sub == "add":
        if not rest:
            print("usage: homestead-health roster add <name> [--minor]", file=sys.stderr)
            return 1
        minor = "--minor" in rest
        name_parts = [a for a in rest if a != "--minor"]
        name = " ".join(name_parts)
        ref = roster.add(name=name, minor=minor)
        print(f"  enrolled: {ref}  ({'minor' if minor else 'adult'})")
        return 0

    elif sub == "list":
        subjects = roster.subjects()
        if not subjects:
            print("  (no household members enrolled)")
            return 0
        print(f"  {len(subjects)} member(s):")
        for ref in subjects:
            record = roster.name_of(ref)
            served = serve(record, Surface.S1_DETAIL)
            display = str(served.value) if served.value else str(ref)
            m = "minor" if roster.is_minor(ref) else "adult"
            print(f"  {ref}  {display}  ({m})")
        return 0

    else:
        print(f"unknown subcommand {sub!r} — one of: add, list", file=sys.stderr)
        return 1


# ── verify ──────────────────────────────────────────────────────────────────

def _cmd_verify(args: Sequence[str]) -> int:
    """``verify`` — verify the Nestor ledger chain."""
    _boot()
    ok = nestor_seam.verify_ledger()
    if ok:
        print("  ledger: intact")
    else:
        print("  ledger: BROKEN — the hash chain does not verify", file=sys.stderr)
    return 0 if ok else 1


# ── ui ──────────────────────────────────────────────────────────────────────

def _cmd_ui(args: Sequence[str]) -> int:
    """``ui [--port N]`` — open the intake and dashboard UI in a browser."""
    from homestead_health.server import serve

    port = 8384
    i = 0
    while i < len(args):
        if args[i] == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        else:
            i += 1

    serve(port=port)
    return 0


# ── dispatch ────────────────────────────────────────────────────────────────

COMMANDS = {
    "resolve": (_cmd_resolve, "resolve <domain> <surface> — entity resolution"),
    "decisions": (_cmd_decisions, "decisions <propose|check|list> — care decisions"),
    "put": (_cmd_put, "put <field> <value> — store an immunization record"),
    "roster": (_cmd_roster, "roster <add|list> — household members"),
    "verify": (_cmd_verify, "verify — check the Nestor ledger chain"),
    "ui": (_cmd_ui, "ui — intake and dashboard in the browser"),
}


def run_cli(argv: Sequence[str]) -> int:
    """Dispatch to a CLI command.  Returns the exit code."""
    if not argv:
        print("homestead-health commands:", file=sys.stderr)
        for name, (_, desc) in COMMANDS.items():
            print(f"  {name:12s} {desc}", file=sys.stderr)
        return 1

    cmd = argv[0]
    if cmd not in COMMANDS:
        print(f"unknown command {cmd!r}", file=sys.stderr)
        print(f"  commands: {', '.join(COMMANDS)}", file=sys.stderr)
        return 1

    handler, _ = COMMANDS[cmd]
    return handler(list(argv[1:]))
