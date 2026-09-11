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
