"""H6-sealed-reader — a sealed `living.jsonl` refuses, never answers `[]`
(see `homestead_health/ledger_seam.py` for the finding). Four legs: (a)
sealed+keyed+`cryptography` — a real decrypted round trip; (b) sealed,
`cryptography` unavailable — refuses by name, hand-built so it runs on
both legs of this bite's own matrix without `importorskip`; (c) sealed,
key file removed — refuses by name; (d) unsealed and keyed-only —
byte-identical to before the fix.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from homestead.keep import paths
from homestead.keep.logs import (
    BOUNDARY_ACT,
    SEAL_BOUNDARY_ACT,
    IntegrityIncompleteError,
    IntegrityKeyError,
    IntegrityLog,
    IntegritySealError,
    init_key,
)
from homestead.keep.sealed import SealTamperError

from homestead_health.ledger_seam import LedgerUnreadable, _ledger_entries
from homestead_health.living import LIVING_KIND, LivingLane, LivingLaneRefused

PRIOR = "PRIOR_SEALED_the-thing-that-must-be-forgotten"
LATEST = "LATEST_SEALED_the-only-thing-that-remains"

# The 0.11.0 floor is proven by import *and* by the pin in
# `tests/test_invariants_release.py::test_the_engine_floor_is_the_release_that_
# ships_sealed_integrity` — the same file that does it for `Event.RECORD_ADDED`.
# Not repeated here: one claim, one test.


# ── (a) sealed, keyed, cryptography present: a real round trip ──────────────


def test_replacements_decrypts_a_really_sealed_log(tmp_path, monkeypatch):
    pytest.importorskip("cryptography")
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    init_key()
    log = IntegrityLog(
        paths.logs_dir() / "living.jsonl", anchor_path=paths.anchors_dir() / "living.head"
    )
    log.seal()
    writer = LivingLane(ledger=log)
    writer.remember("sleep", PRIOR)     # first write, nothing forgotten yet
    writer.remember("sleep", LATEST)    # replaces PRIOR — one forgetting, sealed

    reader = LivingLane()  # a fresh IntegrityLog instance, auto-detecting sealed
    entries = reader.replacements("sleep")

    assert len(entries) == 1, "the sealed replacement must be found, not lost"
    entry = entries[0]
    assert entry["kind"] == LIVING_KIND
    assert entry["thing"] == "sleep"
    assert entry["prior_sha256"] == hashlib.sha256(PRIOR.encode()).hexdigest()
    assert PRIOR not in json.dumps(entry), "the prior value itself never rides along"

    raw = (paths.logs_dir() / "living.jsonl").read_text(encoding="utf-8")
    assert '"sealed": 1' in raw or '"sealed":1' in raw, "this must exercise the sealed path"


# ── (b) sealed, cryptography unavailable: refuse by name ────────────────────


def test_replacements_refuses_when_cryptography_is_unavailable(tmp_path, monkeypatch):
    """Simulated absence of the `sealed` extra, by monkeypatching the engine's
    availability check — runs whether or not this environment has the extra
    installed. The sealed line is hand-built, never real ciphertext: what is
    under test is that `replacements()` refuses the moment it would need to
    decrypt, rather than treating an unreadable line as `[]`."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    from homestead.keep import sealed as sealed_mod

    init_key()  # the key is present; only the extra is (simulated) missing
    log_path = paths.logs_dir() / "living.jsonl"
    paths.ensure(log_path.parent)
    log_path.write_text(
        json.dumps({
            "sealed": 1, "nonce": "00" * 12, "ct": "00" * 32,
            "prev": "genesis", "hash": "deadbeef",
        }) + "\n",
        encoding="utf-8",
    )

    def _unavailable(*_a, **_kw):
        raise IntegritySealError(
            "this log is sealed; install homestead-affairs[sealed] to read "
            'or write it (pip install "homestead-affairs[sealed]")'
        )

    # Patch both names: whichever the installed engine's `unseal_line` reaches
    # for internally, this simulates the extra being absent without it truly
    # being absent.
    monkeypatch.setattr(sealed_mod, "require_available", _unavailable)
    monkeypatch.setattr(sealed_mod, "_require_cryptography", _unavailable)

    lane = LivingLane()
    with pytest.raises(LivingLaneRefused) as excinfo:
        lane.replacements("thing")

    assert "sealed" in str(excinfo.value), "the refusal must name the sealed extra"
    assert isinstance(excinfo.value.__cause__, IntegritySealError)


# ── (c) sealed, the key file removed: refuse by name ─────────────────────────


def test_replacements_refuses_when_the_key_is_gone(tmp_path, monkeypatch):
    """The sealed boundary row survives on disk (plaintext, keyed-HMAC, never
    encrypted itself), so a fresh reader still detects the log as sealed —
    and, with no key to decrypt it, refuses rather than reporting `[]`."""
    pytest.importorskip("cryptography")
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    key_path = init_key()
    log = IntegrityLog(
        paths.logs_dir() / "living.jsonl", anchor_path=paths.anchors_dir() / "living.head"
    )
    log.seal()
    writer = LivingLane(ledger=log)
    writer.remember("sleep", PRIOR)
    writer.remember("sleep", LATEST)

    key_path.unlink()  # the key is gone; the sealed log and its boundary row remain

    reader = LivingLane()  # a fresh IntegrityLog, auto-detecting from scratch
    with pytest.raises(LivingLaneRefused) as excinfo:
        reader.replacements("sleep")

    assert "key" in str(excinfo.value).lower()
    assert isinstance(excinfo.value.__cause__, (IntegritySealError, IntegrityKeyError))


# ── (d) unsealed and keyed-only: unchanged from before the fix ──────────────


def test_unsealed_log_answers_exactly_as_before(tmp_path, monkeypatch):
    """A fixture on the pre-fix shape — plain JSON lines, never keyed, never
    sealed — answers byte-identical through the new reader.

    Written as a literal here, deliberately, and not generated by the code
    under test: a fixture produced by the new reader could only ever prove
    that it agrees with itself.

    Byte-identical is a claim about JSON escaping too, not only about which
    lines survive, so one row carries a non-ASCII `thing` and one a value
    with a literal newline — where a reader that re-encoded or
    `ensure_ascii`-mangled anything would diverge from the raw `json.loads`
    this replaced. (`seen_at` is not a field the lane writes; it is here only
    because a newline cannot live in a `thing`, which `_validate_thing`
    refuses.)"""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    log_path = paths.logs_dir() / "living.jsonl"
    paths.ensure(log_path.parent)

    lines = [
        {"kind": LIVING_KIND, "thing": "sleep", "prior_sha256": "a" * 64,
         "at": "2026-01-01T00:00:00+00:00", "prev": "genesis"},
        {"kind": "not_a_living_line", "thing": "sleep",
         "at": "2026-01-02T00:00:00+00:00", "prev": "x"},
        {"kind": LIVING_KIND, "thing": "sleep", "prior_sha256": "b" * 64,
         "at": "2026-01-03T00:00:00+00:00", "prev": "y"},
        {"kind": LIVING_KIND, "thing": "growth", "prior_sha256": "c" * 64,
         "at": "2026-01-04T00:00:00+00:00", "prev": "z"},
        {"kind": LIVING_KIND, "thing": "wachstum-größe", "prior_sha256": "d" * 64,
         "at": "2026-01-05T00:00:00+00:00", "prev": "w",
         "seen_at": "line one\nline two\ttabbed"},
    ]
    log_path.write_text(
        "\n".join(json.dumps(line, sort_keys=True) for line in lines) + "\n",
        encoding="utf-8",
    )

    lane = LivingLane()
    assert lane.replacements("sleep") == [lines[0], lines[2]]
    assert lane.replacements("growth") == [lines[3]]
    assert lane.replacements("wachstum-größe") == [lines[4]]
    assert lane.replacements("nothing-ever-happened-here") == []


def test_keyed_only_log_answers_exactly_as_before(tmp_path, monkeypatch):
    """Same pin for a log that has run `init-key` but never `seal` (E5's
    posture): a `{"act": "keyed"}` boundary row is on disk and must be
    skipped, exactly as the pre-fix `kind` filter already dropped it."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    init_key()
    log = IntegrityLog(
        paths.logs_dir() / "living.jsonl", anchor_path=paths.anchors_dir() / "living.head"
    )
    lane = LivingLane(ledger=log)

    lane.remember("sleep", PRIOR)    # first write — nothing forgotten yet
    lane.remember("sleep", LATEST)   # replaces PRIOR — one forgetting, keyed

    entries = lane.replacements("sleep")
    assert len(entries) == 1
    assert entries[0]["kind"] == LIVING_KIND
    assert entries[0]["thing"] == "sleep"
    assert entries[0]["prior_sha256"] == hashlib.sha256(PRIOR.encode()).hexdigest()

    raw_lines = (paths.logs_dir() / "living.jsonl").read_text(encoding="utf-8").splitlines()
    assert any(json.loads(line).get("act") == BOUNDARY_ACT for line in raw_lines), (
        "this must exercise the boundary-skip, not an empty log"
    )


# ── (e) every other unreadable shape refuses by name ────────────────────────


def _write_lines(rows) -> None:
    log_path = paths.logs_dir() / "living.jsonl"
    paths.ensure(log_path.parent)
    log_path.write_text(
        "\n".join(r if isinstance(r, str) else json.dumps(r, sort_keys=True)
                  for r in rows) + "\n",
        encoding="utf-8",
    )


def test_a_garbage_line_refuses_rather_than_answering_never_replaced(tmp_path, monkeypatch):
    """A hand-edited or half-written plaintext line. The bare `json.loads`
    in the engine's `_lines()` came straight out of `replacements()` as a
    `json.JSONDecodeError` — a stdlib traceback from a frame the caller never
    called, which is no more a refusal by name than `[]` was."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    _write_lines([
        {"kind": LIVING_KIND, "thing": "sleep", "prior_sha256": "a" * 64},
        "{not json at all",
    ])

    with pytest.raises(LivingLaneRefused) as excinfo:
        LivingLane().replacements("sleep")

    assert isinstance(excinfo.value.__cause__, LedgerUnreadable)
    assert isinstance(excinfo.value.__cause__.__cause__, json.JSONDecodeError)


def test_a_truncated_sealed_line_refuses_rather_than_answering_never_replaced(
    tmp_path, monkeypatch
):
    """A sealed line whose ciphertext was truncated: the GCM tag no longer
    authenticates and the engine says so with `SealTamperError`, which is
    neither `IntegritySealError` nor `IntegrityKeyError` and so sailed
    straight past `replacements()`'s except clause. Tamper is "cannot tell",
    not "nothing happened"."""
    pytest.importorskip("cryptography")
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))

    init_key()
    log = IntegrityLog(
        paths.logs_dir() / "living.jsonl", anchor_path=paths.anchors_dir() / "living.head"
    )
    log.seal()
    writer = LivingLane(ledger=log)
    writer.remember("sleep", PRIOR)
    writer.remember("sleep", LATEST)

    log_path = paths.logs_dir() / "living.jsonl"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    tail = json.loads(lines[-1])
    assert tail.get("sealed") == 1, "the plant must land on a genuinely sealed line"
    tail["ct"] = tail["ct"][:-8]           # truncate the ciphertext
    lines[-1] = json.dumps(tail)
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    with pytest.raises(LivingLaneRefused) as excinfo:
        LivingLane().replacements("sleep")

    assert isinstance(excinfo.value.__cause__, LedgerUnreadable)
    assert isinstance(excinfo.value.__cause__.__cause__, SealTamperError), (
        "every failure the seam maps keeps the engine's own exception as "
        "__cause__ — the message alone is not the pin"
    )
    assert "authenticate" in str(excinfo.value)


def test_an_engine_that_drops_the_public_reader_refuses_by_name(tmp_path, monkeypatch):
    """`read_entries` is a public method (H7-floor-0.12), but still one a
    future `homestead-affairs` inside the `<1.0` cap could rename or drop
    with nothing in this repo changing. The seam must then refuse by name,
    naming the one file to repoint, and never degrade into `[]`.
    `tests/test_ledger_seam.py` pins the other half: that today's installed
    engine still has it."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    _write_lines([{"kind": LIVING_KIND, "thing": "sleep", "prior_sha256": "a" * 64}])

    lane = LivingLane()
    assert lane.replacements("sleep"), "the fixture must answer before the reader goes"
    # Absent is not corrupt, and that is why this is a named class rather than
    # "any failure": a thing never replaced still answers `[]`, here and — on a
    # household with no log at all — in tests/test_invariants_living.py.
    assert lane.replacements("nothing-ever-happened-here") == []

    monkeypatch.delattr(IntegrityLog, "read_entries")
    with pytest.raises(LivingLaneRefused) as excinfo:
        lane.replacements("sleep")

    assert isinstance(excinfo.value.__cause__, LedgerUnreadable)
    assert "read_entries" in str(excinfo.value) and "ledger_seam" in str(excinfo.value)


# ── (g) a log shorter than its anchor refuses too (H7-floor-0.12) ───────────


def test_a_chopped_log_refuses_rather_than_answering_never_replaced(tmp_path, monkeypatch):
    """Three entries written, the file truncated to two lines with the
    anchor left pointing at the third: every surviving line still chains
    perfectly, so only the anchor comparison catches it.
    `IntegrityLog.read_entries()` raises `IntegrityIncompleteError` rather
    than a complete-looking short list — `H6-sealed-reader`'s bug shape, one
    step earlier, closed by the E7 audit."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    log_path = paths.logs_dir() / "living.jsonl"
    log = IntegrityLog(log_path, anchor_path=paths.anchors_dir() / "living.head")
    for i in range(3):
        log.append({"kind": LIVING_KIND, "thing": "sleep", "prior_sha256": f"{i}" * 64})

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 3, "the plant must land on three real, chained lines"
    log_path.write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")  # anchor still names line 3

    with pytest.raises(LivingLaneRefused) as excinfo:
        LivingLane().replacements("sleep")

    assert isinstance(excinfo.value.__cause__, LedgerUnreadable)
    assert isinstance(excinfo.value.__cause__.__cause__, IntegrityIncompleteError)
    assert "sleep" not in str(excinfo.value), "a thing key is not content, but never echo one anyway"


def test_a_deleted_log_with_a_surviving_anchor_refuses_rather_than_answering_never_replaced(
    tmp_path, monkeypatch
):
    """The anchor is a separate file (`paths.anchors_dir()/living.head`):
    deleting `living.jsonl` outright while it survives is the same
    "shorter than the anchor says" finding as truncation, at the extreme —
    zero surviving lines against an anchor that names one."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    log_path = paths.logs_dir() / "living.jsonl"
    log = IntegrityLog(log_path, anchor_path=paths.anchors_dir() / "living.head")
    log.append({"kind": LIVING_KIND, "thing": "sleep", "prior_sha256": "a" * 64})

    assert log_path.exists()
    assert (paths.anchors_dir() / "living.head").exists()
    log_path.unlink()  # the anchor survives; the log itself is gone

    with pytest.raises(LivingLaneRefused) as excinfo:
        LivingLane().replacements("sleep")

    assert isinstance(excinfo.value.__cause__, LedgerUnreadable)
    assert isinstance(excinfo.value.__cause__.__cause__, IntegrityIncompleteError)


def test_a_log_never_written_still_answers_empty_absent_is_not_corrupt(tmp_path, monkeypatch):
    """The distinction this whole class exists to pin: a log that was never
    written has no anchor to be short of, and that is the true `[]` —
    unlike the chopped and deleted cases above, both of which leave an
    anchor behind with nothing (or too little) to back it."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    assert not (paths.logs_dir() / "living.jsonl").exists()
    assert not (paths.anchors_dir() / "living.head").exists()

    assert LivingLane().replacements("sleep") == []


def test_a_chopped_log_never_returns_its_intact_prefix_as_an_answer(tmp_path, monkeypatch):
    """The refusal above, one layer down and from the side that could still
    leak: with a generator seam the danger is not the raise, it is a caller
    keeping what was yielded before it. The surviving lines of a chopped log
    chain perfectly, so the reader *does* walk them — the anchor is the only
    witness that there were more, and it is only consulted at the end of the
    walk. What must not exist is a `return`: `list()` — which is exactly what
    `LivingLane.replacements()` calls — has to raise, so no prefix ever
    reaches a caller as "the answer"."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    log_path = paths.logs_dir() / "living.jsonl"
    anchor_path = paths.anchors_dir() / "living.head"
    log = IntegrityLog(log_path, anchor_path=anchor_path)
    for i in range(3):
        log.append({"kind": LIVING_KIND, "thing": "sleep", "prior_sha256": f"{i}" * 64})
    lines = log_path.read_text(encoding="utf-8").splitlines()
    log_path.write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")

    walked: list[dict] = []
    with pytest.raises(LedgerUnreadable) as excinfo:
        for entry in _ledger_entries(IntegrityLog(log_path, anchor_path=anchor_path)):
            walked.append(entry)

    assert len(walked) == 2, (
        "the intact prefix is walked — that is the whole reason the anchor "
        "has to be checked at the end rather than the chain relied on"
    )
    assert isinstance(excinfo.value.__cause__, IntegrityIncompleteError)

    with pytest.raises(LedgerUnreadable):
        list(_ledger_entries(IntegrityLog(log_path, anchor_path=anchor_path)))
    with pytest.raises(LivingLaneRefused):
        LivingLane().replacements("sleep")


def test_a_log_whose_anchor_alone_is_deleted_still_answers(tmp_path, monkeypatch):
    """The mirror image of the deleted-log case, recorded here because the
    answer is "it answers" and that deserves to be a decision rather than a
    surprise.

    It is the engine's rule, not this repo's: the anchor is the only witness
    to a log's length, so `IntegrityLog._require_whole` returns quietly when
    there is no anchor at all ("no anchor, no claim" — the same posture
    `verify()` takes for `anchor is None`). Deleting the *log* under a
    surviving anchor is "shorter than the claim" and refuses; deleting the
    *anchor* under a surviving log withdraws the claim, and the lines that
    remain are read for what they are. Nothing is served short of what the
    file holds either way, which is the property this class of test exists
    to protect.

    What closes the remaining gap is not a reader with nothing left to
    compare against: it is the head the operator recorded off the machine
    (`LivingLane.verify(expected_head)`). If a later engine refuses this
    case too, this is the test to change — deliberately, not by surprise."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    log_path = paths.logs_dir() / "living.jsonl"
    anchor_path = paths.anchors_dir() / "living.head"
    log = IntegrityLog(log_path, anchor_path=anchor_path)
    for i in range(2):
        log.append({"kind": LIVING_KIND, "thing": "sleep", "prior_sha256": f"{i}" * 64})

    anchor_path.unlink()
    assert log_path.exists() and not anchor_path.exists()

    assert len(LivingLane().replacements("sleep")) == 2


def test_a_ledger_that_cannot_be_read_from_disk_refuses_by_name(tmp_path, monkeypatch):
    """The last failure the seam maps and the only one with no behavioural
    test of its own: `OSError`. A directory standing where the log file
    should be is the portable way to make the engine's own read fail — a
    read-only bit does nothing to a CI leg running as root, and less than
    nothing on Windows."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    (paths.logs_dir() / "living.jsonl").mkdir(parents=True)

    with pytest.raises(LivingLaneRefused) as excinfo:
        LivingLane().replacements("sleep")

    assert isinstance(excinfo.value.__cause__, LedgerUnreadable)
    assert isinstance(excinfo.value.__cause__.__cause__, OSError)
    assert "disk" in str(excinfo.value)


# ── (f) boundary rows are never content, and never over-filter ──────────────


def test_boundary_rows_are_never_counted_as_replacements(tmp_path, monkeypatch):
    """The engine's reader skips `{"act": "keyed"}` / `{"act": "sealed"}`; a
    row with no `kind` at all must also never be counted. Planted by hand so
    both shapes are present in one file."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    _write_lines([
        {"act": BOUNDARY_ACT, "at": "2026-01-01T00:00:00+00:00", "prev": "genesis"},
        {"act": SEAL_BOUNDARY_ACT, "at": "2026-01-02T00:00:00+00:00", "prev": "a"},
        {"thing": "sleep", "prior_sha256": "c" * 64},          # kind absent entirely
    ])

    assert LivingLane().replacements("sleep") == []
    assert LivingLane().replacements(BOUNDARY_ACT) == []
    assert LivingLane().replacements(SEAL_BOUNDARY_ACT) == []


def test_a_replacement_named_like_a_boundary_act_is_still_found(tmp_path, monkeypatch):
    """The mirror of the test above: the skip is on `act`, not on the word,
    so a real forgetting of a thing the household happens to have called
    `sealed` or `keyed` is still found. Over-filtering by act name would be
    the same silent "never replaced" this bite exists to remove."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    rows = [
        {"kind": LIVING_KIND, "thing": BOUNDARY_ACT, "prior_sha256": "a" * 64},
        {"kind": LIVING_KIND, "thing": SEAL_BOUNDARY_ACT, "prior_sha256": "b" * 64},
    ]
    _write_lines(rows)

    lane = LivingLane()
    assert lane.replacements(BOUNDARY_ACT) == [rows[0]]
    assert lane.replacements(SEAL_BOUNDARY_ACT) == [rows[1]]


def test_a_keyed_but_unsealed_log_needs_the_key_to_be_read_at_all(tmp_path, monkeypatch):
    """`LivingLane` builds its own `IntegrityLog` with auto key/seal
    detection rather than being handed the writer's: write keyed (never
    sealed), read through a *fresh* lane with the key present, delete the
    key, read again.

    Before 0.12.0 the second read still succeeded: `_entries()` walked the
    plaintext content and never checked it against the anchor, so a keyed
    log's key mattered only for `verify()`. `read_entries()` (E7) checks
    every read's completeness against the anchor, and that check is itself
    keyed the moment the anchor is (`IntegrityLog._require_whole`) — so
    losing the key now costs *readability* too, refusing rather than
    quietly answering the plaintext prefix. A narrowing the engine's own
    audit brought, not a line this repo wrote to cause it — pinned here so
    a green suite says so out loud."""
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    key_path = init_key()
    writer = LivingLane(ledger=IntegrityLog(
        paths.logs_dir() / "living.jsonl", anchor_path=paths.anchors_dir() / "living.head"
    ))
    writer.remember("sleep", PRIOR)
    writer.remember("sleep", LATEST)

    assert len(LivingLane().replacements("sleep")) == 1  # readable while the key is present

    key_path.unlink()
    with pytest.raises(LivingLaneRefused) as excinfo:
        LivingLane().replacements("sleep")
    assert isinstance(excinfo.value.__cause__, IntegrityKeyError)
