# Homestead · Health

**Family health records the household holds itself.** Module three on
**Homestead · Affairs**, sibling to `homestead-law` and `homestead-ledger`,
incubating here toward promotion to `rudi193-cmd/homestead-health` — the
law-gazelle → homestead-law path, walked again.

The design is
[`homestead/docs/PLAN-homestead-health.md`](https://github.com/rudi193-cmd/homestead/blob/main/docs/PLAN-homestead-health.md):
the packs (immunizations first — one pack proves the seam), the rungs field by
field, the module invariants H-1…H-5, and the five bites.

**Status: the whole plan is built and green — the records track (bites 1–5,
H-1–H-5, `UNBUILT` empty) and both lanes of the 2026-08-17 extension (the living
lane, bite 7/H-8, and the reference lane, bite 6/H-7).** The extension remains
**proposed, not ratified** (`verified_by ≠ author`). Bite 1 — **the
seat** — pins the engine and proves the pin. Bite 2 — **the roster**
(`homestead_health/roster.py`) — is subjects before records: opaque ids
(`subj-01`, minted by a counter, never derived from the person), the id →
person mapping stored through `homestead.keep`'s record layer and reached only
through the gate, a subject's name held at `L4` when the subject is a minor and
`L3` otherwise, and a `VisibleLog` line that carries the id and nothing of the
name (H-1). A subject survives a restart. Bite 3 — **the immunizations pack**
(`homestead_health/packs/immunizations.py`) — is health's first real schema,
classified at import in the custody pack's exact shape: the subject id (`L3`),
the vaccine (`L4`, a medical act on a person), dates that name nobody by
themselves (`L2`, while the record composes to `L4`), provider and source
(`L3`), and notes (`L4`); deleting one field's rung fails the build naming it
(H-4). Bite 4 — **due onto Today** (`homestead_health/due.py`) — computes the
next dose on **calendar** days (a booster interval does not skip weekends, so a
Saturday due date stays Saturday — not `court_days`) and renders the Today line
only when its count survives the engine's k ≥ 2 re-identification gate
(`cover_counts`, applied to the household's subjects): a two-child household
renders "2 immunizations due this month", a one-child household renders nothing,
from a **closed** operator-facing vocabulary that has no slot for advice (H-2).
Bite 5 — **the school form** (`homestead_health/school_form.py`) — is health's
first purposed egress: it serves a subject's several doses through `S4_EGRESS`
with a declared purpose (never reaching a `.payload`), composes them into one
form, and exports through `homestead.keep`'s export path — the artifact to
`exports/`, one `IntegrityLog` entry and one `VisibleLog` `EXPORTED` act carrying
references and no content (I-15), the head anchor held off the log's own tree and
returned to record off the machine, so a hand-edited entry fails
`verify(expected_head=…)`. **H-5 — the pinned reference snapshot**
(`homestead_health/reference.py`) — is the public CDC/ACIP immunization schedule
carried as a versioned, dated snapshot that names its own edition, holds **no
subject**, reads no clock, and dials for nothing (I-17): public reference the
operator pins and updates by a deliberate act, never a runtime fetch, and never
joined to a child (the H-2 wall). **H-3 — the emergency card**
(`homestead_health/emergency.py`) — is the one artifact whose purpose is to
leave: an **authored, never computed** field set (no `auto_include`, no
relevance heuristic) exported like any other record — usefulness does not lower
the rung, the ledger holds the act not the content — with only the operator's
chosen fields, a recorded gap for a chosen-but-empty one, and an `L5` field
dropped without a trace. Its subject-id guard is shared with the school form
(`_egress.py`), so the audit's egress fix protects both by construction.
Every H-* claim is now promoted to its own test file and
`tests/test_invariants_pending.py`'s `UNBUILT` is empty — the guard stays, ready
for the next claim the day its module is named. The
seat's own guarantees (the pin is true and capped, nothing imports the
network, nothing listens, no second path resolver, no shadowed test basename)
are live tests in `tests/test_invariants_seat.py`.

The records track was then **adversarially audited** (`verified_by ≠ author`)
and remediated across two rounds — `docs/audits/bites-2-5-audit.md` and
`docs/audits/h3-h5-audit.md` record the findings and the fixes (a subject-id
egress leak, a k≥2 dedup leak, a clock scan defeated by indirection, a
no-subject denylist replaced by a structural allowlist, a package-wide `.payload`
chokepoint scan replacing a weak per-module one, and more).

The extension's **living lane** (bite 7, `homestead_health/living.py`, H-8) is
now built too: a *forgetting cell* — overwrite-in-place, only-latest, keyed by
the **thing** never the subject — whose audit reuses `keep`'s `IntegrityLog` (a
`living_replaced` line carrying the thing's ref and the SHA-256 of the value it
replaced, anchor off-tree, `verify(expected_head)` catches a hand-edit). It is
`L5` with **no egress**, and grepping its store and ledger for any subject id
comes back empty. Whether `keep`'s `IntegrityLog` *suffices* for it was the check
the plan gated on reading Nestor's ledger — it does, and
`docs/DECISION-living-lane-ledger.md` records the read and the finding (supersede
is a kind-tagged append; no encryption needed since only hashes of priors are
kept). The audit read (`replacements()`) goes through the engine's own reader
(`homestead_health/ledger_seam.py`), never a raw parse of the log file, so once
the operator has run `homestead integrity seal` on `living.jsonl` it needs the
integrity key and the engine's `sealed` extra to be read at all, and it refuses
by name rather than answering "never replaced" without them — and a log shorter
than its anchor refuses too.

The extension's **reference lane** (bite 6, `homestead_health/reference_lane.py`,
H-7) completes the three postures: a pinned, versioned public-domain corpus of
health-literacy and conversation-prep reference (holds **no subject**, structural
allowlist, names its own version and date like H-5's schedule) behind an
**injected reader** — `Reader(corpus)` defaults to the pin, so a host could hand a
larger one. `ask(question)` returns cited answers by term overlap and takes **no
subject, ever**: the wall against H-2 is structural (there is nowhere to pass a
child's record, and the module imports nothing that carries one), so retrieval of
public reference never becomes advice about a person. A source's attribution — a
CC-BY part included — rides through to every answer that quotes it, and the reader
dials for nothing. Suite: **128 passed / 0 xfailed**.

```bash
pip install -e ".[dev]"
pytest -q          # bare, from a cold checkout. No out-of-band install step.
```

## Entering your own information

Records go into the household root — `$HOMESTEAD_HOME`, else `~/.homestead` —
and nothing below needs the optional `entity` extra. Members are enrolled
first (the roster mints the opaque id; the name is stored at `L4` for a
minor), and a dose is entered whole, by subject, at the pack's rungs:

```bash
homestead-health ui                                      # enrolment, dose form, intake and records, on localhost
homestead-health roster add "Mara Chen" --minor          # → subj-01
homestead-health roster add "Ivo Chen" --minor           # → subj-02
homestead-health dose add subj-01 MMR 2026-08-15 --next-due 2026-09-20 --provider "Dr. Lee" --lot AB12
homestead-health dose list subj-01     # the list pane: a dose is L4, so "An immunization dose is on file · next due …"
homestead-health dose show subj-01-01  # the detail pane: vaccine, date, provider, lot — rendered
homestead-health today                 # "2 immunizations due this month", only where k ≥ 2 survives
homestead-health export subj-01        # the school form, to exports/, both logs written, head anchor printed
```

A dose is one composed `L4` record (`homestead_health/doses.py`) keyed
`<subject id>-<NN>` — a reference, never a name — with its `next_due` kept
beside it as the `L2` date it is declared to be; the school form and the
Today line read exactly these records. The browser UI (`ui`) has a *Roster*
tab, a *Records* tab (the dose form, the subject's doses through the gate,
the gated Today line) and an *Intake* tab that extracts vaccines, dates,
providers and lot numbers from pasted text and fills the form with one click.
Entity resolution, care decisions and the ledger check need
`pip install 'homestead-health[entity]'` and say so when it is missing.

> `homestead-affairs` is a pinned dependency consumed only through
> `homestead.keep`'s public API. Do not modify it, propose changes to it, or
> generalize app logic into it. Upstream changes are issues on
> [`rudi193-cmd/homestead`](https://github.com/rudi193-cmd/homestead).

**Synthetic data only.** No real household's health records enter this app
before the export/log story (bite 5) is built and audited — the engine's own
rule, and this module handles exactly the material the rung model calls `L4`.

Apache-2.0, matching the engine.
