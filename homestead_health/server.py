"""Localhost web UI for homestead-health — intake and dashboard.

Serves on 127.0.0.1 only.  All HTML/CSS/JS is embedded (no external files,
no CDN).  Imports of ``http.server`` and ``urllib.parse`` are **local** to
``serve()`` — this module's top level touches nothing network-shaped, so
``import homestead_health`` stays import-pure.

The server is a thin dispatch over existing modules: ``intake.extract()``
for text extraction, the Nestor seam for entity resolution and care
decisions, the roster for subject management, and ``due`` for deadline
computation.

**Chokepoint**: this module never accesses ``.payload``.  Roster names reach
the browser through ``serve()`` (the gated display form).  Entity and
decision data come through Nestor's public API (dicts, not ``Classified``).
"""
from __future__ import annotations

__all__ = ["serve"]


# ── the page ──────────────────────────────────────────────────────────────

_PAGE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>homestead-health</title>
<style>
:root {
  --bg: #f3f7f4;
  --surface: #ffffff;
  --text: #2c2c2c;
  --text-2: #6b6560;
  --border: #d5e0db;
  --accent: #3d7a4f;
  --accent-h: #336a42;
  --accent-l: #e8f5ec;
  --ok: #3d7a4f;
  --ok-l: #e8f5ec;
  --warn: #b8862d;
  --warn-l: #fdf3e3;
  --danger: #b54a4a;
  --danger-l: #fce8e8;
  --blue: #4a6fa5;
  --blue-l: #e8eff8;
  --r: 6px;
}
*{box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;
  background:var(--bg);color:var(--text);margin:0;line-height:1.5}
header{background:var(--surface);border-bottom:1px solid var(--border);
  padding:12px 24px;display:flex;align-items:center;gap:16px}
header h1{font-size:18px;font-weight:600;margin:0}
header .sub{font-size:13px;color:var(--text-2)}
nav{background:var(--surface);border-bottom:1px solid var(--border);
  padding:0 24px;display:flex;gap:0}
.tb{background:none;border:none;border-bottom:2px solid transparent;
  padding:10px 16px;font-size:14px;color:var(--text-2);cursor:pointer}
.tb:hover{color:var(--text)}
.tb.on{color:var(--accent);border-bottom-color:var(--accent);font-weight:500}
main{max-width:900px;margin:24px auto;padding:0 24px}
.tab{display:none}.tab.on{display:block}
h2{font-size:16px;font-weight:600;margin:0 0 16px}
textarea{width:100%;min-height:180px;padding:12px;border:1px solid var(--border);
  border-radius:var(--r);font-family:inherit;font-size:14px;line-height:1.6;
  resize:vertical;background:var(--surface)}
textarea:focus{outline:2px solid var(--accent);border-color:transparent}
.btn{display:inline-block;padding:8px 16px;border:none;border-radius:var(--r);
  font-size:14px;font-weight:500;cursor:pointer}
.bp{background:var(--accent);color:#fff}.bp:hover{background:var(--accent-h)}
.bg{background:var(--ok);color:#fff}.bg:hover{background:#2d5c36}
.bs{padding:4px 10px;font-size:13px}
.btn:disabled{opacity:.5;cursor:not-allowed}
.acts{margin-top:12px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--r);
  padding:14px 16px;margin-bottom:10px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.cr{display:flex;align-items:center;gap:12px;flex-wrap:wrap}
.kb{display:inline-block;padding:2px 8px;border-radius:12px;font-size:12px;
  font-weight:500;text-transform:uppercase;letter-spacing:.5px}
.k-vaccine{background:var(--accent-l);color:var(--accent)}
.k-date{background:var(--blue-l);color:var(--blue)}
.k-provider{background:var(--warn-l);color:var(--warn)}
.k-lot{background:#f0e8f8;color:#6b4fa0}
.k-dose{background:#e8f0f8;color:#4a7fa5}
.mt{font-size:14px;flex:1;min-width:120px}
.mv{font-size:13px;color:var(--text-2)}
.fs{padding:4px 8px;border:1px solid var(--border);border-radius:4px;font-size:13px;
  background:var(--surface)}
.stored{opacity:.6}.stored .btn,.stored .fs{display:none}
.sm{display:inline-block;padding:4px 10px;border-radius:4px;font-size:13px;font-weight:500}
.s-ok{background:var(--ok-l);color:var(--ok)}
.s-err{background:var(--danger-l);color:var(--danger)}
.ri{display:flex;align-items:center;gap:12px;padding:10px 16px;background:var(--surface);
  border:1px solid var(--border);border-radius:var(--r);margin-bottom:8px;
  box-shadow:0 1px 3px rgba(0,0,0,.08)}
.ri .sid{font-size:13px;font-weight:600;min-width:60px;color:var(--accent)}
.ri .rn{flex:1;font-size:14px}
.ri .rm{font-size:12px;padding:2px 6px;border-radius:4px;font-weight:500}
.minor{background:var(--warn-l);color:var(--warn)}
.adult{background:#f0eeec;color:#888}
.rf{display:flex;gap:8px;align-items:center;margin-bottom:16px;flex-wrap:wrap}
.rf select,.rf input{padding:8px 12px;border:1px solid var(--border);border-radius:var(--r);
  font-size:14px;background:var(--surface)}
.rf input{flex:1;min-width:150px}
.rr{padding:16px;background:var(--surface);border:1px solid var(--border);border-radius:var(--r)}
.oi{padding:12px 16px;background:var(--surface);border:1px solid var(--border);
  border-radius:var(--r);margin-bottom:8px;box-shadow:0 1px 3px rgba(0,0,0,.08)}
.oq{font-weight:500}.oc{color:var(--text-2);margin-top:4px}
.os{display:inline-block;font-size:12px;padding:2px 8px;border-radius:12px;margin-top:6px}
.sealed{background:var(--ok-l);color:var(--ok)}
.draft{background:var(--warn-l);color:var(--warn)}
.empty{color:var(--text-2);font-style:italic;padding:24px 0;text-align:center}
.add-form{display:flex;gap:8px;align-items:center;margin-bottom:16px;flex-wrap:wrap}
.add-form input{padding:8px 12px;border:1px solid var(--border);border-radius:var(--r);
  font-size:14px;background:var(--surface);flex:1;min-width:120px}
.add-form label{font-size:13px;display:flex;align-items:center;gap:4px}
</style>
</head>
<body>
<header>
  <h1>homestead-health</h1>
  <span class="sub">immunization intake &amp; records</span>
</header>
<nav>
  <button class="tb on" onclick="show('intake',this)">Intake</button>
  <button class="tb" onclick="show('roster',this)">Roster</button>
  <button class="tb" onclick="show('entities',this)">Entities</button>
  <button class="tb" onclick="show('decisions',this)">Decisions</button>
</nav>
<main>

<section id="t-intake" class="tab on">
  <h2>Dump immunization text</h2>
  <textarea id="raw" placeholder="Paste a clinic card, shot record, portal printout, or pediatrician notes.  The system extracts vaccine names, dates, providers, lot numbers, and doses."></textarea>
  <div class="acts">
    <button class="btn bp" onclick="doExtract()">Extract</button>
  </div>
  <div id="res" style="margin-top:16px"></div>
</section>

<section id="t-roster" class="tab">
  <h2>Household members</h2>
  <div class="add-form">
    <input id="rname" placeholder="Name">
    <label><input type="checkbox" id="rminor"> Minor</label>
    <button class="btn bp bs" onclick="addSubject()">Add</button>
  </div>
  <div id="rlist"></div>
</section>

<section id="t-entities" class="tab">
  <h2>Entity lookup</h2>
  <div class="rf">
    <select id="edom">
      <option value="provider">Provider</option>
      <option value="vaccine">Vaccine</option>
    </select>
    <input id="eqry" placeholder="Name or term to resolve&#8230;"
           onkeydown="if(event.key==='Enter')doResolve()">
    <button class="btn bp" onclick="doResolve()">Resolve</button>
  </div>
  <div id="eres"></div>
</section>

<section id="t-decisions" class="tab">
  <h2>Care decisions</h2>
  <div id="dlist"></div>
</section>

</main>
<script>
function show(name, btn) {
  document.querySelectorAll('.tab').forEach(function(el){el.classList.remove('on')});
  document.querySelectorAll('.tb').forEach(function(el){el.classList.remove('on')});
  document.getElementById('t-'+name).classList.add('on');
  btn.classList.add('on');
  if(name==='roster') loadRoster();
  if(name==='decisions') loadDecisions();
}

function esc(s) {
  var d=document.createElement('div'); d.textContent=s; return d.innerHTML;
}

var _items=[];

function doExtract() {
  var text=document.getElementById('raw').value.trim();
  if(!text) return;
  fetch('/api/extract',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({text:text})})
  .then(function(r){return r.json()})
  .then(function(data){_items=data.items; renderItems()})
  .catch(function(){document.getElementById('res').innerHTML=
    '<p class="sm s-err">Extraction failed</p>'});
}

function renderItems() {
  var div=document.getElementById('res');
  if(!_items.length){div.innerHTML='<p class="empty">No structured items found.</p>';return;}
  var html='<h2>Found '+_items.length+' item(s)</h2>';
  _items.forEach(function(item,i){
    var opts='';
    if(item.kind==='vaccine'){
      opts='<option value="vaccine">Vaccine</option>';
    } else if(item.kind==='date'){
      opts='<option value="dose_date">Dose date</option><option value="next_due">Next due</option>';
    } else if(item.kind==='provider'){
      opts='<option value="provider">Provider</option>';
    } else if(item.kind==='lot'){
      opts='<option value="lot_number">Lot number</option>';
    } else {
      opts='<option value="">&#8212;</option>';
    }
    html+='<div class="card" id="c'+i+'"><div class="cr">'
      +'<span class="kb k-'+item.kind+'">'+item.kind+'</span>'
      +'<span class="mt">'+esc(item.text)+'</span>'
      +'<span class="mv">'+esc(item.value)+'</span>'
      +'<select class="fs" id="f'+i+'">'+opts+'</select>'
      +'<button class="btn bg bs" onclick="storeItem('+i+')">Store</button>'
      +'</div></div>';
  });
  div.innerHTML=html;
}

function storeItem(idx) {
  var item=_items[idx];
  var field=document.getElementById('f'+idx).value;
  if(!field) return;
  var card=document.getElementById('c'+idx);
  fetch('/api/store',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({field:field,value:item.value})})
  .then(function(r){return r.json()})
  .then(function(data){
    if(data.ok){card.classList.add('stored');
      card.innerHTML+='<span class="sm s-ok">Stored ('+data.rung+')</span>';}
    else{card.innerHTML+='<span class="sm s-err">'+esc(data.error||'Failed')+'</span>';}
  })
  .catch(function(){card.innerHTML+='<span class="sm s-err">Error</span>';});
}

function addSubject() {
  var name=document.getElementById('rname').value.trim();
  if(!name) return;
  var minor=document.getElementById('rminor').checked;
  fetch('/api/roster',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({name:name,minor:minor})})
  .then(function(r){return r.json()})
  .then(function(data){
    if(data.ok){
      document.getElementById('rname').value='';
      document.getElementById('rminor').checked=false;
      loadRoster();
    } else {
      alert(data.error||'Failed');
    }
  });
}

function loadRoster() {
  var div=document.getElementById('rlist');
  div.innerHTML='<p class="empty">Loading&#8230;</p>';
  fetch('/api/roster').then(function(r){return r.json()}).then(function(data){
    if(!data.subjects||!data.subjects.length){
      div.innerHTML='<p class="empty">No household members enrolled.</p>';return;}
    var html='';
    data.subjects.forEach(function(s){
      var mc=s.minor?'minor':'adult';
      html+='<div class="ri">'
        +'<span class="sid">'+esc(s.id)+'</span>'
        +'<span class="rn">'+esc(s.display)+'</span>'
        +'<span class="rm '+mc+'">'+(s.minor?'minor':'adult')+'</span>'
        +'</div>';
    });
    div.innerHTML=html;
  }).catch(function(){div.innerHTML='<p class="sm s-err">Failed to load roster</p>';});
}

function doResolve() {
  var domain=document.getElementById('edom').value;
  var query=document.getElementById('eqry').value.trim();
  if(!query) return;
  var div=document.getElementById('eres');
  div.innerHTML='<p class="empty">Resolving&#8230;</p>';
  fetch('/api/resolve?domain='+encodeURIComponent(domain)+'&surface='+encodeURIComponent(query))
  .then(function(r){return r.json()}).then(function(data){
    if(data.error){div.innerHTML='<p class="sm s-err">'+esc(data.error)+'</p>';return;}
    var r=data.result, html='<div class="rr">';
    html+='<p><strong>Query:</strong> '+esc(query)+'</p>';
    if(r.sealed){
      html+='<p><strong>Canonical:</strong> '+esc(r.canonical)
        +' <span class="os sealed">sealed</span></p>';
      html+='<p><strong>Confidence:</strong> '+r.confidence.toFixed(2)+'</p>';
      if(r.provenance&&r.provenance.verifier)
        html+='<p><strong>Verified by:</strong> '+esc(r.provenance.verifier)+'</p>';
    } else if(r.provenance&&r.provenance.suggestion){
      html+='<p><strong>Suggestion:</strong> '+esc(r.provenance.suggestion)
        +' <span class="os draft">draft</span></p>';
      html+='<p><strong>Confidence:</strong> '+r.confidence.toFixed(2)+'</p>';
      html+='<p style="color:var(--text-2)">Not sealed &#8212; seal with <code>nestor ui</code></p>';
    } else {
      html+='<p class="empty">No match found.</p>';
    }
    html+='</div>';
    div.innerHTML=html;
  }).catch(function(){div.innerHTML='<p class="sm s-err">Failed to resolve</p>';});
}

function loadDecisions() {
  var div=document.getElementById('dlist');
  div.innerHTML='<p class="empty">Loading&#8230;</p>';
  fetch('/api/decisions').then(function(r){return r.json()}).then(function(data){
    if(!data.decisions||!data.decisions.length){
      div.innerHTML='<p class="empty">No care decisions recorded.</p>';return;}
    var html='';
    data.decisions.forEach(function(d,i){
      var sc=d.status==='sealed'?'sealed':'draft';
      html+='<div class="oi">'
        +'<div class="oq">'+(i+1)+'. '+esc(d.question)+'</div>'
        +'<div class="oc">&rarr; '+esc(d.commitment)+'</div>'
        +'<span class="os '+sc+'">'+d.status+'</span>'
        +'</div>';
    });
    div.innerHTML=html;
  }).catch(function(){div.innerHTML='<p class="sm s-err">Failed to load decisions</p>';});
}
</script>
</body>
</html>
"""


# ── server ────────────────────────────────────────────────────────────────

def serve(*, host: str = "127.0.0.1", port: int = 8384) -> None:
    """Start the intake UI on localhost.  Blocks until Ctrl+C."""
    import http.server
    import json
    import urllib.parse
    import webbrowser

    from homestead.keep import paths
    from homestead.keep.record import Sidecar
    from homestead.keep.rungs import Classified, Rung, Surface, serve as rung_serve

    from homestead_health import nestor_seam
    from homestead_health.intake import extract
    from homestead_health.nestor_store import get_store
    from homestead_health.packs.immunizations import FIELDS, MATTER
    from homestead_health.roster import Roster

    root = paths.home()
    root.mkdir(parents=True, exist_ok=True)
    (root / "keep").mkdir(parents=True, exist_ok=True)

    try:
        nestor_seam.bind(root)
        nestor_ok = True
    except Exception:
        nestor_ok = False

    sidecar = Sidecar()
    roster = Roster(sidecar)

    def _derived(field: str) -> str:
        table = {
            "vaccine": "A vaccine dose is on file",
            "dose_date": "A dose date is on file",
            "next_due": "A due date is on file",
            "provider": "A provider is named",
            "lot_number": "A lot number is on file",
            "source": "A record source is on file",
            "notes": "An operator note is on file",
        }
        return table.get(field, f"A {field.replace('_', ' ')} is on file")

    class _H(http.server.BaseHTTPRequestHandler):

        def log_message(self, fmt, *args):
            pass

        def _json(self, obj, status=200):
            body = json.dumps(obj).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _html(self, content):
            body = content.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length", 0))
            return json.loads(self.rfile.read(n)) if n else {}

        # ── GET ───────────────────────────────────────────────────────

        def do_GET(self):
            p = urllib.parse.urlparse(self.path)
            qs = dict(urllib.parse.parse_qsl(p.query))

            if p.path == "/":
                return self._html(_PAGE)
            if p.path == "/api/roster":
                return self._get_roster()
            if p.path == "/api/resolve":
                return self._get_resolve(qs)
            if p.path == "/api/decisions":
                return self._get_decisions()
            self.send_error(404)

        def _get_roster(self):
            subjects = []
            for ref in roster.subjects():
                record = roster.name_of(ref)
                served = rung_serve(record, Surface.S1_DETAIL)
                display = str(served.value) if served.value else str(ref)
                subjects.append({
                    "id": str(ref),
                    "display": display,
                    "minor": roster.is_minor(ref),
                })
            self._json({"subjects": subjects})

        def _get_resolve(self, qs):
            if not nestor_ok:
                return self._json({"error": "nestor-meaning not installed"}, 503)
            domain = qs.get("domain", "provider")
            surface = qs.get("surface", "")
            if not surface:
                return self._json({"error": "surface is required"}, 400)
            valid = ("provider", "vaccine")
            if domain not in valid:
                return self._json({"error": f"unknown domain {domain!r}"}, 400)
            try:
                store = get_store()
                resolver = nestor_seam.resolver_for(domain, store)
                result = resolver.resolve(surface)
                self._json({"result": result})
            except Exception as exc:
                self._json({"error": str(exc)}, 500)

        def _get_decisions(self):
            if not nestor_ok:
                return self._json({"decisions": []})
            try:
                store = get_store()
                dm = nestor_seam.decisions_for("care", store)
                decisions = dm.all_decisions()
                self._json({"decisions": [
                    {"question": d.get("source_text", "?"),
                     "commitment": d.get("target_text", "?"),
                     "status": d.get("status", "draft")}
                    for d in decisions
                ]})
            except Exception as exc:
                self._json({"decisions": [], "error": str(exc)})

        # ── POST ──────────────────────────────────────────────────────

        def do_POST(self):
            p = urllib.parse.urlparse(self.path).path
            body = self._body()

            if p == "/api/extract":
                return self._post_extract(body)
            if p == "/api/store":
                return self._post_store(body)
            if p == "/api/roster":
                return self._post_roster(body)
            self.send_error(404)

        def _post_extract(self, body):
            text = body.get("text", "")
            items = extract(text)
            self._json({"items": [
                {"kind": e.kind, "text": e.text, "value": e.value,
                 "start": e.start, "end": e.end, "field": e.field}
                for e in items
            ]})

        def _post_store(self, body):
            field = body.get("field", "")
            value = body.get("value", "")

            if field not in FIELDS:
                return self._json(
                    {"ok": False, "error": f"unknown field {field!r}"}, 400)

            rung = FIELDS[field]
            derived = _derived(field) if rung.value in ("L3", "L4") else None
            item = Classified(rung, value, derived)
            item_id = f"intake-{field}-{hash(value) & 0xFFFFFFFF:08x}"
            sidecar.put(MATTER, field, item_id, item, overwrite=True)

            if field == "provider" and nestor_ok:
                try:
                    store = get_store()
                    resolver = nestor_seam.resolver_for("provider", store)
                    resolver.propose(value, value, reason=f"entered as {field}")
                except Exception:
                    pass
            elif field == "vaccine" and nestor_ok:
                try:
                    store = get_store()
                    resolver = nestor_seam.resolver_for("vaccine", store)
                    resolver.propose(value, value, reason=f"entered as {field}")
                except Exception:
                    pass

            self._json({"ok": True, "rung": rung.value})

        def _post_roster(self, body):
            name = body.get("name", "").strip()
            minor = body.get("minor", False)
            if not name:
                return self._json({"ok": False, "error": "name is required"}, 400)
            try:
                ref = roster.add(name=name, minor=minor)
                self._json({"ok": True, "id": str(ref)})
            except Exception as exc:
                self._json({"ok": False, "error": str(exc)}, 500)

    srv = http.server.HTTPServer((host, port), _H)
    url = f"http://{host}:{port}"
    print(f"  homestead-health ui: {url}")
    print(f"  press Ctrl+C to stop")

    try:
        webbrowser.open(url)
    except Exception:
        pass

    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
        print("\n  stopped")
