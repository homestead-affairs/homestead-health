"""Dose records — the household's own immunizations, keyed by subject (H-1, I-12).

A dose is the record the rest of the module consumes and nothing had written:
`school_form.export_history` takes a subject's dose records, `due.today_line`
counts next-due dates. This file holds the shape those consumers rely on:

* one composed record per dose, at the max of its fields' declared rungs — L4,
  so an ambient list shows only *"An immunization dose is on file"* and the
  detail pane renders it;
* the key carries the opaque subject id and a counter, never a name or a vaccine,
  so finding a subject's doses is a key-prefix scan reaching no payload;
* refusals happen before any write — an unenrolled subject, an empty vaccine, a
  date the engine will not read;
* the school form and the Today line consume these records unchanged.
"""
from __future__ import annotations

import json

import pytest

from homestead.keep.dates import UnparseableDate
from homestead.keep.logs import VisibleLog
from homestead.keep.record import Sidecar
from homestead.keep.rungs import Disposition, Rung, Surface, serve

from homestead_health import doses
from homestead_health.roster import Roster


@pytest.fixture
def household(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    roster = Roster(store)
    a = roster.add(name="Mara Chen", minor=True)
    b = roster.add(name="Ivo Chen", minor=True)
    return store, roster, a, b


def test_a_dose_is_one_l4_record_keyed_by_subject_and_counter(household):
    store, roster, a, _ = household
    ref = doses.add_dose(store, roster, subject=a, vaccine="MMR", dose_date="2026-08-15",
                         provider="Dr. Lee", lot_number="AB12")
    assert ref.id == "subj-01-01" and ref.subject == "subj-01"
    record = store.get(doses.MATTER, doses.DOSE_ITEM, ref.id)
    assert record.rung is Rung.L4

    listed = serve(record, Surface.S1_LIST)
    assert listed.disposition is Disposition.DERIVE
    assert listed.value == doses.DERIVED
    assert "MMR" not in str(listed.value) and "2026-08-15" not in str(listed.value)

    detail = serve(record, Surface.S1_DETAIL)
    assert detail.disposition is Disposition.RENDER
    assert detail.value == {"subject": "subj-01", "vaccine": "MMR", "dose_date": "2026-08-15",
                            "provider": "Dr. Lee", "lot_number": "AB12"}


def test_ids_count_per_subject_and_survive_a_restart(household):
    store, roster, a, b = household
    assert doses.add_dose(store, roster, subject=a, vaccine="MMR", dose_date="2026-08-15").id == "subj-01-01"
    assert doses.add_dose(store, roster, subject=a, vaccine="DTaP", dose_date="2026-08-16").id == "subj-01-02"
    assert doses.add_dose(store, roster, subject=b, vaccine="MMR", dose_date="2026-08-15").id == "subj-02-01"

    reopened = Sidecar()
    assert doses.add_dose(reopened, Roster(reopened), subject=a, vaccine="HepB",
                          dose_date="2026-08-17").id == "subj-01-03"
    assert [r.id for r, _ in doses.doses_of(reopened, a)] == ["subj-01-01", "subj-01-02", "subj-01-03"]
    assert [r.id for r, _ in doses.doses_of(reopened, b)] == ["subj-02-01"]


def test_finding_doses_by_subject_is_a_key_scan_not_a_name(household, tmp_path):
    store, roster, a, _ = household
    doses.add_dose(store, roster, subject=a, vaccine="MMR", dose_date="2026-08-15")
    files = [p.name for p in (tmp_path / "sidecar" / doses.MATTER / doses.DOSE_ITEM).iterdir()]
    assert files == ["subj-01-01.json"]
    assert doses.doses_of(store, "subj-99") == []
    assert doses.doses_of(store, "subj-0") == []      # a prefix of a real id is not it


def test_the_log_line_carries_the_dose_id_and_nothing_else(household, tmp_path):
    store, roster, a, _ = household
    doses.add_dose(store, roster, subject=a, vaccine="MMR", dose_date="2026-08-15",
                   provider="Dr. Lee", notes="cried a little")
    lines = VisibleLog().read()
    dose_lines = [l for l in lines if l["ref"] == "subj-01-01"]
    assert len(dose_lines) == 1
    rendered = json.dumps(lines)
    for secret in ("Mara", "Chen", "MMR", "Dr. Lee", "cried", "2026-08-15"):
        assert secret not in rendered


def test_refusals_happen_before_any_write(household):
    store, roster, a, _ = household
    with pytest.raises(ValueError, match="not on the roster"):
        doses.add_dose(store, roster, subject="subj-09", vaccine="MMR", dose_date="2026-08-15")
    with pytest.raises(ValueError, match="names its vaccine"):
        doses.add_dose(store, roster, subject=a, vaccine="   ", dose_date="2026-08-15")
    with pytest.raises(UnparseableDate):
        doses.add_dose(store, roster, subject=a, vaccine="MMR", dose_date="next Tuesday")
    with pytest.raises(UnparseableDate):
        doses.add_dose(store, roster, subject=a, vaccine="MMR", dose_date="2026-08-15",
                       next_due="soon")
    assert store.records(doses.MATTER) == []


def test_dates_are_stored_in_their_iso_form(household):
    store, roster, a, _ = household
    ref = doses.add_dose(store, roster, subject=a, vaccine="MMR",
                         dose_date="August 15, 2026", next_due="Sep 20 2026")
    detail = serve(store.get(doses.MATTER, doses.DOSE_ITEM, ref.id), Surface.S1_DETAIL)
    assert detail.value["dose_date"] == "2026-08-15"
    (nxt_ref, nxt), = doses.next_due_of(store, a)
    assert nxt_ref.id == ref.id
    assert nxt.rung is Rung.L2
    assert serve(nxt, Surface.S1_LIST).value == "2026-09-20"


def test_empty_optional_fields_are_left_out_not_stored_blank(household):
    store, roster, a, _ = household
    ref = doses.add_dose(store, roster, subject=a, vaccine="MMR", dose_date="2026-08-15",
                         provider="  ", notes=None)
    detail = serve(store.get(doses.MATTER, doses.DOSE_ITEM, ref.id), Surface.S1_DETAIL)
    assert set(detail.value) == {"subject", "vaccine", "dose_date"}
    assert doses.next_due_of(store, a) == []


def test_dose_ref_reads_an_id_back_and_refuses_a_non_id():
    ref = doses.dose_ref("subj-03-07")
    assert ref.subject == "subj-03" and ref.id == "subj-03-07"
    for bad in ("", "subj-03", "MMR", "subj-03-x"):
        with pytest.raises(ValueError):
            doses.dose_ref(bad)


def test_the_school_form_consumes_these_records_unchanged(household):
    store, roster, a, _ = household
    doses.add_dose(store, roster, subject=a, vaccine="MMR", dose_date="2026-08-15")
    doses.add_dose(store, roster, subject=a, vaccine="DTaP", dose_date="2026-05-01")
    from homestead_health.school_form import export_history

    receipt = export_history(a, [rec for _, rec in doses.doses_of(store, a)])
    body = json.loads(receipt.artifact.read_text(encoding="utf-8"))
    text = json.dumps(body)
    assert "MMR" in text and "DTaP" in text
    assert "Mara" not in text


def test_the_today_line_counts_next_due_dates_and_stays_gated(household):
    store, roster, a, b = household
    assert doses.today_line(store, roster, today="2026-09-11") is None

    doses.add_dose(store, roster, subject=a, vaccine="MMR", dose_date="2026-08-15", next_due="2026-09-20")
    # one due date in one child: the count resolves to that child — nothing
    assert doses.today_line(store, roster, today="2026-09-11") is None

    doses.add_dose(store, roster, subject=b, vaccine="DTaP", dose_date="2026-08-01", next_due="2026-09-05")
    assert doses.today_line(store, roster, today="2026-09-11") == "2 immunizations due this month"
    # a different month: neither falls in it
    assert doses.today_line(store, roster, today="2026-10-11") is None


def test_a_one_child_household_never_renders_a_count(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    store = Sidecar()
    roster = Roster(store)
    a = roster.add(name="Solo", minor=True)
    doses.add_dose(store, roster, subject=a, vaccine="MMR", dose_date="2026-08-15", next_due="2026-09-20")
    doses.add_dose(store, roster, subject=a, vaccine="DTaP", dose_date="2026-08-15", next_due="2026-09-21")
    assert doses.today_line(store, roster, today="2026-09-11") is None


# ── the W0 audit's additions ────────────────────────────────────────────────


def test_a_dose_is_l4_whatever_subset_of_fields_it_carries(household):
    """I-12, exhaustively: `compose()` runs over the fields *given*, and the one
    that is never optional is `vaccine` (L4). So there is no combination of
    optional fields — none given, all given, any subset — that stores a dose
    below L4, and therefore none that renders a vaccine or a dose date on a list
    surface. Asserted over the whole power set rather than one happy case,
    because the failure mode is a *particular* subset (say: vaccine plus a lone
    L2 lot number) composing lower than the others.
    """
    import itertools

    store, roster, a, _ = household
    optional = {"provider": "Dr. Lee", "lot_number": "AB12",
                "source": "clinic card", "notes": "cried a little"}
    for size in range(len(optional) + 1):
        for combo in itertools.combinations(sorted(optional), size):
            ref = doses.add_dose(store, roster, subject=a, vaccine="MMR",
                                 dose_date="2026-08-15",
                                 **{k: optional[k] for k in combo})
            record = store.get(doses.MATTER, doses.DOSE_ITEM, ref.id)
            assert record.rung is Rung.L4, f"{combo} composed to {record.rung}"
            assert serve(record, Surface.S1_LIST).disposition is Disposition.DERIVE


def test_a_list_row_is_the_derived_sentence_even_for_a_record_that_would_render():
    """The list pane refuses to print a payload, and that is not the same claim
    as "a dose is always L4".

    A dose written by `add_dose` composes to L4 and the gate derives it. But a
    *record* is a file on disk: a hand-edit, a half-restored tree, or a future
    writer that skips `add_dose` can leave a dose-shaped record at L2 — and L2
    RENDERs on a list surface. The surfaces printed `str(Served.value)`
    unconditionally, so such a record put the vaccine, the dose date, the
    provider and the operator's notes on an ambient row beside the subject id:
    exactly what the pack's `dose_date` declaration promises cannot happen.

    The violation is planted here as the record itself, because that is the only
    way in.
    """
    from homestead.keep.rungs import Classified

    planted = Classified(Rung.L2, {"subject": "subj-01", "vaccine": "MMR",
                                   "dose_date": "2026-08-15",
                                   "notes": "cried a little"})
    assert serve(planted, Surface.S1_LIST).disposition is Disposition.RENDER, (
        "the plant must be a record the gate would render on a list — otherwise "
        "this test passes for the wrong reason"
    )

    rung, text = doses.list_row(planted)
    assert rung is Rung.L2                      # the row still tells the truth
    assert text == doses.DERIVED
    for leaked in ("MMR", "2026-08-15", "cried"):
        assert leaked not in text


def test_a_list_row_for_a_denied_record_is_nothing_at_all(household):
    """`L5` (and a rung that did not survive at all) is dropped, with no count
    left behind — `serve_all`'s discipline, one record at a time."""
    from homestead.keep.rungs import Classified

    assert doses.list_row(Classified(Rung.L5, {"vaccine": "MMR"})) is None


def test_next_due_text_is_a_date_or_nothing():
    """The L2 date renders on the list; anything that does not render there is
    not a date and does not go where a date goes."""
    from homestead.keep.rungs import Classified

    assert doses.next_due_text(Classified(Rung.L2, "2026-09-20")) == "2026-09-20"
    assert doses.next_due_text(
        Classified(Rung.L4, "2026-09-20", derived="A date is on file")) is None
    assert doses.next_due_text(Classified(Rung.L5, "2026-09-20")) is None


def test_the_derived_sentence_has_no_slot_to_advise_or_to_leak_through(household):
    """H-2's structural half, on the dose surface.

    `due.DERIVED` is a closed vocabulary parameterised by a count; the dose's
    own ambient sentence is parameterised by **nothing**. No format field, no
    percent slot, no digit — so there is no code path that can compose *"due for
    a booster"* onto a list row, and no way for a vaccine name or a date to be
    interpolated into it. `list_row` returns the constant itself, for every dose
    there can be, which is the same claim made behaviourally.
    """
    import string

    assert not [f for _, f, _, _ in string.Formatter().parse(doses.DERIVED) if f]
    assert "%" not in doses.DERIVED
    assert not any(ch.isdigit() for ch in doses.DERIVED)

    store, roster, a, _ = household
    for vaccine, note in (("MMR", "cried"), ("HPV", "second of two"), ("Tdap", "")):
        ref = doses.add_dose(store, roster, subject=a, vaccine=vaccine,
                             dose_date="2026-08-15", notes=note or None)
        _, text = doses.list_row(store.get(doses.MATTER, doses.DOSE_ITEM, ref.id))
        assert text == doses.DERIVED


def test_a_raced_id_is_refused_by_the_store_and_nothing_is_written(household, monkeypatch):
    """Two processes adding a dose for the same subject can both count `NN` from
    disk before either writes — a TOCTOU the counter cannot close from here.

    The store closes it: `put` is `O_EXCL` and refuses an occupied key (I-9), so
    the loser gets `FileExistsError` and **writes nothing** — not the dose, and
    not the next-due record beside it. The id is not burned either, because the
    next call recounts. The race is planted by pinning the counter, which is
    precisely what the losing process has: a stale count.
    """
    store, roster, a, _ = household
    winner = doses.add_dose(store, roster, subject=a, vaccine="MMR",
                            dose_date="2026-08-15", next_due="2026-09-20")

    recount = doses._next_number
    monkeypatch.setattr(doses, "_next_number", lambda store, sid: 1)
    with pytest.raises(FileExistsError):
        doses.add_dose(store, roster, subject=a, vaccine="DTaP",
                       dose_date="2026-08-16", next_due="2026-09-05")

    # The winner's record is untouched and the loser left nothing behind.
    assert [r.id for r, _ in doses.doses_of(store, a)] == [winner.id]
    kept = serve(store.get(doses.MATTER, doses.DOSE_ITEM, winner.id), Surface.S1_DETAIL)
    assert kept.value["vaccine"] == "MMR"
    assert [doses.next_due_text(rec) for _, rec in doses.next_due_of(store, a)] == ["2026-09-20"]

    # And the id is not burned: recounting hands out the next one. (Restored by
    # name, not by `monkeypatch.undo()` — that would also undo the fixture's
    # HOMESTEAD_HOME and point the rest of this test at a real household root.)
    monkeypatch.setattr(doses, "_next_number", recount)
    assert doses.add_dose(store, roster, subject=a, vaccine="DTaP",
                          dose_date="2026-08-16").id == "subj-01-02"


def test_a_malformed_subject_is_refused_as_export_refused_not_a_value_error(household):
    """`_egress.validate_subject` is the module's one subject validator, and it
    raises `ExportRefused` — a `PermissionError`, *not* a `ValueError`. Both
    surfaces caught `ValueError` only, so the likeliest operator mistake of all
    — typing the person's name where the opaque id goes — came back as a
    traceback that then echoed the name. The type is asserted here so a surface
    knows what it must catch."""
    from homestead.keep.export import ExportRefused

    store, roster, a, _ = household
    for bad in ("Mara Chen", "subj-01\nFORGED", "../subj-01", None, "   "):
        with pytest.raises(ExportRefused) as caught:
            doses.add_dose(store, roster, subject=bad, vaccine="MMR",
                           dose_date="2026-08-15")
        assert not isinstance(caught.value, ValueError)
    assert store.records(doses.MATTER) == []
