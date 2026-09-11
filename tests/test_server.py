"""The browser UI — the door a household enrols members and records doses through.

`server.build_server()` binds the real handlers on an ephemeral port without
serving, so this suite drives them end to end with `http.client`. No Nestor is
needed for any of it. The invariants hold at the browser exactly as on the CLI: a
dose lists as its derived form and renders in the detail; a name never reaches a
list row for a minor; the Today line is gated k ≥ 2; a bad date is refused at
entry.
"""
from __future__ import annotations

import http.client
import json
import threading

import pytest

from homestead_health import server


@pytest.fixture
def ui(tmp_path, monkeypatch):
    monkeypatch.setenv("HOMESTEAD_HOME", str(tmp_path))
    srv = server.build_server(host="127.0.0.1", port=0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()

    class _Client:
        host, port = srv.server_address[0], srv.server_address[1]

        def get(self, path):
            conn = http.client.HTTPConnection(self.host, self.port, timeout=5)
            conn.request("GET", path)
            resp = conn.getresponse()
            body = resp.read()
            conn.close()
            return resp.status, body

        def json(self, path, payload=None):
            conn = http.client.HTTPConnection(self.host, self.port, timeout=5)
            if payload is None:
                conn.request("GET", path)
            else:
                conn.request("POST", path, body=json.dumps(payload),
                             headers={"Content-Type": "application/json"})
            resp = conn.getresponse()
            data = json.loads(resp.read())
            conn.close()
            return resp.status, data

    try:
        yield _Client()
    finally:
        srv.shutdown()
        srv.server_close()


def _enrol(ui, name, minor):
    status, data = ui.json("/api/roster", {"name": name, "minor": minor})
    assert status == 200 and data["ok"], data
    return data["id"]


def test_the_page_serves_and_carries_the_dose_form(ui):
    status, body = ui.get("/")
    assert status == 200
    page = body.decode()
    for field in ("dsubject", "dvaccine", "ddate", "dnext", "dprovider", "dlot", "dsource", "dnotes"):
        assert f'id="{field}"' in page
    assert "/api/dose" in page and "/api/roster" in page
    assert "/api/store" not in page


def test_roster_round_trip_derives_a_minor_on_the_list(ui):
    assert _enrol(ui, "Mara Chen", True) == "subj-01"
    assert _enrol(ui, "Rudi", False) == "subj-02"
    status, data = ui.json("/api/roster")
    by_id = {s["id"]: s for s in data["subjects"]}
    assert by_id["subj-01"]["minor"] is True
    assert by_id["subj-02"]["minor"] is False and by_id["subj-02"]["display"] == "Rudi"


def test_dose_round_trip_through_the_gate(ui):
    sid = _enrol(ui, "Mara Chen", True)
    status, data = ui.json("/api/dose", {"subject": sid, "vaccine": "MMR", "dose_date": "2026-08-15",
                                         "next_due": "2026-09-20", "provider": "Dr. Lee",
                                         "lot_number": "AB12", "source": "clinic card", "notes": ""})
    assert status == 200 and data == {"ok": True, "id": "subj-01-01", "rung": "L4"}

    status, data = ui.json(f"/api/doses?subject={sid}")
    assert data["doses"] == [{"id": "subj-01-01", "rung": "L4",
                              "text": "An immunization dose is on file", "next_due": "2026-09-20"}]
    assert "MMR" not in json.dumps(data) and "Mara" not in json.dumps(data)

    status, data = ui.json("/api/dose?id=subj-01-01")
    assert status == 200 and data["rendered"] is True and data["rung"] == "L4"
    assert data["fields"] == {"subject": "subj-01", "vaccine": "MMR", "dose_date": "2026-08-15",
                              "provider": "Dr. Lee", "lot_number": "AB12", "source": "clinic card"}


def test_dose_refusals_at_entry(ui):
    status, data = ui.json("/api/dose", {"subject": "subj-09", "vaccine": "MMR", "dose_date": "2026-08-15"})
    assert status == 400 and "roster" in data["error"]
    sid = _enrol(ui, "Mara Chen", True)
    status, data = ui.json("/api/dose", {"subject": sid, "vaccine": "", "dose_date": "2026-08-15"})
    assert status == 400
    status, data = ui.json("/api/dose", {"subject": sid, "vaccine": "MMR", "dose_date": "soonish"})
    assert status == 400 and data["ok"] is False
    status, data = ui.json(f"/api/doses?subject={sid}")
    assert data["doses"] == []
    status, data = ui.json("/api/dose?id=subj-01-01")
    assert status == 404
    status, data = ui.json("/api/doses?subject=nobody")
    assert status == 400


def test_the_today_line_is_gated_at_the_browser(ui):
    a = _enrol(ui, "Mara", True)
    status, data = ui.json("/api/today?today=2026-09-11")
    assert data["line"] is None
    ui.json("/api/dose", {"subject": a, "vaccine": "MMR", "dose_date": "2026-08-15", "next_due": "2026-09-20"})
    status, data = ui.json("/api/today?today=2026-09-11")
    assert data["line"] is None                          # one child: nothing
    b = _enrol(ui, "Ivo", True)
    ui.json("/api/dose", {"subject": b, "vaccine": "DTaP", "dose_date": "2026-08-01", "next_due": "2026-09-05"})
    status, data = ui.json("/api/today?today=2026-09-11")
    assert data["line"] == "2 immunizations due this month"


def test_intake_extracts_without_storing(ui):
    status, data = ui.json("/api/extract", {"text": "MMR given 2026-08-15 at Sunrise Pediatrics, Lot AB12"})
    kinds = {i["kind"] for i in data["items"]}
    assert {"vaccine", "date"} <= kinds
    _enrol(ui, "Mara", True)
    status, data = ui.json("/api/doses?subject=subj-01")
    assert data["doses"] == []


def test_status_and_localhost(ui):
    status, data = ui.json("/api/status")
    assert status == 200 and isinstance(data["nestor"], bool)
    assert ui.host == "127.0.0.1"
