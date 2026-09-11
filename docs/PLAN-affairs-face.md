# The Homestead · Affairs plan — this module's face

This is not a new plan. It is the health-naming excerpts of
`so-lets-plan-it-sparkling-shell.md` (the Homestead · Affairs build-out plan,
held by the orchestrating session — this repo does not carry the full
document) copied verbatim, one bite struck through as its PR lands. Unlanded
items stay unstruck. `tests/test_plan_affairs_face.py` asserts every struck
line names a PR number, so a strikethrough here can never be wishful.

Struck lines carry `(#PR, released X.Y.Z)` — **both**, because a PR number
says a change merged and a release number says it shipped, and the two are not
the same event here (#20 merged before 0.2.1 was cut). PR numbers and release
versions are read from this repo's own `git log`/`CHANGELOG.md`, not asserted
from memory. A bite named in the plan but not yet landed keeps its plain text,
and every health bite the plan names has an entry here whether it landed or
not — this file does not get ahead of what merged, and it does not quietly
drop what has not started.

## Wave 0 — land the base (parallel)

~~**W0-HEALTH** `homestead-health`, existing branch. Audit+fix+PR. Flag
`RECORD_SYNCED` use (fixed in H2-cap); concurrent-add race refused by the
store (test exists).~~ (#17, released 0.2.0 — "feat: dose records a household
enters itself, by subject"; audit findings and fixes recorded in
`docs/audits/w0-records-entry-audit.md`.)

## Wave 2 — modules adopt 0.3.0 (parallel)

~~**H2-cap** health `build(deps):` — `>=0.3.0,<1.0` (rationale reversal
recorded); `doses.py` logs `RECORD_ADDED`. Test imports the symbol so CI
proves the floor.~~ (#19, released 0.2.1 — "build(deps): lift the engine cap
to <1.0 and log RECORD_ADDED for a dose".)

## Wave 6 — Phase 4 sealing

~~**H6-sealed-reader** health `fix:` (found by the E6 audit, 2026-09-11) —
`homestead_health/living.py` `LivingLane.replacements()` reads the integrity
log file with raw `json.loads`, so a sealed `living.jsonl` answers "never
replaced" instead of refusing; route it through the engine's `IntegrityLog`
reader (the door `sync._already_delivered` uses) and plant a sealed log in the
test.~~ (#23, released 0.2.2 — "fix: read the living log through the engine's
reader so a sealed log refuses instead of answering 'never replaced'".)

**E7-public-log-reader** engine `feat:` (proposed by the H6 audit,
2026-09-11) — `IntegrityLog._entries()` is the engine's one reader that skips
boundary rows, decrypts sealed lines and refuses by name, and it already has
callers in `keep/sync`, `keep/export` and (via a documented seam)
`homestead_health`. Give it a public name whose signature carries the
refusal (`entries_for_audit(*, decrypt=True)` or `read_entries`), keep
`_entries()` as a deprecated alias for one minor, and narrow
`test_sealed_log_has_no_public_read_method` from "no public reader" to "no
public reader that can return a short or plaintext-fallback answer". Health's
`ledger_seam.py` then becomes a one-line pass-through. *(Engine bite, not
health's to land or strike — tracked here because `ledger_seam.py` is the
named caller. As of this bite, the installed engine (0.11.0) still has no
`read_entries`/`entries_for_audit`; `homestead_health/ledger_seam.py` still
reaches the private `_entries()` as the documented one-time exception.)*

**H7-floor-0.12** health `fix:` — when the floor rises to 0.12.0, the seam
calls `read_entries` and maps the new `IntegrityIncompleteError` (a truncated
or deleted log with a surviving anchor) to `LedgerUnreadable`; plant a chopped
log. *(Health's, and unlanded: it cannot start until E7 ships a 0.12.0 engine.
The floor here is still `>=0.11.0,<1.0` and `IntegrityIncompleteError` does not
exist in the installed engine, so there is nothing yet to map. The X7 drift
sweep added this entry: the bite is named in the plan and was missing from this
face, which is the same drift in the other direction — a face that omits an
unlanded bite reads as if nothing is outstanding.)*

## Wave 7 — drift and closure sweep (one bite per repo, `test:`/`docs:`)

**X7-drift-health** — `tests/test_docs_drift.py` grep-guards for known stale
sentences; the meta-scan `tests/test_scans_fire.py` (every AST-guard helper
must have a planted-violation test; itself planted); README status tables;
`docs/PLAN-affairs-face.md` = this plan with items struck through as they
land. *(This bite. Unstruck on its own branch, `claude/health-drift` — a bite
does not strike itself before the orchestrator has opened and merged its PR;
the strikethrough and PR number land in the same commit the orchestrator
makes, or a follow-up on this branch once merged.)*
