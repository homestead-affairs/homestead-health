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
