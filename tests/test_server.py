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


# ── the W0 audit's additions ────────────────────────────────────────────────


def _raw(ui, method, path, body=None, headers=None):
    """One request with the bytes and the headers exactly as given — the point
    is to send what a browser would not."""
    conn = http.client.HTTPConnection(ui.host, ui.port, timeout=5)
    try:
        conn.request(method, path, body=body, headers=headers or {})
        resp = conn.getresponse()
        return resp.status, resp.read()
    finally:
        conn.close()


@pytest.mark.parametrize("name,body,headers,status", [
    ("malformed JSON", "{not json", {"Content-Length": "9"}, 400),
    ("a body that is not an object", "[1,2]", {"Content-Length": "5"}, 400),
    ("a Content-Length that is not a number", "{}", {"Content-Length": "abc"}, 400),
    ("a negative Content-Length", "{}", {"Content-Length": "-1"}, 400),
])
def test_a_bad_request_body_is_answered_not_dropped(ui, name, body, headers, status):
    """Every one of these closed the connection with no response at all and put
    a traceback on the operator's terminal: `json.loads` on rubbish, `.get` on a
    list, `int("abc")`. A localhost UI is still a parser at a socket — it
    answers, with a status, or it is not a door anyone can reason about.

    The answer also never echoes the body back: a refusal says what was wrong
    with the envelope, never what was in it (I-15's shape at the boundary).
    """
    got, raw = _raw(ui, "POST", "/api/roster", body=body, headers=headers)
    assert got == status, raw
    payload = json.loads(raw)
    assert payload["ok"] is False and payload["error"]
    assert "not json" not in payload["error"]


def test_an_oversized_body_is_refused_before_it_is_read(ui):
    """There was no cap at all: `rfile.read(n)` allocated whatever the header
    asked for, and a three-megabyte name was accepted and stored. The cap is
    checked against the *header*, so nothing large is read to find out."""
    from homestead_health.server import _MAX_BODY

    huge = json.dumps({"name": "A" * (_MAX_BODY + 4096)})
    assert len(huge) > _MAX_BODY
    status, raw = _raw(ui, "POST", "/api/roster", body=huge,
                       headers={"Content-Length": str(len(huge))})
    assert status == 413
    assert json.loads(raw)["error"]
    status, data = ui.json("/api/roster")
    assert data["subjects"] == []


def test_a_missing_content_length_is_an_empty_body_not_a_crash(ui):
    status, raw = _raw(ui, "POST", "/api/roster", body=None)
    assert status == 400
    assert json.loads(raw)["error"] == "name is required"


@pytest.mark.parametrize("payload,status", [
    ({"name": 5}, 400),                      # AttributeError on .strip() before
    ({"name": ["Mara"]}, 400),
    ({"name": None}, 400),
    ({"name": "Mara", "minor": "false"}, 400),
    ({"name": "Mara", "minor": "true"}, 400),
    ({"name": "Mara", "minor": 1}, 400),
])
def test_roster_refuses_values_of_the_wrong_type(ui, payload, status):
    """`name` was `.strip()`ed without a type check, so `{"name": 5}` dropped the
    connection.

    `minor` is the sharper one: it is not a truthiness question, it **is** the
    name's rung (L4 minor, L3 adult), and `bool("false")` read the string
    `"false"` as a minor. That direction over-protects, which is the safe one —
    but the tempting tightening the other way (`minor is True`) would read
    `"true"` as an *adult*, which is the fail-open direction `Roster.is_minor`
    calls catastrophic. Refusing anything that is not a JSON boolean is the only
    reading that is wrong in neither direction.
    """
    got, raw = ui.json("/api/roster", payload)
    assert got == status, raw
    status2, data = ui.json("/api/roster")
    assert data["subjects"] == []


def test_a_boolean_minor_still_works_both_ways(ui):
    assert _enrol(ui, "Mara Chen", True) == "subj-01"
    assert _enrol(ui, "Rudi", False) == "subj-02"
    _, data = ui.json("/api/roster")
    assert [s["minor"] for s in data["subjects"]] == [True, False]


def test_a_name_typed_into_the_subject_box_is_a_400_not_a_500(ui):
    """`_egress.validate_subject` raises `ExportRefused` — a `PermissionError`,
    not a `ValueError` — so the likeliest operator mistake fell through to the
    catch-all and was answered `500`: a server fault for an input the operator
    can fix."""
    status, data = ui.json("/api/dose", {"subject": "Mara Chen", "vaccine": "MMR",
                                         "dose_date": "2026-08-15"})
    assert status == 400 and data["ok"] is False
    status, data = ui.json("/api/dose", {"vaccine": "MMR", "dose_date": "2026-08-15"})
    assert status == 400


def test_a_raced_dose_id_is_a_409_not_a_500(ui, monkeypatch):
    """The store refuses a second writer's `put` with `FileExistsError` (I-9),
    an `OSError` — so it too fell through to the catch-all `500` that echoed
    `str(exc)`. A taken id is the client's to retry: 409, and a fixed sentence."""
    from homestead_health import doses

    sid = _enrol(ui, "Mara", True)
    ui.json("/api/dose", {"subject": sid, "vaccine": "MMR", "dose_date": "2026-08-15"})
    monkeypatch.setattr(doses, "_next_number", lambda store, s: 1)
    status, data = ui.json("/api/dose", {"subject": sid, "vaccine": "DTaP",
                                         "dose_date": "2026-08-16"})
    assert status == 409
    assert "Nothing was stored" in data["error"]
    assert "already exists" not in data["error"]      # not the store's own text


def test_the_last_resort_answer_never_echoes_an_exception(ui, monkeypatch):
    """The catch-all answered `str(exc)` for *any* exception, so the next
    exception type to carry a field value would have carried it to the browser.
    Planted with an exception whose message is a name and a vaccine."""
    from homestead_health import doses

    def boom(*a, **k):
        raise RuntimeError("Mara Chen · MMR · 2026-08-15")

    monkeypatch.setattr(doses, "add_dose", boom)
    sid = "subj-01"
    status, data = ui.json("/api/dose", {"subject": sid, "vaccine": "MMR",
                                         "dose_date": "2026-08-15"})
    assert status == 500
    for secret in ("Mara", "MMR", "2026-08-15"):
        assert secret not in json.dumps(data)


def test_a_planted_sub_l4_dose_still_lists_as_its_derived_form(ui, tmp_path):
    """The browser list pane, against the record the gate *would* render — the
    same plant as the CLI's, one surface over, because `doses.list_row` is the
    one place the rule lives and both must be shown to use it."""
    from homestead.keep.record import Sidecar
    from homestead.keep.rungs import Classified, Rung

    from homestead_health import doses

    sid = _enrol(ui, "Mara Chen", True)
    Sidecar().put(doses.MATTER, doses.DOSE_ITEM, "subj-01-01",
                  Classified(Rung.L2, {"subject": sid, "vaccine": "MMR",
                                       "dose_date": "2026-08-15",
                                       "notes": "cried a little"}))
    status, data = ui.json(f"/api/doses?subject={sid}")
    assert status == 200
    assert data["doses"] == [{"id": "subj-01-01", "rung": "L2",
                              "text": "An immunization dose is on file"}]
    rendered = json.dumps(data)
    for leaked in ("MMR", "2026-08-15", "cried", "Mara"):
        assert leaked not in rendered


def test_a_bad_today_is_a_400_and_an_empty_one_is_todays_date(ui):
    """I-31's surface: the Today line is computed from a date the engine parses,
    and a date it will not parse is the client's error, not a crash."""
    status, data = ui.json("/api/today?today=garbage")
    assert status == 400 and "error" in data
    status, data = ui.json("/api/today?today=")
    assert status == 200 and data["line"] is None
    status, data = ui.json("/api/today")
    assert status == 200 and data["line"] is None


def test_every_dose_id_the_browser_is_handed_is_the_minted_shape(ui):
    """The list template builds `onclick="openDose('<id>')"` — an attribute
    context, and `esc()` (a `textContent` round-trip) escapes `&<>` but not the
    apostrophe that would close it. What holds that seam is that an id is never
    free text: `doses.doses_of` returns only keys matching `subj-NN-NN`, so the
    quote cannot be in one. Asserted here so a future loosening of the key scan
    fails at the surface that depends on it."""
    import re

    sid = _enrol(ui, "Mara", True)
    for i in range(3):
        ui.json("/api/dose", {"subject": sid, "vaccine": "MMR",
                              "dose_date": f"2026-08-1{i + 1}"})
    _, data = ui.json(f"/api/doses?subject={sid}")
    assert len(data["doses"]) == 3
    for d in data["doses"]:
        assert re.fullmatch(r"subj-\d+-\d{2,}", d["id"]), d["id"]


def test_extract_refuses_text_that_is_not_text(ui):
    status, data = ui.json("/api/extract", {"text": 5})
    assert status == 400


class _Sock:
    """A socket that hands out the chunks it was given, honouring the size
    asked for, then whatever `then` is — `b""` for a peer that closed, or an
    exception to raise."""

    def __init__(self, chunks, then=b""):
        self.chunks = list(chunks)
        self.then = then
        self.timeout = None
        self.asked = []

    def settimeout(self, t):
        self.timeout = t

    def recv(self, n):
        self.asked.append(n)
        if self.chunks:
            head, rest = self.chunks[0][:n], self.chunks[0][n:]
            if rest:
                self.chunks[0] = rest
            else:
                self.chunks.pop(0)
            return head
        if isinstance(self.then, BaseException):
            raise self.then
        return self.then


def test_a_refused_body_is_drained_before_the_socket_closes():
    """Closing a socket with unread bytes in its receive buffer turns the
    close into a reset, and on Windows a reset discards the 400 the client
    has not read yet (`WinError 10053`, seen on the law module's release PR
    for its bad-Content-Length test).  The drain reads what arrived, waits
    only `DRAIN_TIMEOUT_SECONDS` for more, is bounded by the cap, and
    swallows the socket's own errors — the answer is already sent."""
    sock = _Sock([b"{}", b"more"])
    assert server._drain(sock) == 6
    assert sock.timeout == server.DRAIN_TIMEOUT_SECONDS
    sock = _Sock([b"{}"], then=TimeoutError())
    assert server._drain(sock) == 2
    sock = _Sock([b"x" * 65536] * 40)
    assert server._drain(sock, limit=100_000) == 100_000
    assert max(sock.asked) <= 65536 and sum(sock.asked) >= 100_000
    sock = _Sock([], then=OSError())
    assert server._drain(sock) == 0


def test_a_refused_content_length_reaches_the_drain(ui, monkeypatch):
    """The refusal path must actually call the drain on the live connection —
    the unit test above proves what draining does, this proves it happens,
    once, after the answer is on the wire (the client read a 400)."""
    calls = []
    real = server._drain

    def _spy(sock, **kw):
        calls.append(sock)
        return real(sock, **kw)

    monkeypatch.setattr(server, "_drain", _spy)
    status, raw = _raw(ui, "POST", "/api/dose", body="{}",
                       headers={"Content-Length": "abc"})
    assert status == 400 and json.loads(raw)["error"]
    assert len(calls) == 1 and hasattr(calls[0], "recv")
