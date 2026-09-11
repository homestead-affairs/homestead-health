"""CLI commands for homestead-health — entity resolution, care decisions, roster, intake.

Every command here operates on a real household root (``$HOMESTEAD_HOME`` or
``~/.homestead``), not a throwaway.  Nestor's seam is bound and a SqliteStore
is opened at ``<root>/nestor-health.db`` before any command runs.

**Covenant**: no command here seals anything.  ``resolve`` proposes; ``decisions
propose`` proposes.  Sealing is a human act, done through ``nestor ui`` or a
caller that passes a ``verifier=`` — never through this CLI.

**Nestor is optional.** ``roster``, ``dose``, ``today`` and ``export`` — the
commands a household uses to enter and read its own records — need only the
engine.  ``resolve``, ``decisions`` and ``verify`` need the ``entity`` extra and
say so, in one line, when it is missing.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Sequence

from homestead.keep import paths

from homestead_health import nestor_seam
from homestead_health.nestor_store import get_store

__all__ = ["run_cli"]

# ── bootstrap ───────────────────────────────────────────────────────────────

def _boot(household_root: Path | None = None) -> None:
    """Bind the seam and ensure the household root exists."""
    root = Path(household_root) if household_root is not None else paths.home()
    root.mkdir(parents=True, exist_ok=True)
    (root / "keep").mkdir(parents=True, exist_ok=True)
    nestor_seam.bind(root)


def _needs_nestor() -> bool:
    """True when the Nestor-backed command can run; otherwise says why not."""
    if nestor_seam.available():
        return True
    print(f"  {nestor_seam.NOT_INSTALLED}", file=sys.stderr)
    return False


def _flag(args: Sequence[str], name: str) -> tuple[list[str], str | None]:
    """Pull ``--name value`` out of ``args``; return the rest and the value."""
    rest: list[str] = []
    value: str | None = None
    i = 0
    while i < len(args):
        if args[i] == name and i + 1 < len(args):
            value = args[i + 1]
            i += 2
        else:
            rest.append(args[i])
            i += 1
    return rest, value


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
    if not _needs_nestor():
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

    if not _needs_nestor():
        return 1
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


# ── dose (record input, by subject) ─────────────────────────────────────────

_DOSE_USAGE = """\
usage: homestead-health dose add <subject> <vaccine> <date> [--next-due D] [--provider P]
                                 [--lot L] [--source S] [--notes N]
       homestead-health dose list <subject>
       homestead-health dose show <dose-id>
  e.g.: homestead-health dose add subj-01 MMR 2026-08-15 --next-due 2026-09-20 --provider "Dr. Lee"
"""


def _cmd_dose(args: Sequence[str]) -> int:
    """``dose <add|list|show> ...`` — a subject's immunization doses.

    ``add`` records one dose for an enrolled subject, composed to the pack's
    rungs (a dose is L4; no rung is chosen here). ``list`` shows the subject's
    doses as the list pane would — the derived form, since a dose is L4 — with
    each next-due date (L2) beside it. ``show`` opens one dose in the detail
    pane, where it renders in full.
    """
    from homestead.keep.dates import UnparseableDate
    from homestead.keep.export import ExportRefused
    from homestead.keep.record import Sidecar
    from homestead.keep.rungs import Disposition, Surface, serve

    from homestead_health import doses
    from homestead_health.roster import Roster

    if not args:
        print(_DOSE_USAGE, end="", file=sys.stderr)
        return 1
    sub, rest = args[0], list(args[1:])

    _boot()
    sidecar = Sidecar()
    roster = Roster(sidecar)

    if sub == "add":
        rest, next_due = _flag(rest, "--next-due")
        rest, provider = _flag(rest, "--provider")
        rest, lot = _flag(rest, "--lot")
        rest, source = _flag(rest, "--source")
        rest, notes = _flag(rest, "--notes")
        # Exactly three positionals. `< 3` silently dropped the extras, so
        # `dose add subj-01 MMR 2026-08-15 2026-09-20` — the flag forgotten —
        # recorded the dose with **no next-due date at all** and said nothing:
        # a dropped fact reported as a success, which is the shape H-4 refuses
        # ("a recorded gap, never a silent promotion to certainty").
        if len(rest) != 3:
            print(_DOSE_USAGE, end="", file=sys.stderr)
            if len(rest) > 3:
                print("  (a dose is subject, vaccine and date — everything else "
                      "is a named flag)", file=sys.stderr)
            return 1
        subject, vaccine, date = rest[0], rest[1], rest[2]
        try:
            ref = doses.add_dose(
                sidecar, roster, subject=subject, vaccine=vaccine, dose_date=date,
                next_due=next_due, provider=provider, lot_number=lot, source=source,
                notes=notes,
            )
        # Every refusal `add_dose` documents, in one place. ExportRefused is a
        # PermissionError and FileExistsError an OSError — neither is a
        # ValueError, so catching only ValueError turned the two most likely
        # real-world refusals (the operator typing a *name* where the subject id
        # goes; a second process minting the same id) into a traceback that also
        # echoed whatever was typed.
        except ExportRefused as exc:
            print(f"  refused: {exc}", file=sys.stderr)
            print("  a subject is the roster's opaque id (subj-01), never a name "
                  "— `homestead-health roster list`", file=sys.stderr)
            return 1
        except FileExistsError:
            print("  refused: another writer took that dose id between counting "
                  "and writing. Nothing was stored (I-9) — run the same command "
                  "again.", file=sys.stderr)
            return 1
        except (ValueError, UnparseableDate) as exc:
            print(f"  refused: {exc}", file=sys.stderr)
            return 1
        print(f"  recorded: {ref}  (rung L4)")
        if next_due:
            print(f"  next due: {next_due}")
        if provider and nestor_seam.available():
            try:
                resolver = nestor_seam.resolver_for("provider", get_store())
                resolver.propose(provider, provider, reason="entered as provider")
                print(f"  proposed to provider resolver: {provider}")
            except Exception:
                pass
        return 0

    if sub == "list":
        if not rest:
            print(_DOSE_USAGE, end="", file=sys.stderr)
            return 1
        subject = rest[0]
        if subject not in roster:
            print(f"  {subject}: not on the roster", file=sys.stderr)
            return 1
        found = doses.doses_of(sidecar, subject)
        if not found:
            print(f"  {subject}: no doses on file — `homestead-health dose add {subject} <vaccine> <date>`")
            return 0
        due_by = {ref.id: rec for ref, rec in doses.next_due_of(sidecar, subject)}
        print(f"  {subject}: {len(found)} dose(s)")
        for ref, record in found:
            row = doses.list_row(record)
            if row is None:
                continue
            rung, text = row
            line = f"  [{rung.value}]  {ref.id}: {text}"
            nxt = due_by.get(ref.id)
            if nxt is not None:
                nxt_text = doses.next_due_text(nxt)
                if nxt_text is not None:
                    line += f"  ·  next due {nxt_text}"
            print(line)
        return 0

    if sub == "show":
        if not rest:
            print(_DOSE_USAGE, end="", file=sys.stderr)
            return 1
        try:
            ref = doses.dose_ref(rest[0])
        except ValueError as exc:
            print(f"  {exc}", file=sys.stderr)
            return 1
        match = [rec for r, rec in doses.doses_of(sidecar, ref.subject) if r.id == ref.id]
        if not match:
            print(f"  {ref.id}: no such dose", file=sys.stderr)
            return 1
        served = serve(match[0], Surface.S1_DETAIL)
        print(f"  {ref.id}  [{served.rung.value}]")
        if served.disposition is Disposition.RENDER and isinstance(served.value, dict):
            for name, value in served.value.items():
                print(f"  {name.replace('_', ' ')}: {value}")
        elif served.disposition is Disposition.RENDER:
            print(f"  {served.value}")
        else:
            print("  This record is sealed and is not shown here.")
        return 0

    print(f"unknown subcommand {sub!r} — one of: add, list, show", file=sys.stderr)
    return 1


# ── today ────────────────────────────────────────────────────────────────────

def _cmd_today(args: Sequence[str]) -> int:
    """``today [--today YYYY-MM-DD]`` — the Today line, if a count survives the
    k ≥ 2 re-identification check over the household (H-2, I-31). Nothing is
    drawn when nothing survives; that is an absence, never a zero."""
    import datetime as dt

    from homestead.keep.record import Sidecar

    from homestead_health import doses
    from homestead_health.roster import Roster

    _rest, today = _flag(args, "--today")
    today = today or dt.date.today().isoformat()

    _boot()
    sidecar = Sidecar()
    try:
        line = doses.today_line(sidecar, Roster(sidecar), today=today)
    except (ValueError, TypeError) as exc:
        # `--today garbage` reached `parse_deadline` and came back out as a
        # traceback. The engine refuses to guess at a date (BUG-1); so does this.
        print(f"  refused: {exc}", file=sys.stderr)
        return 1
    print(f"  {line}" if line else "  (nothing to show)")
    return 0


# ── export (the school form) ─────────────────────────────────────────────────

def _cmd_export(args: Sequence[str]) -> int:
    """``export <subject>`` — the school form: the subject's immunization
    history out through S4 with a declared purpose, one entry to each log,
    the head anchor printed for the operator to record off the machine."""
    from homestead.keep.export import ExportRefused
    from homestead.keep.record import Sidecar

    from homestead_health import doses
    from homestead_health.school_form import export_history

    if not args:
        print("usage: homestead-health export <subject>", file=sys.stderr)
        return 1
    subject = args[0]

    _boot()
    sidecar = Sidecar()
    try:
        receipt = export_history(subject, [rec for _, rec in doses.doses_of(sidecar, subject)])
    except (ExportRefused, ValueError) as exc:
        print(f"  refused: {exc}", file=sys.stderr)
        return 1
    print(f"  exported: {receipt.artifact}")
    print(f"  head:     {receipt.head}  (record this off the machine)")
    return 0


# ── put (retired) ────────────────────────────────────────────────────────────

def _cmd_put(args: Sequence[str]) -> int:
    """``put`` is retired: a lone field under a random id was a record nothing
    could find. A dose is entered whole, by subject, with ``dose add``."""
    print("  `put` is retired — a dose is entered whole, by subject:", file=sys.stderr)
    print(_DOSE_USAGE, end="", file=sys.stderr)
    return 1


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
    if not _needs_nestor():
        return 1
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
    "roster": (_cmd_roster, "roster <add|list> — household members"),
    "dose": (_cmd_dose, "dose <add|list|show> — a subject's immunization doses"),
    "today": (_cmd_today, "today — the gated Today line"),
    "export": (_cmd_export, "export <subject> — the school form, to exports/"),
    "put": (_cmd_put, "put — retired; use `dose add`"),
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
