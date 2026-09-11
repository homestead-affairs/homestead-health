# W0 audit — record entry (the dose, the CLI, the browser door), attacked and remediated

**Audited 2026-09-11**, on branch `claude/user-editable-information-gax5u7`, by an
independent adversarial pass (`verified_by ≠ author`). Scope: the commit that
made the module writable — `homestead_health/doses.py` (new), the `dose`/`today`/
`export` CLI commands, `build_server()` and the dose form, and the `--smoke`
and README claims that go out with them. Brief: find *enforcement theatre* and
the failure modes the three earlier audits taught this repo to look for —
a refusal that is really a traceback, a validator that two callers disagree
about, a scan whose claim is broader than what it measures.

**Verdict as delivered:** the shape held. A dose is one composed `L4` record,
found by key prefix with no payload reached; the pack's rungs decide, not the
surfaces; the visible log carries `subj-NN-NN` and nothing else; `today_line`
gates through the engine's `cover_counts` with the roster deduplicated; the
package-wide chokepoint scan covers `doses.py`; the network scan still exempts
`server.py` alone. What the pass found was a **cluster of refusals that were
not refusals** — four exception types the surfaces did not catch, a body reader
with no answer for a malformed request, and two claims stated wider than they
were measured. All remediated on the branch; suite **212 → 248** (252 with the
`entity` extra).

## Severe

### W0-1 · Four refusal types came back as tracebacks, on both surfaces — **fixed**

`doses.add_dose` refuses in four types and only two of them are `ValueError`.
`_egress.validate_subject` raises `ExportRefused` (a `PermissionError`) and the
store's I-9 clobber refusal is `FileExistsError` (an `OSError`). Both surfaces
caught `(ValueError, UnparseableDate)`.

So the *likeliest operator mistake at this prompt* — typing the person's name
where the opaque subject id goes — produced a fourteen-frame traceback whose
last line echoed the name, and a second process adding a dose for the same
subject produced another. On the server both landed in a catch-all that
answered `500` (a server fault for an input the operator can fix) with
`str(exc)` for **any** exception, which is a leak waiting on the first
exception type to carry a field value.

**Remediation:** `add_dose`'s docstring now names all four types (a surface that
catches three turns the fourth into a stack); the CLI answers each in one line
(`ExportRefused` also says where an id comes from, `FileExistsError` says
nothing was stored and to run it again); the server answers `400`, `409`, and a
**fixed** last-resort sentence that echoes nothing. `today --today garbage`,
which reached `parse_deadline` and came back out as a traceback, is a refusal
too. Tests plant each, and assert `"Traceback" not in err`.

### W0-2 · The browser door dropped the connection on four malformed requests — **fixed**

`_body()` was `json.loads(self.rfile.read(int(Content-Length)))`. A bad
`Content-Length` (`int("abc")`), a malformed body (`JSONDecodeError`), and a
body that is JSON but not an object (`.get` on a list) each raised out of
`do_POST`: no status, connection reset, traceback on the operator's terminal.
There was **no size cap at all** — a three-megabyte body was read into memory
and accepted.

**Remediation:** a `_BadBody` signal with a status and a **fixed** sentence
(400 for each malformed shape, 413 past 1 MiB, checked on the header so nothing
oversized is buffered, with the declared bytes drained in bounded chunks so the
client gets its answer). The sentence never echoes the body: a refusal says what
was wrong with the envelope, never what was in it.

### W0-3 · `_post_roster` crashed on a non-string name, and read minority by truthiness — **fixed**

`body.get("name", "").strip()` raised `AttributeError` on `{"name": 5}` —
another dropped connection. And `minor=bool(minor)` read the JSON string
`"false"` as a **minor**. That direction over-protects (the safe one), but the
tempting tightening the other way — `minor is True` — would read `"true"` as an
*adult*, which is the fail-open direction `Roster.is_minor` calls catastrophic.
Minority is not a truthiness question: it **is** the name's rung.

**Remediation:** `name` must be text and `minor` must be a JSON boolean;
anything else is `400`. Refusing is the only reading that is wrong in neither
direction.

## Moderate

### W0-4 · The list pane printed `Served.value`, whatever the gate said — **fixed**

A dose composes to `L4` (the vaccine), so `S1_LIST` derives it by construction
and the pane showed the one sentence. But a *record* is a file: a hand-edit or a
future writer that skips `add_dose` can leave a dose-shaped record at `L2`,
which **renders** on a list surface — and both panes printed
`str(served.value)`, putting the vaccine, the dose date and the operator's notes
on an ambient row beside the subject id. That is precisely what the pack's
`dose_date` declaration promises cannot happen ("the declaration is per-field,
the protection is per-record").

**Remediation:** `doses.list_row()` and `doses.next_due_text()` — one place the
list-surface rule lives, shared by the CLI and the browser, the `_egress` lesson
about not keeping two validators for one rule. A row carries `DERIVED` and
nothing else; a `DENY` is dropped with no count behind it. The violation is
planted as the record itself (the only way in) on both surfaces. `compose()`
over the *given* fields is asserted across the whole power set of the optional
fields, so no subset stores a sub-`L4` dose.

### W0-5 · `--smoke` claimed the package and measured a quarter of it — **fixed**

`--smoke` says it *"proves every import survived packaging"* and imported four of
fifteen modules. A wheel missing `server`, `cli`, `doses`, `intake`,
`school_form`, `due`, `emergency`, `living`, `reference_lane`, `nestor_store` or
`_egress` printed `smoke ok` and shipped.

**Remediation:** every module, by name — and `tests/test_invariants_smoke.py`
scans that branch against the package's own file list, so a module added without
a line there fails by name. The scan is fired against a planted omission (one
import deleted from a copy of the source), and a subprocess leg runs the real
thing, because an AST scan proves the names are listed and only an interpreter
proves they import.

### W0-6 · A forgotten flag silently dropped a fact — **fixed**

`dose add` took `len(rest) < 3` and ignored the rest, so
`dose add subj-01 MMR 2026-08-15 2026-09-20` — `--next-due` forgotten — recorded
the dose with **no next-due date at all** and reported success. A dropped fact
reported as a success is the shape H-4 refuses. Now exactly three positionals,
with the usage and a line naming the mistake.

### W0-7 · `homestead-health` was a command that did not exist — **fixed**

`pyproject.toml` declared no `[project.scripts]`, while `--help` has printed
`homestead-health <command>` since the seat landed and every line of the
README's new entry recipe begins with it. A household that ran
`pip install homestead-health` got a package whose own usage named a command it
did not create. Declared, with a test that reads it from the file (so it holds
on a cold checkout) and resolves the target to a callable.

## Attacked and found sound — recorded so the next pass does not redo them

* **A per-subject `dose list` showing the `L2` next-due date beside the subject
  id.** Not an ambient-surface violation. The operator has already named the
  subject — `PLAN-homestead-health.md`'s own worked example puts strictly *more*
  there ("opening the queue … shows *MMR · due Sep 1* against the subject"), and
  `next_due` is declared `L2`, "a date, naming nobody by itself", which renders
  on a list surface by the gate's own table. The dose itself is still served
  derived, so the pane is more conservative than the plan allows. **Residual,
  not a defect:** storing `next_due` as its own record does give up I-12's
  per-record protection that `dose_date` keeps — a future surface that iterates
  `next_due` records *without* an operator naming a subject would show dates
  beside subject ids ambiently. No such path exists (`today_line` emits only the
  gated count; `/api/doses` requires a subject on the roster), and
  `doses.next_due_text` is the one reader.
* **H-2.** `due.DERIVED` is a closed vocabulary parameterised by a count;
  `doses.DERIVED` is parameterised by nothing — no format slot, no percent, no
  digit — and `list_row` returns the constant itself for every dose there can
  be. There is no template a recommendation could be phrased in and no slot to
  write one into. Asserted both ways.
* **I-31.** `due.today_line` deduplicates the roster before `cover_counts`, and
  `/api/today?today=<unparseable>` is a `400`, `?today=` (blank) is today.
* **XSS.** `esc()` is a `textContent` round-trip: it escapes `&<>` but not the
  apostrophe that would close `onclick="openDose('…')"`. What holds that seam is
  that a dose id is never free text — `doses.doses_of` returns only keys matching
  `subj-NN-NN`. Asserted at the surface, so a future loosening of the key scan
  fails here.
* **The chokepoint and the seat scans.** The package-wide chokepoint scan
  (`rglob`) covers `doses.py` and `server.py`; the network scan's `BOUNDARY`
  still exempts `server.py` alone. Both verified by listing what they walk.
* **I-15.** After a full end-to-end run the visible log holds `subj-01`,
  `subj-02`, `subj-01-01`, `subj-02-01` and an export reference; grepping it and
  the anchors for every name, vaccine, provider, lot and date comes back empty.

## Out of scope, noted

* `doses.py` logs `Event.RECORD_SYNCED` for a dose add because the pinned engine
  has no `RECORD_ADDED` and `Event` is closed. Left, with a comment naming the
  plan bite (**H2-cap**) that raises the floor and switches the line. The roster
  carries the same debt on the same event.
* Importing `homestead_health.due` (and so `doses`) pulls `socket`/`urllib` into
  the process transitively, through the engine's `homestead.app.cover`. The
  module's own source is clean — the AST scan is the invariant and it passes —
  and the fix, if it is one, is the engine's.
* `today_line`'s anonymity set is the whole roster, so two doses due for one
  child in a two-child household render a count. That is the plan's own worked
  example ("a two-child household's Today renders *2 immunizations due this
  month*"), and changing it would be a `due.py` decision, not a W0 one.
