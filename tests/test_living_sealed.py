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
    IntegrityKeyError,
    IntegrityLog,
    IntegritySealError,
    init_key,
)

from homestead_health.living import LIVING_KIND, LivingLane, LivingLaneRefused

PRIOR = "PRIOR_SEALED_the-thing-that-must-be-forgotten"
LATEST = "LATEST_SEALED_the-only-thing-that-remains"


def test_the_engine_exports_the_sealing_symbols_this_fix_imports():
    """Proves the 0.11.0 floor by import, not only by the pyproject.toml pin —
    same convention H2-cap used for `Event.RECORD_ADDED`."""
    assert issubclass(IntegritySealError, Exception)
    assert SEAL_BOUNDARY_ACT == "sealed"


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
    sealed — answers byte-identical through the new reader."""
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
    ]
    log_path.write_text(
        "\n".join(json.dumps(line, sort_keys=True) for line in lines) + "\n",
        encoding="utf-8",
    )

    lane = LivingLane()
    assert lane.replacements("sleep") == [lines[0], lines[2]]
    assert lane.replacements("growth") == [lines[3]]
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
