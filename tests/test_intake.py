"""Tests for homestead_health.intake — text extraction from immunization records."""
from __future__ import annotations

import pytest
from homestead_health.intake import Extracted, extract


# ── vaccine abbreviation extraction ─────────────────────────────────────

class TestVaccineAbbreviations:
    def test_dtap(self):
        items = extract("DTaP dose 1")
        vaccines = [i for i in items if i.kind == "vaccine"]
        assert any(v.value == "DTaP" for v in vaccines)

    def test_mmr(self):
        items = extract("MMR given on 2026-01-15")
        vaccines = [i for i in items if i.kind == "vaccine"]
        assert any(v.value == "MMR" for v in vaccines)

    def test_hepb(self):
        items = extract("HepB at birth")
        vaccines = [i for i in items if i.kind == "vaccine"]
        assert any(v.value == "HepB" for v in vaccines)

    def test_ipv(self):
        items = extract("IPV dose 3 of 4")
        vaccines = [i for i in items if i.kind == "vaccine"]
        assert any(v.value == "IPV" for v in vaccines)

    def test_varicella(self):
        items = extract("Varicella dose 1 of 2")
        vaccines = [i for i in items if i.kind == "vaccine"]
        assert any(v.value == "Varicella" for v in vaccines)

    def test_influenza(self):
        items = extract("Influenza annual")
        vaccines = [i for i in items if i.kind == "vaccine"]
        assert any(v.value == "Influenza" for v in vaccines)

    def test_menacwy(self):
        items = extract("MenACWY dose 1")
        vaccines = [i for i in items if i.kind == "vaccine"]
        assert any(v.value == "MenACWY" for v in vaccines)

    def test_hpv(self):
        items = extract("HPV dose 1 of 2")
        vaccines = [i for i in items if i.kind == "vaccine"]
        assert any(v.value == "HPV" for v in vaccines)

    def test_tdap(self):
        items = extract("Tdap booster")
        vaccines = [i for i in items if i.kind == "vaccine"]
        assert any(v.value == "Tdap" for v in vaccines)

    def test_pcv(self):
        items = extract("PCV dose 4 of 4")
        vaccines = [i for i in items if i.kind == "vaccine"]
        assert any(v.value == "PCV" for v in vaccines)


# ── vaccine full name extraction ────────────────────────────────────────

class TestVaccineFullNames:
    def test_hepatitis_b(self):
        items = extract("Hepatitis B vaccine given")
        vaccines = [i for i in items if i.kind == "vaccine"]
        assert any(v.value == "HepB" for v in vaccines)

    def test_measles(self):
        items = extract("measles, mumps, rubella combination")
        vaccines = [i for i in items if i.kind == "vaccine"]
        values = {v.value for v in vaccines}
        assert "MMR" in values

    def test_chickenpox(self):
        items = extract("chickenpox vaccine administered")
        vaccines = [i for i in items if i.kind == "vaccine"]
        assert any(v.value == "Varicella" for v in vaccines)

    def test_polio(self):
        items = extract("polio vaccine dose 2")
        vaccines = [i for i in items if i.kind == "vaccine"]
        assert any(v.value == "IPV" for v in vaccines)

    def test_flu(self):
        items = extract("flu shot given annually")
        vaccines = [i for i in items if i.kind == "vaccine"]
        assert any(v.value == "Influenza" for v in vaccines)


# ── date extraction ─────────────────────────────────────────────────────

class TestDates:
    def test_iso_date(self):
        items = extract("Given on 2026-03-15")
        dates = [i for i in items if i.kind == "date"]
        assert any(d.value == "2026-03-15" for d in dates)

    def test_written_date(self):
        items = extract("Administered March 15, 2026")
        dates = [i for i in items if i.kind == "date"]
        assert any(d.value == "2026-03-15" for d in dates)

    def test_us_date(self):
        items = extract("Date: 3/15/2026")
        dates = [i for i in items if i.kind == "date"]
        assert any(d.value == "2026-03-15" for d in dates)

    def test_abbreviated_month(self):
        items = extract("Given Jan. 5, 2026")
        dates = [i for i in items if i.kind == "date"]
        assert any(d.value == "2026-01-05" for d in dates)

    def test_multiple_dates(self):
        items = extract("Dose 1: 2026-01-15  Dose 2: 2026-03-15")
        dates = [i for i in items if i.kind == "date"]
        assert len(dates) >= 2


# ── provider extraction ─────────────────────────────────────────────────

class TestProviders:
    def test_dr_lastname(self):
        items = extract("Dr. Smith administered the vaccine")
        providers = [i for i in items if i.kind == "provider"]
        assert any("Smith" in p.value for p in providers)

    def test_doctor_lastname(self):
        items = extract("Doctor Martinez gave the shot")
        providers = [i for i in items if i.kind == "provider"]
        assert any("Martinez" in p.value for p in providers)

    def test_clinic_name(self):
        items = extract("Sunrise Pediatrics")
        providers = [i for i in items if i.kind == "provider"]
        assert any("Sunrise" in p.value for p in providers)

    def test_medical_center(self):
        items = extract("Valley Children's Medical Center")
        providers = [i for i in items if i.kind == "provider"]
        assert len(providers) >= 1

    def test_provider_label(self):
        items = extract("Provider: Kaiser Permanente South Bay")
        providers = [i for i in items if i.kind == "provider"]
        assert any("Kaiser" in p.value for p in providers)

    def test_administered_by(self):
        items = extract("Administered by: County Health Dept")
        providers = [i for i in items if i.kind == "provider"]
        assert len(providers) >= 1


# ── lot number extraction ───────────────────────────────────────────────

class TestLotNumbers:
    def test_lot_hash(self):
        items = extract("Lot# EN6208")
        lots = [i for i in items if i.kind == "lot"]
        assert any(l.value == "EN6208" for l in lots)

    def test_lot_colon(self):
        items = extract("Lot: AB1234-56")
        lots = [i for i in items if i.kind == "lot"]
        assert any("AB1234" in l.value for l in lots)

    def test_lot_number_word(self):
        items = extract("LOT Number: XY7890")
        lots = [i for i in items if i.kind == "lot"]
        assert any(l.value == "XY7890" for l in lots)


# ── dose info extraction ────────────────────────────────────────────────

class TestDoseInfo:
    def test_dose_of(self):
        items = extract("dose 2 of 3")
        doses = [i for i in items if i.kind == "dose"]
        assert any(d.value == "dose 2 of 3" for d in doses)

    def test_nth_dose(self):
        items = extract("1st dose given")
        doses = [i for i in items if i.kind == "dose"]
        assert any("dose 1" in d.value for d in doses)

    def test_booster(self):
        items = extract("Tdap booster given")
        doses = [i for i in items if i.kind == "dose"]
        assert any(d.value == "booster" for d in doses)


# ── full clinic card ────────────────────────────────────────────────────

class TestFullClinicCard:
    SAMPLE = """\
IMMUNIZATION RECORD

Patient: [redacted]
DOB: [redacted]

Date: 3/15/2026
Vaccine: DTaP dose 2 of 5
Lot# EN6208
Provider: Sunrise Pediatrics
Administered by: Dr. Martinez

Date: 6/10/2026
Vaccine: IPV dose 2 of 4
Lot: AB1234-56
Site: Valley Children's Medical Center
"""

    def test_finds_vaccines(self):
        items = extract(self.SAMPLE)
        vaccines = [i for i in items if i.kind == "vaccine"]
        values = {v.value for v in vaccines}
        assert "DTaP" in values
        assert "IPV" in values

    def test_finds_dates(self):
        items = extract(self.SAMPLE)
        dates = [i for i in items if i.kind == "date"]
        values = {d.value for d in dates}
        assert "2026-03-15" in values
        assert "2026-06-10" in values

    def test_finds_lot_numbers(self):
        items = extract(self.SAMPLE)
        lots = [i for i in items if i.kind == "lot"]
        assert len(lots) >= 2

    def test_finds_providers(self):
        items = extract(self.SAMPLE)
        providers = [i for i in items if i.kind == "provider"]
        assert len(providers) >= 2

    def test_sorted_by_position(self):
        items = extract(self.SAMPLE)
        positions = [i.start for i in items]
        assert positions == sorted(positions)

    def test_no_duplicates(self):
        items = extract(self.SAMPLE)
        keys = [(i.start, i.end, i.kind) for i in items]
        assert len(keys) == len(set(keys))


# ── edge cases ──────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_text(self):
        assert extract("") == []

    def test_no_health_content(self):
        items = extract("The weather is sunny today in Los Angeles.")
        vaccines = [i for i in items if i.kind == "vaccine"]
        assert len(vaccines) == 0

    def test_field_attribute(self):
        items = extract("DTaP dose 1")
        vaccines = [i for i in items if i.kind == "vaccine"]
        assert all(v.field == "vaccine" for v in vaccines)
        dates_items = extract("2026-01-15")
        dates = [i for i in dates_items if i.kind == "date"]
        assert all(d.field == "dose_date" for d in dates)
