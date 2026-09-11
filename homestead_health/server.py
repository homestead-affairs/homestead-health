"""Localhost web UI for homestead-health — enrolment, dose entry and records.

Serves on 127.0.0.1 only.  All HTML/CSS/JS is embedded (no external files,
no CDN).  Imports of ``http.server`` and ``urllib.parse`` are **local** to
``build_server()`` — this module's top level touches nothing network-shaped,
so ``import homestead_health`` stays import-pure.

**This is where a household enters its own information.** The *Roster* tab
enrols members (opaque ids minted by the roster; a minor's name at L4). The
*Records* tab is a dose form — subject, vaccine, dose date, and the optional
provider, lot, source, notes and next-due — stored whole through
``doses.add_dose`` at the pack's rungs, never a rung chosen here; beneath it,
the subject's doses as the list pane shows them (a dose is L4: its derived
form, with the L2 next-due date beside it) and, on a click, the detail pane
where the dose renders. The *Intake* tab is the other way in: paste a clinic
card and each extracted item fills the form with one click.

**Chokepoint**: this module never accesses ``.payload``.  Everything reaches
the browser as ``Served.value`` from ``serve()``, or as a reference.  Entity
and decision data come through Nestor's public API — optional, and absent
without the ``entity`` extra.

``build_server()`` returns the bound ``HTTPServer`` without serving, so a
test can drive the real handlers on an ephemeral port; ``serve()`` is the
operator's door and blocks until Ctrl+C.
"""
from __future__ import annotations

__all__ = ["build_server", "serve"]

#: The most a request body may be, in bytes. A localhost UI still reads from a
#: socket, and an unbounded `rfile.read(n)` is an unbounded allocation decided by
#: whatever sent the header. One mebibyte is far more than a dose form, a roster
#: name or a pasted clinic card; past it the answer is 413, before a byte is read.
_MAX_BODY = 1024 * 1024

#: How long a refused request's leftover bytes get to arrive before the
#: connection is closed anyway.  Short: the client sent them already or never
#: will; this waits for a segment in flight, not for a slow sender.
DRAIN_TIMEOUT_SECONDS = 0.2


def _drain(sock, *, limit=_MAX_BODY, timeout=DRAIN_TIMEOUT_SECONDS):
    """Read and discard whatever the client already sent of a body the
    handler refused to read, so the socket closes with an empty receive
    buffer.

    Closing a socket that still holds unread bytes makes the kernel answer
    with a reset instead of an orderly close, and on Windows a reset discards
    data the peer has received but not yet read — the 400 the client was
    about to parse (``WinError 10053``, seen on the law module's release PR).
    ``_discard`` above covers the oversized case, where the length is known;
    this covers the refusals where it is not.  The bytes are bounded by
    ``limit`` and the wait by ``timeout``; a slow or silent client is not
    waited for, and nothing read here is looked at (I-15).  Returns the count
    discarded.
    """
    discarded = 0
    try:
        sock.settimeout(timeout)
        while discarded < limit:
            chunk = sock.recv(min(65536, limit - discarded))
            if not chunk:
                break
            discarded += len(chunk)
    except OSError:
        pass
    return discarded


class _BadBody(Exception):
    """A request body this server answers about instead of dropping the socket.

    Carries the status and the **fixed** sentence to send. Fixed on purpose: a
    body refusal says what was wrong with the *envelope* (not JSON, not an
    object, too large, bad length) and never echoes the bytes back, so a refusal
    cannot become a reflector for whatever was posted (I-15's shape at the
    boundary: a message may name a field, never carry a value).
    """

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


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
.why{font-size:12px;color:var(--text-2);margin-top:6px}
.today{font-size:15px;color:var(--accent);margin-bottom:16px;min-height:1em}
.qi{display:flex;align-items:center;gap:12px;padding:10px 16px;background:var(--surface);
  border:1px solid var(--border);border-radius:var(--r);margin-bottom:8px;
  box-shadow:0 1px 3px rgba(0,0,0,.08)}
.rw{cursor:pointer}.rw:hover{background:var(--accent-l)}
.rb{font-size:12px;padding:2px 6px;border-radius:4px;font-weight:500}
.r-L2{background:#f0eeec;color:#888}.r-L3{background:#f0eeec;color:#333}
.r-L4{background:var(--warn-l);color:var(--warn)}
.rk{font-size:13px;color:var(--text-2);min-width:90px}
.qs{flex:1;font-size:14px}.qn{font-size:13px;color:var(--text-2)}
.dt{padding:14px 16px;background:var(--accent-l);border-radius:var(--r);margin-top:8px}
.dt div{font-size:14px}
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
  <button class="tb on" onclick="show('records',this)">Records</button>
  <button class="tb" onclick="show('roster',this)">Roster</button>
  <button class="tb" onclick="show('intake',this)">Intake</button>
  <button class="tb" onclick="show('entities',this)">Entities</button>
  <button class="tb" onclick="show('decisions',this)">Decisions</button>
</nav>
<main>

<section id="t-records" class="tab on">
  <div id="today" class="today"></div>
  <h2>Record a dose</h2>
  <div class="card">
    <div class="rf">
      <select id="dsubject" onchange="loadDoses()"></select>
      <input id="dvaccine" placeholder="Vaccine (e.g. MMR)" style="max-width:180px">
      <input id="ddate" placeholder="Dose date YYYY-MM-DD" style="max-width:190px">
      <input id="dnext" placeholder="Next due YYYY-MM-DD" style="max-width:190px">
    </div>
    <div class="rf">
      <input id="dprovider" placeholder="Provider">
      <input id="dlot" placeholder="Lot number" style="max-width:160px">
      <input id="dsource" placeholder="Source (clinic card, portal, memory)">
    </div>
    <div class="rf">
      <input id="dnotes" placeholder="Notes" onkeydown="if(event.key==='Enter')storeDose()">
      <button class="btn bg" onclick="storeDose()">Record dose</button>
    </div>
    <div class="why">A dose is stored at the pack's rungs: the vaccine is L4 (a medical act on a person), so the list below shows only that a dose is on file &#8212; open it to read it. No rung is chosen here.</div>
    <div id="dmsg"></div>
  </div>

  <h2>On file</h2>
  <div id="dlist"></div>
  <div id="ddetail"></div>
</section>

<section id="t-intake" class="tab">
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
  if(name==='records'){loadSubjects().then(loadDoses);}
  if(name==='roster') loadRoster();
  if(name==='decisions') loadDecisions();
}

function loadSubjects() {
  return fetch('/api/roster').then(function(r){return r.json()}).then(function(data){
    var sel=document.getElementById('dsubject'); var prev=sel.value; sel.innerHTML='';
    (data.subjects||[]).forEach(function(s){
      var o=document.createElement('option'); o.value=s.id; o.textContent=s.id+' \u00b7 '+s.display; sel.appendChild(o);
    });
    if(prev) sel.value=prev;
    if(!data.subjects||!data.subjects.length){
      document.getElementById('dlist').innerHTML='<p class="empty">Enrol a household member on the Roster tab first.</p>';
    }
  });
}

function loadToday() {
  fetch('/api/today').then(function(r){return r.json()}).then(function(data){
    document.getElementById('today').textContent=data.line||'';
  });
}

function storeDose() {
  var msg=document.getElementById('dmsg');
  var body={subject:document.getElementById('dsubject').value,
    vaccine:document.getElementById('dvaccine').value.trim(),
    dose_date:document.getElementById('ddate').value.trim(),
    next_due:document.getElementById('dnext').value.trim()||null,
    provider:document.getElementById('dprovider').value.trim()||null,
    lot_number:document.getElementById('dlot').value.trim()||null,
    source:document.getElementById('dsource').value.trim()||null,
    notes:document.getElementById('dnotes').value.trim()||null};
  if(!body.subject){msg.innerHTML='<span class="sm s-err">Enrol a household member first</span>';return;}
  fetch('/api/dose',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)})
  .then(function(r){return r.json()}).then(function(data){
    if(data.ok){
      msg.innerHTML='<span class="sm s-ok">Recorded '+esc(data.id)+' ('+data.rung+')</span>';
      ['dvaccine','ddate','dnext','dprovider','dlot','dsource','dnotes'].forEach(function(id){document.getElementById(id).value='';});
      loadDoses(); loadToday();
    } else {msg.innerHTML='<span class="sm s-err">'+esc(data.error||'Failed')+'</span>';}
  }).catch(function(){msg.innerHTML='<span class="sm s-err">Error</span>';});
}

function loadDoses() {
  var subject=document.getElementById('dsubject').value;
  var div=document.getElementById('dlist');
  document.getElementById('ddetail').innerHTML='';
  loadToday();
  if(!subject) return;
  fetch('/api/doses?subject='+encodeURIComponent(subject)).then(function(r){return r.json()}).then(function(data){
    if(!data.doses||!data.doses.length){
      div.innerHTML='<p class="empty">No doses on file for '+esc(subject)+' yet.</p>';return;}
    var html='';
    data.doses.forEach(function(d){
      html+='<div class="qi rw" onclick="openDose(\''+esc(d.id)+'\')">'
        +'<span class="rb r-'+d.rung+'">'+d.rung+'</span>'
        +'<span class="rk">'+esc(d.id)+'</span>'
        +'<span class="qs">'+esc(d.text)+'</span>'
        +(d.next_due?'<span class="qn">next due '+esc(d.next_due)+'</span>':'')
        +'</div>';
    });
    div.innerHTML=html;
  }).catch(function(){div.innerHTML='<p class="sm s-err">Failed to load doses</p>';});
}

function openDose(id) {
  var div=document.getElementById('ddetail');
  fetch('/api/dose?id='+encodeURIComponent(id)).then(function(r){return r.json()}).then(function(data){
    if(data.error){div.innerHTML='<p class="sm s-err">'+esc(data.error)+'</p>';return;}
    var html='<div class="dt"><strong>'+esc(id)+'</strong> <span class="rb r-'+data.rung+'">'+data.rung+'</span>';
    if(data.rendered){
      Object.keys(data.fields).forEach(function(k){
        html+='<div><span class="rk">'+esc(k.replace(/_/g,' '))+'</span> '+esc(data.fields[k])+'</div>';
      });
    } else { html+='<div>This record is sealed and is not shown here.</div>'; }
    html+='</div>';
    div.innerHTML=html;
  });
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
      opts='<option value="dvaccine">Vaccine</option>';
    } else if(item.kind==='date'){
      opts='<option value="ddate">Dose date</option><option value="dnext">Next due</option>';
    } else if(item.kind==='provider'){
      opts='<option value="dprovider">Provider</option>';
    } else if(item.kind==='lot'){
      opts='<option value="dlot">Lot number</option>';
    } else {
      opts='<option value="">&#8212;</option>';
    }
    html+='<div class="card" id="c'+i+'"><div class="cr">'
      +'<span class="kb k-'+item.kind+'">'+item.kind+'</span>'
      +'<span class="mt">'+esc(item.text)+'</span>'
      +'<span class="mv">'+esc(item.value)+'</span>'
      +'<select class="fs" id="f'+i+'">'+opts+'</select>'
      +'<button class="btn bg bs" onclick="fillItem('+i+')">Use</button>'
      +'</div></div>';
  });
  div.innerHTML=html;
}

function fillItem(idx) {
  var item=_items[idx];
  var target=document.getElementById('f'+idx).value;
  if(!target) return;
  document.getElementById(target).value=item.value;
  var card=document.getElementById('c'+idx);
  card.classList.add('stored');
  card.innerHTML+='<span class="sm s-ok">Filled into the dose form (Records tab)</span>';
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
loadSubjects().then(loadDoses);
</script>
</body>
</html>
"""


# ── server ────────────────────────────────────────────────────────────────

def build_server(*, host: str = "127.0.0.1", port: int = 8384):
    """Bind the UI's ``HTTPServer`` on ``host:port`` and return it, unserved.

    Everything the handlers need is bound here — the household root, the
    sidecar, the roster, the (optional) Nestor seam — so ``serve()`` and a test
    share one construction. ``port=0`` asks the OS for a free port; read it
    back from ``server.server_address``.
    """
    import datetime as dt
    import http.server
    import json
    import urllib.parse

    from homestead.keep import paths
    from homestead.keep.dates import UnparseableDate
    from homestead.keep.export import ExportRefused
    from homestead.keep.record import Sidecar
    from homestead.keep.rungs import Disposition, Surface, serve as rung_serve

    from homestead_health import doses, nestor_seam
    from homestead_health.intake import extract
    from homestead_health.nestor_store import get_store
    from homestead_health.roster import Roster

    root = paths.home()
    root.mkdir(parents=True, exist_ok=True)
    (root / "keep").mkdir(parents=True, exist_ok=True)

    nestor_ok = nestor_seam.bind(root) is not None

    sidecar = Sidecar()
    roster = Roster(sidecar)

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

        def _discard(self, n):
            """Read and throw away up to `n` bytes, a chunk at a time."""
            while n > 0:
                chunk = self.rfile.read(min(n, 65536))
                if not chunk:
                    return
                n -= len(chunk)

        def _body(self):
            """The request body as a JSON object, or `_BadBody` with the answer.

            Every branch here was a **dropped connection** before the W0 audit:
            a bad `Content-Length` (`int("abc")`), a malformed body
            (`JSONDecodeError`), a body that is JSON but not an object (`[1,2]`,
            then `.get` on a list), and a body of any size at all (three
            megabytes were read into memory and accepted). None of them
            answered; each raised out of `do_POST`, so the operator's browser
            saw a reset and the traceback went to the terminal. A localhost UI
            is still a parser at a socket: it answers, with a status, or it is
            not a door you can reason about.
            """
            raw_length = self.headers.get("Content-Length")
            if raw_length is None:
                return {}
            try:
                n = int(raw_length)
            except (TypeError, ValueError):
                raise _BadBody(400, "Content-Length is not a number")
            if n < 0:
                raise _BadBody(400, "Content-Length is not a number")
            if n > _MAX_BODY:
                # Refused on the *header*, so nothing oversized is ever held in
                # memory — but the declared bytes are still on their way up the
                # socket, and answering into a client that is mid-send gets the
                # answer thrown away. So read them off and discard them, in
                # bounded chunks (memory is the chunk, never the body), up to a
                # hard ceiling past which the sender is not owed a conversation.
                self._discard(min(n, _MAX_BODY * 2))
                raise _BadBody(413, f"a request body is at most {_MAX_BODY} bytes")
            if n == 0:
                return {}
            raw = self.rfile.read(n)
            try:
                body = json.loads(raw)
            except (ValueError, UnicodeDecodeError):
                raise _BadBody(400, "the request body is not JSON")
            if not isinstance(body, dict):
                raise _BadBody(400, "the request body is a JSON object")
            return body

        # ── GET ───────────────────────────────────────────────────────

        def do_GET(self):
            p = urllib.parse.urlparse(self.path)
            qs = dict(urllib.parse.parse_qsl(p.query))

            if p.path == "/":
                return self._html(_PAGE)
            if p.path == "/api/status":
                return self._json({"nestor": nestor_ok, "subjects": len(roster)})
            if p.path == "/api/roster":
                return self._get_roster()
            if p.path == "/api/doses":
                return self._get_doses(qs)
            if p.path == "/api/dose":
                return self._get_dose(qs)
            if p.path == "/api/today":
                return self._get_today(qs)
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

        def _get_doses(self, qs):
            subject = qs.get("subject", "")
            if subject not in roster:
                return self._json({"error": f"{subject!r} is not on the roster"}, 400)
            due_by = {ref.id: rec for ref, rec in doses.next_due_of(sidecar, subject)}
            out = []
            for ref, record in doses.doses_of(sidecar, subject):
                # The list pane: a dose is L4, so this is its derived form —
                # the vaccine and the date never sit beside the subject here.
                # `doses.list_row` is the one place that rule lives, shared with
                # the CLI's `dose list`, and it refuses to print a payload even
                # for a record whose stored rung did not survive as L4.
                row = doses.list_row(record)
                if row is None:
                    continue
                rung, text = row
                entry = {"id": ref.id, "rung": rung.value, "text": text}
                nxt = due_by.get(ref.id)
                if nxt is not None:
                    nxt_text = doses.next_due_text(nxt)
                    if nxt_text is not None:
                        entry["next_due"] = nxt_text
                out.append(entry)
            self._json({"doses": out})

        def _get_dose(self, qs):
            try:
                ref = doses.dose_ref(qs.get("id", ""))
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
            match = [rec for r, rec in doses.doses_of(sidecar, ref.subject) if r.id == ref.id]
            if not match:
                return self._json({"error": "no such dose"}, 404)
            # The detail pane: opening it is the purpose declaration, so the L4
            # dose renders; L5 would still be refused (I-13).
            served = rung_serve(match[0], Surface.S1_DETAIL)
            rendered = served.disposition is Disposition.RENDER
            fields = served.value if rendered and isinstance(served.value, dict) else {}
            self._json({"rung": served.rung.value, "rendered": rendered, "fields": fields})

        def _get_today(self, qs):
            today = qs.get("today") or dt.date.today().isoformat()
            try:
                line = doses.today_line(sidecar, roster, today=today)
            except ValueError as exc:
                return self._json({"error": str(exc)}, 400)
            self._json({"line": line})

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
            try:
                body = self._body()
            except _BadBody as bad:
                # A refused body was not read: drain what arrived before
                # the connection closes, or the close becomes a reset.
                self._json({"ok": False, "error": bad.message}, bad.status)
                self.close_connection = True
                _drain(self.connection)
                return

            if p == "/api/extract":
                return self._post_extract(body)
            if p == "/api/dose":
                return self._post_dose(body)
            if p == "/api/roster":
                return self._post_roster(body)
            self.send_error(404)

        def _post_extract(self, body):
            text = body.get("text", "")
            if not isinstance(text, str):
                return self._json({"error": "text is text"}, 400)
            items = extract(text)
            self._json({"items": [
                {"kind": e.kind, "text": e.text, "value": e.value,
                 "start": e.start, "end": e.end, "field": e.field}
                for e in items
            ]})

        def _post_dose(self, body):
            try:
                ref = doses.add_dose(
                    sidecar, roster,
                    subject=body.get("subject"),
                    vaccine=body.get("vaccine") or "",
                    dose_date=body.get("dose_date") or "",
                    next_due=body.get("next_due"),
                    provider=body.get("provider"),
                    lot_number=body.get("lot_number"),
                    source=body.get("source"),
                    notes=body.get("notes"),
                )
            # `add_dose` refuses in four types and only two were ValueErrors.
            # ExportRefused (a PermissionError — a subject that is not one clean
            # reference segment, e.g. a *name* typed into the id box) and
            # FileExistsError (I-9: a second process took this id between the
            # count and the write) both fell through to the catch-all, which
            # answered 500 — a server fault for an input the operator can fix —
            # and echoed `str(exc)` for *any* exception, so the next exception
            # type to carry a field value would have carried it to the browser.
            except (ValueError, UnparseableDate, ExportRefused) as exc:
                return self._json({"ok": False, "error": str(exc)}, 400)
            except FileExistsError:
                return self._json({"ok": False, "error": (
                    "another writer took that dose id between counting and "
                    "writing. Nothing was stored (I-9) — submit it again."
                )}, 409)
            except Exception:
                # Last resort: a fixed sentence. Whatever went wrong, the
                # operator is not the right reader for its message.
                return self._json({"ok": False, "error": (
                    "the dose was not recorded. Nothing was stored."
                )}, 500)

            provider = (body.get("provider") or "").strip()
            if provider and nestor_ok:
                try:
                    resolver = nestor_seam.resolver_for("provider", get_store())
                    resolver.propose(provider, provider, reason="entered as provider")
                except Exception:
                    pass

            self._json({"ok": True, "id": ref.id, "rung": "L4"})

        def _post_roster(self, body):
            name = body.get("name", "")
            minor = body.get("minor", False)
            # `body.get("name", "").strip()` raised AttributeError on any
            # non-string — `{"name": 5}` dropped the connection with a traceback.
            if not isinstance(name, str):
                return self._json({"ok": False, "error": "name is text"}, 400)
            name = name.strip()
            if not name:
                return self._json({"ok": False, "error": "name is required"}, 400)
            # Minority is not a truthiness question. It IS the name's rung (L4
            # minor, L3 adult), so a non-boolean is refused rather than coerced:
            # `bool("false")` was True — over-protecting, the safe direction, but
            # still not what was sent — and the tempting tightening the other way
            # (`minor is True`) would read the string "true" as an *adult*, which
            # is the fail-open direction `Roster.is_minor` calls catastrophic.
            # Refusing is the only reading that is wrong in neither direction.
            if not isinstance(minor, bool):
                return self._json(
                    {"ok": False, "error": "minor is true or false"}, 400)
            try:
                ref = roster.add(name=name, minor=minor)
                self._json({"ok": True, "id": str(ref)})
            except ValueError as exc:
                self._json({"ok": False, "error": str(exc)}, 400)
            except FileExistsError:
                self._json({"ok": False, "error": (
                    "another writer took that subject id. Nothing was stored "
                    "(I-9) — submit it again."
                )}, 409)
            except Exception:
                self._json({"ok": False, "error": (
                    "the member was not enrolled. Nothing was stored."
                )}, 500)

    return http.server.HTTPServer((host, port), _H)


def serve(*, host: str = "127.0.0.1", port: int = 8384) -> None:
    """Start the UI on localhost, open a browser on it, and block until Ctrl+C."""
    import webbrowser

    srv = build_server(host=host, port=port)
    url = f"http://{host}:{srv.server_address[1]}"
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
