"""Sinh trang web dashboard tu-dong-goi tu samples/ -> viewer/index.html.

Chay:  python tools/gen_viewer.py   (sau gen_samples + gen_fhir)
Trang web nhung san du lieu 10 thiet bi (MQTT + FHIR + ket qua validate +
danh sach [CAN XAC MINH]) -> mo bang double-click, khong can server.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gateway import devices as reg          # noqa: E402
from gateway import validator               # noqa: E402
from gateway.publisher_mqtt import build_topic  # noqa: E402

MQTT_DIR = os.path.join(ROOT, "samples", "mqtt")
FHIR_DIR = os.path.join(ROOT, "samples", "fhir")
OUT_DIR = os.path.join(ROOT, "viewer")

ORDER = ["BP-01", "SPO-02", "TMP-07", "WGT-09", "LAB-05",
         "ECG-03", "CAM-04", "ECH-06", "STE-08", "GLU-10"]


def _prefix(device_id: str) -> str:
    return device_id.lower().replace("-", "")


def _code_display_map():
    idx = {}
    for dev in reg.DEVICES.values():
        specs = list(dev.get("measurements", [])) + list(dev.get("components", [])) \
            + list(dev.get("extra", []))
        if "panel" in dev:
            specs.append(dev["panel"])
        if "waveform" in dev:
            specs.append(dev["waveform"])
        for s in specs:
            idx[(s["system"], s["code"])] = s["display"]
    return idx


CODE_DISPLAY = _code_display_map()


def _summary_rows(payload):
    rows = []
    for meas in payload["measurements"]:
        code = meas["code"]
        verify = "[CAN XAC MINH]" in (code.get("display") or "")
        if meas.get("components"):
            for c in meas["components"]:
                cc = c["code"]
                label = CODE_DISPLAY.get((cc["system"], cc["code"]), cc["code"])
                rows.append({"label": label, "value": c["value"],
                             "unit": reg.UCUM_DISPLAY.get(c["unit"], c["unit"]), "verify": False})
        elif meas.get("sampled_data"):
            sd = meas["sampled_data"]
            rows.append({"label": code.get("display", code["code"]),
                         "value": f"{sd.get('frequency_hz','?')} Hz · {sd.get('sample_count','?')} mẫu · lead {sd.get('lead','?')}",
                         "unit": sd.get("unit", ""), "verify": verify})
        elif meas.get("media"):
            md = meas["media"]
            extra = []
            if md.get("duration_sec") is not None:
                extra.append(f"{md['duration_sec']}s")
            if md.get("size_bytes") is not None:
                extra.append(f"{round(md['size_bytes']/1024)} KB")
            if md.get("number_of_instances"):
                extra.append(f"{md['number_of_instances']} ảnh")
            rows.append({"label": code.get("display", code["code"]),
                         "value": md.get("content_type", "") + (" · " + " · ".join(extra) if extra else ""),
                         "unit": "", "verify": verify})
        elif meas.get("value") is not None:
            rows.append({"label": code.get("display", code["code"]),
                         "value": meas["value"],
                         "unit": reg.UCUM_DISPLAY.get(meas.get("unit"), meas.get("unit", "")),
                         "verify": verify})
    return rows


def _verify_count(dev):
    n = 0
    for v in dev.values():
        if isinstance(v, dict) and v.get("verify"):
            n += 1
        elif isinstance(v, list):
            n += sum(1 for it in v if isinstance(it, dict) and it.get("verify"))
    return n


def _verify_items():
    items = []
    for did in ORDER:
        dev = reg.DEVICES[did]

        def add(where, disp):
            items.append({"device": did, "where": where, "what": disp})
        if dev.get("snomed_type", {}).get("verify"):
            add("Device.type (SNOMED) + manufacturer", dev["snomed_type"]["display"])
        for s in dev.get("measurements", []) + dev.get("components", []) + dev.get("extra", []):
            if s.get("verify"):
                add("mã chỉ số", s["display"])
        if dev.get("waveform", {}).get("verify"):
            add("mã waveform", dev["waveform"]["display"])
        if dev.get("report", {}).get("verify"):
            add("mã panel/report (DiagnosticReport)", dev["report"]["display"])
        if dev.get("media", {}).get("code", {}).get("verify"):
            add("mã media", dev["media"]["code"]["display"])
        if dev.get("media", {}).get("body_site", {}).get("verify"):
            add("body_site", dev["media"]["body_site"]["text"])
        if dev.get("meal_context", {}).get("verify"):
            add("ngữ cảnh bữa ăn", dev["meal_context"]["text"])
    return items


def build_data():
    devices = []
    for did in ORDER:
        pfx = _prefix(did)
        with open(os.path.join(MQTT_DIR, f"{pfx}.json"), encoding="utf-8") as f:
            payload = json.load(f)
        with open(os.path.join(FHIR_DIR, f"{pfx}.bundle.json"), encoding="utf-8") as f:
            bundle = json.load(f)
        errs = validator.validate(payload)
        res_count = {}
        for e in bundle["entry"]:
            rt = e["resource"]["resourceType"]
            res_count[rt] = res_count.get(rt, 0) + 1
        dev = reg.DEVICES[did]
        devices.append({
            "device_id": did,
            "device_type": payload["device"]["device_type"],
            "connection": payload["device"]["connection"],
            "serial": payload["device"].get("serial_number", ""),
            "mac": payload["device"].get("mac_address", ""),
            "device_class": payload["device"]["device_class"],
            "ble_profile": dev.get("ble_profile", ""),
            "message_type": payload["message_type"],
            "topic": build_topic(payload["message_type"], did),
            "sequence_no": payload.get("sequence_no"),
            "measured_at": payload["timestamps"]["measured_at"],
            "valid": not errs,
            "errors": errs,
            "verify_count": _verify_count(dev),
            "summary": _summary_rows(payload),
            "fhir_resources": res_count,
            "mqtt": payload,
            "fhir": bundle,
        })
    return {
        "generated_at": "2026-10-20",
        "clinic_id": reg.CLINIC_ID,
        "gateway_id": reg.GATEWAY_ID,
        "patient_id": reg.PATIENT_ID,
        "encounter_id": reg.ENCOUNTER_ID,
        "schema_version": "2.1",
        "devices": devices,
        "verify_items": _verify_items(),
    }


# =====================================================================
# HTML TEMPLATE (tu dong goi, du lieu nhung o <script type=application/json>)
# =====================================================================
HTML = r"""<title>Medical Gateway Contract</title>
<meta name="claude:viewport-fit-sides" content="cover">
<meta name="description" content="Dashboard 10 thiet bi IoT y te - Canonical v2.1 -> FHIR R4">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
/* Layout: dashboard lam sang - header dinh, hang tile tong quan, luoi the thiet bi, drawer chi tiet JSON */
:root{
  --bg:#eef2f6; --surface:#ffffff; --surface-2:#f1f5f9; --border:#d5dee7;
  --fg:#0e1b24; --muted:#5a6c7a; --accent:#0e7c86; --accent-weak:#d2ebee;
  --good:#1f8a4c; --good-weak:#dcf0e4; --warn:#9a5b06; --warn-weak:#f6e8d2;
  --crit:#c0352f;
  --mono:"IBM Plex Mono",ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;
  --sans:"IBM Plex Sans",system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
  --radius:12px; --shadow:0 1px 2px rgba(16,30,40,.06),0 4px 16px rgba(16,30,40,.05);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0b141b; --surface:#111d26; --surface-2:#17242e; --border:#243541;
  --fg:#e7eff5; --muted:#92a6b4; --accent:#43bac6; --accent-weak:#113037;
  --good:#4fcc82; --good-weak:#133325; --warn:#e3a94f; --warn-weak:#352911;
  --crit:#eb6b63; color-scheme:dark;
}}
:root[data-theme="dark"]{
  --bg:#0b141b; --surface:#111d26; --surface-2:#17242e; --border:#243541;
  --fg:#e7eff5; --muted:#92a6b4; --accent:#43bac6; --accent-weak:#113037;
  --good:#4fcc82; --good-weak:#133325; --warn:#e3a94f; --warn-weak:#352911;
  --crit:#eb6b63; color-scheme:dark;
}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font-family:var(--sans);line-height:1.5;margin:0}
body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);z-index:20;background:var(--surface)}
.wrap{padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));max-width:1180px;margin:0 auto}
a{color:var(--accent)}
h1,h2,h3{text-wrap:balance;margin:0}
.mono{font-family:var(--mono)}
.tnum{font-variant-numeric:tabular-nums}

/* Header dinh */
header{position:sticky;top:env(safe-area-inset-top,0px);z-index:15;background:var(--surface);border-bottom:1px solid var(--border)}
.head-in{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding-block:14px}
.brand{display:flex;flex-direction:column;gap:2px;min-width:0}
.brand h1{font-size:1.15rem;font-weight:700;letter-spacing:-.01em}
.brand .sub{color:var(--muted);font-size:.8rem}
.head-meta{margin-left:auto;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.kv{font-size:.72rem;color:var(--muted);line-height:1.3}
.kv b{display:block;color:var(--fg);font-size:.82rem;font-weight:600}
.toggle{appearance:none;border:1px solid var(--border);background:var(--surface-2);color:var(--fg);
  border-radius:8px;padding:7px 11px;font:inherit;font-size:.8rem;cursor:pointer}
.toggle:hover{border-color:var(--accent)}

/* Tiles tong quan */
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:18px}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px;box-shadow:var(--shadow)}
.tile .n{font-size:1.9rem;font-weight:700;letter-spacing:-.02em}
.tile .l{color:var(--muted);font-size:.76rem;margin-top:2px}
.tile.ok .n{color:var(--good)} .tile.warn .n{color:var(--warn)}

/* Filter */
.filters{display:flex;gap:8px;flex-wrap:wrap;margin:20px 0 6px}
.chip{appearance:none;border:1px solid var(--border);background:var(--surface);color:var(--muted);
  border-radius:999px;padding:6px 13px;font:inherit;font-size:.78rem;cursor:pointer}
.chip[aria-pressed="true"]{background:var(--accent-weak);color:var(--accent);border-color:var(--accent);font-weight:600}

/* Luoi the thiet bi */
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px;margin:14px 0 40px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);
  box-shadow:var(--shadow);display:flex;flex-direction:column;overflow:hidden}
.card-h{display:flex;align-items:flex-start;gap:10px;padding:14px 16px 10px}
.card-h .id{font-family:var(--mono);font-weight:600;font-size:1rem}
.card-h .ty{color:var(--muted);font-size:.76rem;margin-top:1px}
.pill{margin-left:auto;display:inline-flex;align-items:center;gap:5px;font-size:.7rem;font-weight:600;
  padding:3px 9px;border-radius:999px;white-space:nowrap}
.pill.ok{background:var(--good-weak);color:var(--good)}
.pill.warn{background:var(--warn-weak);color:var(--warn)}
.dot{width:6px;height:6px;border-radius:50%;background:currentColor}
.mtype{font-family:var(--mono);font-size:.68rem;color:var(--accent);background:var(--accent-weak);
  padding:2px 7px;border-radius:6px;display:inline-block;margin:0 16px}
.rows{padding:10px 16px 4px;display:flex;flex-direction:column;gap:7px;min-width:0}
.row{display:flex;align-items:baseline;gap:10px;font-size:.84rem}
.row .lab{color:var(--muted);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.row .val{margin-left:auto;font-weight:600;font-family:var(--mono);text-align:right}
.row .val .u{color:var(--muted);font-weight:400;font-size:.8em;margin-left:3px}
.row.vf .val::after{content:"⚠";color:var(--warn);margin-left:6px;font-size:.8em}
.topic{margin:8px 16px 0;font-family:var(--mono);font-size:.68rem;color:var(--muted);
  background:var(--surface-2);border-radius:7px;padding:7px 9px;overflow-x:auto;white-space:nowrap}
.card-f{display:flex;gap:8px;padding:12px 16px 14px;margin-top:auto}
.btn{flex:1;appearance:none;border:1px solid var(--border);background:var(--surface-2);color:var(--fg);
  border-radius:8px;padding:8px;font:inherit;font-size:.78rem;font-weight:500;cursor:pointer}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.res{display:flex;gap:6px;flex-wrap:wrap;padding:0 16px 12px}
.res span{font-size:.66rem;color:var(--muted);background:var(--surface-2);border:1px solid var(--border);
  border-radius:6px;padding:2px 6px;font-family:var(--mono)}

/* Verify section */
.section-title{font-size:1rem;font-weight:700;margin:14px 0 4px;display:flex;align-items:center;gap:8px}
.section-title .c{font-size:.72rem;font-weight:600;color:var(--warn);background:var(--warn-weak);padding:2px 8px;border-radius:999px}
.verify-note{color:var(--muted);font-size:.82rem;margin:0 0 12px;max-width:68ch}
.vtable{width:100%;border-collapse:collapse;font-size:.82rem;margin-bottom:40px;
  background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
.vtable th,.vtable td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--border);vertical-align:top}
.vtable th{background:var(--surface-2);font-size:.72rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);font-weight:600}
.vtable tr:last-child td{border-bottom:none}
.vtable .did{font-family:var(--mono);font-weight:600;white-space:nowrap}

/* Drawer */
.overlay{position:fixed;inset:0;background:rgba(6,14,20,.55);z-index:30;display:none;
  padding:max(16px,env(safe-area-inset-top,0px)) max(12px,env(safe-area-inset-right,0px)) max(12px,env(safe-area-inset-bottom,0px)) max(12px,env(safe-area-inset-left,0px))}
.overlay[aria-hidden="false"]{display:flex;justify-content:center;align-items:flex-start}
.modal{background:var(--surface);border:1px solid var(--border);border-radius:14px;max-width:860px;width:100%;
  max-height:100%;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.4)}
.modal-h{display:flex;align-items:center;gap:12px;padding:14px 16px;border-bottom:1px solid var(--border)}
.modal-h .id{font-family:var(--mono);font-weight:600}
.modal-h .x{margin-left:auto;appearance:none;border:1px solid var(--border);background:var(--surface-2);
  color:var(--fg);border-radius:8px;width:32px;height:32px;cursor:pointer;font-size:1rem}
.tabs{display:flex;gap:4px;padding:10px 16px 0}
.tab{appearance:none;border:none;background:none;color:var(--muted);font:inherit;font-size:.82rem;font-weight:600;
  padding:8px 12px;border-radius:8px 8px 0 0;cursor:pointer;border-bottom:2px solid transparent}
.tab[aria-selected="true"]{color:var(--accent);border-bottom-color:var(--accent)}
.code{margin:0;padding:16px;overflow:auto;font-family:var(--mono);font-size:.78rem;line-height:1.55;flex:1;
  background:var(--surface-2);white-space:pre;tab-size:2}
.tok-key{color:var(--accent)} .tok-str{color:var(--good)} .tok-num{color:var(--warn)}
.tok-bool{color:var(--crit)} .tok-null{color:var(--muted)}
footer{color:var(--muted);font-size:.74rem;padding:24px 0 40px;border-top:1px solid var(--border)}

@media (max-width:720px){.tiles{grid-template-columns:repeat(2,1fr)}.head-meta{width:100%;margin-left:0}}
@media (max-width:420px){.grid{grid-template-columns:1fr}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>

<header><div class="wrap head-in">
  <div class="brand">
    <h1>Medical Gateway — Data Contract</h1>
    <span class="sub">Canonical v<span id="sv"></span> → FHIR R4 · MQTT over TLS</span>
  </div>
  <div class="head-meta">
    <div class="kv">Clinic<b class="mono" id="clinic"></b></div>
    <div class="kv">Gateway<b class="mono" id="gw"></b></div>
    <div class="kv">Patient<b class="mono" id="pid"></b></div>
    <button class="toggle" id="theme" type="button">◐ Giao diện</button>
  </div>
</div></header>

<main class="wrap">
  <div class="tiles" id="tiles"></div>
  <div class="filters" id="filters"></div>
  <div class="grid" id="grid"></div>

  <h2 class="section-title">Cần xác minh trước khi chạy dữ liệu thật <span class="c" id="vcount"></span></h2>
  <p class="verify-note">Các mã dưới đây chưa được kiểm chứng (hiển thị kèm ⚠ và hậu tố <span class="mono">[CAN XAC MINH]</span>). Không dùng với bệnh nhân thật cho tới khi được lâm sàng / phần cứng / backend chốt.</p>
  <table class="vtable"><thead><tr><th>Thiết bị</th><th>Hạng mục</th><th>Giá trị tạm</th></tr></thead>
    <tbody id="vbody"></tbody></table>

  <footer class="wrap">Sinh tự động từ <span class="mono">samples/mqtt</span> + <span class="mono">samples/fhir</span> · <span id="gen"></span> · dữ liệu giả lập theo chuẩn thật.</footer>
</main>

<div class="overlay" id="overlay" aria-hidden="true" role="dialog" aria-modal="true" aria-labelledby="m-id">
  <div class="modal">
    <div class="modal-h"><span class="id" id="m-id"></span><span class="mtype" id="m-type" style="margin:0"></span>
      <button class="x" id="m-close" type="button" aria-label="Đóng">×</button></div>
    <div class="tabs" role="tablist">
      <button class="tab" role="tab" data-tab="summary" aria-selected="true">Chỉ số</button>
      <button class="tab" role="tab" data-tab="mqtt" aria-selected="false">MQTT payload</button>
      <button class="tab" role="tab" data-tab="fhir" aria-selected="false">FHIR Bundle</button>
    </div>
    <pre class="code" id="m-body"></pre>
  </div>
</div>

<script type="application/json" id="contract-data">__DATA__</script>
<script>
"use strict";
const DATA = JSON.parse(document.getElementById("contract-data").textContent);
const $ = s => document.querySelector(s);
const el = (t, c, txt) => { const e = document.createElement(t); if(c) e.className=c; if(txt!=null) e.textContent=txt; return e; };

// --- Header meta ---
$("#sv").textContent = DATA.schema_version;
$("#clinic").textContent = DATA.clinic_id;
$("#gw").textContent = DATA.gateway_id;
$("#pid").textContent = DATA.patient_id;
$("#gen").textContent = DATA.generated_at;

// --- Theme toggle (localStorage, co try/catch) ---
(function(){
  let saved=null; try{saved=localStorage.getItem("mgw-theme");}catch(e){}
  if(saved) document.documentElement.setAttribute("data-theme",saved);
  $("#theme").addEventListener("click",()=>{
    const cur=document.documentElement.getAttribute("data-theme");
    const prefDark=matchMedia("(prefers-color-scheme:dark)").matches;
    const next=(cur==="dark"||(!cur&&prefDark))?"light":"dark";
    document.documentElement.setAttribute("data-theme",next);
    try{localStorage.setItem("mgw-theme",next);}catch(e){}
  });
})();

// --- Tiles tong quan ---
const total=DATA.devices.length;
const okCount=DATA.devices.filter(d=>d.valid).length;
const mtypes=new Set(DATA.devices.map(d=>d.message_type));
const tiles=[
  {n:total,l:"thiết bị IoT",cls:""},
  {n:okCount+"/"+total,l:"payload hợp lệ (schema+range+UCUM)",cls:okCount===total?"ok":"warn"},
  {n:mtypes.size,l:"loại message_type",cls:""},
  {n:DATA.verify_items.length,l:"mục [CẦN XÁC MINH]",cls:"warn"},
];
tiles.forEach(t=>{const d=el("div","tile "+t.cls);d.append(el("div","n",String(t.n)),el("div","l",t.l));$("#tiles").append(d);});

// --- Filters theo message_type ---
let active="all";
const types=["all",...mtypes];
types.forEach(t=>{
  const b=el("button","chip",t==="all"?"Tất cả":t);b.type="button";
  b.setAttribute("aria-pressed",t==="all"?"true":"false");
  b.addEventListener("click",()=>{active=t;[...$("#filters").children].forEach(c=>c.setAttribute("aria-pressed",c===b?"true":"false"));render();});
  $("#filters").append(b);
});

// --- The thiet bi ---
function fmtVal(v){return typeof v==="number"?new Intl.NumberFormat("en-US").format(v):v;}
function render(){
  const g=$("#grid");g.innerHTML="";
  DATA.devices.filter(d=>active==="all"||d.message_type===active).forEach(d=>{
    const c=el("div","card");
    // header
    const h=el("div","card-h");
    const idbox=el("div");idbox.append(el("div","id",d.device_id),el("div","ty",d.device_type+" · "+d.connection.toUpperCase()));
    const pill=el("span","pill "+(d.valid?"ok":"warn"));
    pill.append(el("span","dot"),document.createTextNode(d.valid?"hợp lệ":"lỗi"));
    h.append(idbox,pill);
    c.append(h, Object.assign(el("span","mtype",d.message_type),{}));
    // rows
    const rows=el("div","rows");
    d.summary.forEach(r=>{
      const row=el("div","row"+(r.verify?" vf":""));
      row.append(el("div","lab",r.label));
      const val=el("div","val");val.append(document.createTextNode(fmtVal(r.value)));
      if(r.unit) val.append(Object.assign(el("span","u"),{textContent:r.unit}));
      row.append(val);rows.append(row);
    });
    c.append(rows);
    // topic
    c.append(Object.assign(el("div","topic"),{textContent:d.topic}));
    // fhir resources
    const res=el("div","res");
    Object.entries(d.fhir_resources).forEach(([k,v])=>res.append(el("span",null,v>1?`${k}×${v}`:k)));
    c.append(res);
    // footer buttons
    const f=el("div","card-f");
    const b1=el("button","btn","MQTT payload");b1.type="button";b1.onclick=()=>openModal(d,"mqtt");
    const b2=el("button","btn","FHIR Bundle");b2.type="button";b2.onclick=()=>openModal(d,"fhir");
    f.append(b1,b2);c.append(f);
    c.style.cursor="default";
    g.append(c);
  });
}

// --- Verify table ---
$("#vcount").textContent=DATA.verify_items.length+" mục";
DATA.verify_items.forEach(it=>{
  const tr=el("tr");
  tr.append(Object.assign(el("td","did"),{textContent:it.device}),el("td",null,it.where),
            Object.assign(el("td","mono"),{textContent:it.what}));
  $("#vbody").append(tr);
});

// --- Modal + JSON highlight ---
let cur=null;
function hl(obj){
  const s=JSON.stringify(obj,null,2);
  return s.replace(/&/g,"&amp;").replace(/</g,"&lt;")
    .replace(/"(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?/g,
      m=>{let cls="tok-num";
        if(/^"/.test(m)) cls=/:$/.test(m)?"tok-key":"tok-str";
        else if(/true|false/.test(m)) cls="tok-bool";
        else if(/null/.test(m)) cls="tok-null";
        return `<span class="${cls}">${m}</span>`;});
}
function showTab(t){
  [...document.querySelectorAll(".tab")].forEach(b=>b.setAttribute("aria-selected",b.dataset.tab===t?"true":"false"));
  if(!cur)return;
  if(t==="summary"){
    const lines=cur.summary.map(r=>`${r.label}: ${fmtVal(r.value)} ${r.unit}${r.verify?"  [CAN XAC MINH]":""}`).join("\n");
    $("#m-body").innerHTML=`<span class="tok-key">Thiết bị</span> ${cur.device_id} — ${cur.device_type}\n`
      +`<span class="tok-key">Serial</span> ${cur.serial}   <span class="tok-key">MAC</span> ${cur.mac}\n`
      +`<span class="tok-key">BLE/Profile</span> ${cur.ble_profile}\n`
      +`<span class="tok-key">Đo lúc</span> ${cur.measured_at}   <span class="tok-key">seq</span> ${cur.sequence_no}\n`
      +`<span class="tok-key">Topic</span> ${cur.topic}\n\n`+lines
      +(cur.valid?`\n\n<span class="tok-str">✓ Hợp lệ: schema + khoảng hợp lệ KT + UCUM</span>`
                 :`\n\n<span class="tok-bool">✗ Lỗi: ${cur.errors.join("; ")}</span>`);
  }else{
    $("#m-body").innerHTML=hl(t==="mqtt"?cur.mqtt:cur.fhir);
  }
}
function openModal(d,tab){cur=d;$("#m-id").textContent=d.device_id;$("#m-type").textContent=d.message_type;
  $("#overlay").setAttribute("aria-hidden","false");showTab(tab);}
function closeModal(){$("#overlay").setAttribute("aria-hidden","true");cur=null;}
document.querySelectorAll(".tab").forEach(b=>b.addEventListener("click",()=>showTab(b.dataset.tab)));
$("#m-close").addEventListener("click",closeModal);
$("#overlay").addEventListener("click",e=>{if(e.target===$("#overlay"))closeModal();});
document.addEventListener("keydown",e=>{if(e.key==="Escape")closeModal();});

render();
</script>
"""


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    data = build_data()
    data_json = json.dumps(data, ensure_ascii=False)
    html = HTML.replace("__DATA__", data_json)
    out = os.path.join(OUT_DIR, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    kb = round(len(html.encode("utf-8")) / 1024)
    print(f"  wrote {out} ({kb} KB, {len(data['devices'])} thiet bi)")


if __name__ == "__main__":
    main()
