"""Enrolling members and recording doses needs only the engine — never the
`entity` extra. This file poisons the `nestor` import so the *absent* branch runs
on every checkout: the seam degrades to nothing bound, every record command works
end to end, and every Nestor-backed command refuses in one line naming the extra.
"""
from __future__ import annotations

import sys

import pytest

from homestead_health import nestor_seam
from homestead_health.cli import run_cli


@pytest.fixture(autouse=True)
def _no_nestor(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    monkeypatch.setitem(sys.modules, "nestor", None)
    monkeypatch.setattr(nestor_seam, "_bound", False)
    monkeypatch.setattr(nestor_seam, "_ledger_path", None)
    yield


def test_available_is_false_and_bind_degrades(tmp_path):
    assert nestor_seam.available() is False
    assert nestor_seam.bind(tmp_path) is None
    with pytest.raises(nestor_seam.SeamNotBoundError):
        nestor_seam.resolver_for("provider", object())


def test_roster_add_and_list(capsys):
    assert run_cli(["roster", "add", "Mara", "Chen", "--minor"]) == 0
    assert "enrolled: subj-01  (minor)" in capsys.readouterr().out
    assert run_cli(["roster", "add", "Rudi"]) == 0
    capsys.readouterr()
    assert run_cli(["roster", "list"]) == 0
    out = capsys.readouterr().out
    assert "subj-01" in out and "subj-02" in out


def test_dose_add_list_show_today_export_round_trip(capsys):
    run_cli(["roster", "add", "Mara", "--minor"])
    run_cli(["roster", "add", "Ivo", "--minor"])
    capsys.readouterr()

    assert run_cli(["dose", "add", "subj-01", "MMR", "2026-08-15", "--next-due", "2026-09-20",
                    "--provider", "Dr. Lee", "--lot", "AB12", "--source", "clinic card"]) == 0
    out = capsys.readouterr().out
    assert "recorded: subj-01-01" in out and "proposed" not in out
    assert run_cli(["dose", "add", "subj-02", "DTaP", "2026-08-01", "--next-due", "2026-09-05"]) == 0
    capsys.readouterr()

    assert run_cli(["dose", "list", "subj-01"]) == 0
    out = capsys.readouterr().out
    assert "[L4]  subj-01-01: An immunization dose is on file  ·  next due 2026-09-20" in out
    assert "MMR" not in out and "2026-08-15" not in out          # L4 on a list: derived only

    assert run_cli(["dose", "show", "subj-01-01"]) == 0
    out = capsys.readouterr().out
    assert "vaccine: MMR" in out and "dose date: 2026-08-15" in out and "lot number: AB12" in out

    assert run_cli(["today", "--today", "2026-09-11"]) == 0
    assert "2 immunizations due this month" in capsys.readouterr().out

    assert run_cli(["export", "subj-01"]) == 0
    out = capsys.readouterr().out
    assert "exported:" in out and "head:" in out


def test_dose_refusals_are_one_line_each(capsys):
    run_cli(["roster", "add", "Mara", "--minor"])
    capsys.readouterr()
    assert run_cli(["dose", "add", "subj-07", "MMR", "2026-08-15"]) == 1
    assert "not on the roster" in capsys.readouterr().err
    assert run_cli(["dose", "add", "subj-01", "MMR", "next week"]) == 1
    err = capsys.readouterr().err
    assert "refused" in err and "Traceback" not in err
    assert run_cli(["dose", "list", "subj-01"]) == 0
    assert "no doses on file" in capsys.readouterr().out
    assert run_cli(["dose", "show", "subj-01-01"]) == 1
    assert run_cli(["dose", "show", "MMR"]) == 1
    assert run_cli(["dose"]) == 1
    assert run_cli(["dose", "bogus"]) == 1


def test_today_over_an_empty_household_draws_nothing(capsys):
    assert run_cli(["today"]) == 0
    assert "(nothing to show)" in capsys.readouterr().out


def test_export_of_nothing_is_refused(capsys):
    run_cli(["roster", "add", "Mara", "--minor"])
    capsys.readouterr()
    assert run_cli(["export", "subj-01"]) == 1
    assert "refused" in capsys.readouterr().err


def test_put_is_retired_and_points_at_dose_add(capsys):
    assert run_cli(["put", "vaccine", "MMR"]) == 1
    assert "dose add" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [
    ["resolve", "provider", "Dr. Lee"],
    ["decisions", "list"],
    ["verify"],
])
def test_nestor_backed_commands_refuse_in_one_line_naming_the_extra(argv, capsys):
    assert run_cli(argv) == 1
    captured = capsys.readouterr()
    assert "homestead-health[entity]" in captured.err
    assert "Traceback" not in captured.err


# ── the W0 audit's additions ────────────────────────────────────────────────


def test_typing_a_name_where_the_subject_id_goes_is_one_line_not_a_traceback(capsys):
    """The likeliest mistake at this prompt, and the worst failure for it.

    `_egress.validate_subject` raises `ExportRefused` — a `PermissionError`, not
    a `ValueError` — so `dose add "Mara Chen" MMR 2026-08-15` came back as a
    fourteen-frame traceback whose last line echoed the name that was typed.
    A refusal is a sentence, and it says where the id comes from.
    """
    run_cli(["roster", "add", "Mara", "Chen", "--minor"])
    capsys.readouterr()
    assert run_cli(["dose", "add", "Mara Chen", "MMR", "2026-08-15"]) == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "refused" in err and "roster list" in err


def test_a_raced_dose_id_is_a_sentence_not_a_traceback(capsys, monkeypatch):
    """Two processes adding a dose for the same subject race on the counter; the
    store refuses the loser with `FileExistsError` (I-9), which is an `OSError`
    and so slipped past the `ValueError` catch. The operator is told nothing was
    stored and to run it again — never a stack."""
    from homestead_health import doses

    run_cli(["roster", "add", "Mara", "--minor"])
    run_cli(["dose", "add", "subj-01", "MMR", "2026-08-15"])
    capsys.readouterr()

    monkeypatch.setattr(doses, "_next_number", lambda store, sid: 1)
    assert run_cli(["dose", "add", "subj-01", "DTaP", "2026-08-16"]) == 1
    err = capsys.readouterr().err
    assert "Traceback" not in err
    assert "Nothing was stored" in err and "again" in err


def test_a_forgotten_flag_is_refused_rather_than_silently_dropped(capsys):
    """`dose add subj-01 MMR 2026-08-15 2026-09-20` — `--next-due` forgotten —
    used to record the dose with **no next-due date at all** and report success.
    A dropped fact reported as a success is the shape H-4 refuses; the extra
    positional is now the usage message."""
    run_cli(["roster", "add", "Mara", "--minor"])
    capsys.readouterr()
    assert run_cli(["dose", "add", "subj-01", "MMR", "2026-08-15", "2026-09-20"]) == 1
    assert "named flag" in capsys.readouterr().err
    assert run_cli(["dose", "list", "subj-01"]) == 0
    assert "no doses on file" in capsys.readouterr().out


def test_today_refuses_a_date_it_cannot_read(capsys):
    """`--today garbage` reached the engine's strict parser and came back out of
    the CLI as a traceback. The engine does not guess at a date (BUG-1) and
    neither does the surface that asked it."""
    assert run_cli(["today", "--today", "garbage"]) == 1
    err = capsys.readouterr().err
    assert "refused" in err and "Traceback" not in err


def test_a_dose_list_never_carries_the_vaccine_even_for_a_planted_record(capsys, tmp_path):
    """The CLI list pane, against the record the gate *would* render.

    A dose-shaped record left at L2 by a hand-edit renders on a list surface,
    and the pane printed `Served.value` whatever it was — the whole payload
    beside the subject id. Planted directly in the store, which is the only way
    such a record can exist.
    """
    from homestead.keep.record import Sidecar
    from homestead.keep.rungs import Classified, Rung

    from homestead_health import doses

    run_cli(["roster", "add", "Mara", "--minor"])
    capsys.readouterr()
    Sidecar().put(doses.MATTER, doses.DOSE_ITEM, "subj-01-01",
                  Classified(Rung.L2, {"subject": "subj-01", "vaccine": "MMR",
                                       "dose_date": "2026-08-15"}))

    assert run_cli(["dose", "list", "subj-01"]) == 0
    out = capsys.readouterr().out
    assert "An immunization dose is on file" in out
    assert "MMR" not in out and "2026-08-15" not in out
