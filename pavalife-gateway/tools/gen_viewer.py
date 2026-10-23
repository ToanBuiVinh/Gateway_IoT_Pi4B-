"""Sinh dashboard PavaLife v2.1 -> pavalife-gateway/viewer/index.html.

Tu dong goi: nhung du lieu 6 thiet bi + device.status + vi du thieu du lieu.
Vitals chay monitor (day 1 diem / 500ms); lab/glucose bieu do thanh; co tab ban tin JSON.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from gateway import registry as reg      # noqa: E402
from gateway import validator            # noqa: E402

SAMPLES = os.path.join(ROOT, "samples")
OUT = os.path.join(ROOT, "viewer")
ORDER = ["blood_pressure", "spo2", "thermometer", "scale", "lab_analyzer", "glucose"]
FILE = {"blood_pressure": "bp", "spo2": "spo2", "thermometer": "temp",
        "scale": "scale", "lab_analyzer": "lab", "glucose": "glu"}


def _rows(msg):
    rows = []
    for m in msg["payload"]["measurements"]:
        q = m.get("quality", {}).get("status")
        if "components" in m:
            for c in m["components"]:
                thr = reg.M.get(c["local_code"], {}).get("thr")
                rows.append({"label": c["code"]["display"], "local_code": c["local_code"],
                             "value": c["value"], "unit": c["unit"]["display"],
                             "min": thr[0] if thr else None, "max": thr[1] if thr else None, "quality": q})
        elif "value" in m:
            thr = reg.M.get(m["local_code"], {}).get("thr")
            rows.append({"label": m["code"]["display"], "local_code": m["local_code"],
                         "value": m["value"], "unit": m["unit"]["display"],
                         "min": thr[0] if thr else None, "max": thr[1] if thr else None, "quality": q})
        else:
            rows.append({"label": m["code"]["display"], "local_code": m["local_code"],
                         "absent": m.get("data_absent_reason"), "quality": q})
    return rows


def build_data():
    devices = []
    for key in ORDER:
        with open(os.path.join(SAMPLES, f"{FILE[key]}.json"), encoding="utf-8") as f:
            msg = json.load(f)
        dev = reg.DEVICES[key]
        kind = "lab" if msg["message_type"] == "observation.lab" else "vitals"
        entry = {
            "device_key": key, "device_id": dev["device_id"], "message_type": msg["message_type"],
            "source_type": msg["source"]["source_type"], "topic": reg.topic_for(msg["message_type"]),
            "sequence_no": msg["sequence_no"], "event_time": msg["event_time"],
            "kind": kind, "valid": not validator.validate(msg),
            "summary": _rows(msg), "msg": msg,
        }
        if kind == "lab":
            entry["specimen"] = msg["payload"]["specimen"]
            entry["report"] = msg["payload"]["report"]
        devices.append(entry)

    # Sieu am (imaging.study) — chi tham chieu DICOM, khong pixel
    with open(os.path.join(SAMPLES, "ultrasound.json"), encoding="utf-8") as f:
        um = json.load(f)
    study = um["payload"]["study"]
    storage = um["payload"]["storage"]
    devices.append({
        "device_key": "ultrasound", "device_id": "US-001", "message_type": "imaging.study",
        "source_type": um["source"]["source_type"], "topic": reg.topic_for("imaging.study"),
        "sequence_no": um["sequence_no"], "event_time": um["event_time"],
        "kind": "imaging", "valid": not validator.validate(um),
        "summary": [
            {"label": "Modality", "value": study["modality"]},
            {"label": "Số ảnh (instances)", "value": study["number_of_instances"]},
            {"label": "Vị trí", "value": study.get("body_site", "—")},
            {"label": "StudyInstanceUID", "value": "…" + study["study_instance_uid"][-16:]},
            {"label": "Lưu trữ", "value": storage["type"]},
        ],
        "wado": storage.get("wado_rs_study"), "msg": um,
    })

    with open(os.path.join(SAMPLES, "device_status.json"), encoding="utf-8") as f:
        ds = json.load(f)
    status = {"device_id": reg.SOURCE_ID, "message_type": "device.status",
              "topic": reg.topic_for("device.status"), "payload": ds["payload"],
              "valid": not validator.validate(ds), "msg": ds}

    absent = []
    for fn in ["bp_absent", "temp_absent"]:
        with open(os.path.join(SAMPLES, f"{fn}.json"), encoding="utf-8") as f:
            am = json.load(f)
        for m in am["payload"]["measurements"]:
            if "data_absent_reason" in m:
                absent.append({"device_id": m["observation_id"].rsplit("-", 2)[0],
                               "label": m["code"]["display"], "reason": m["data_absent_reason"],
                               "quality": m["quality"]})
    return {
        "facility": reg.FACILITY_ID, "gateway_id": reg.GATEWAY_ID, "source_id": reg.SOURCE_ID,
        "broker": reg.BROKER_URL, "schema_version": reg.SCHEMA_VERSION,
        "devices": devices, "status": status, "absent": absent,
    }


HTML = r"""<title>PavaLife Device Contract</title>
<meta name="claude:viewport-fit-sides" content="cover">
<meta name="description" content="Dashboard 6 thiet bi y te PavaLife - Device Data Contract v2.1 (MQTT 5.0/WSS)">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
/* Layout: dashboard - header dinh, tiles, luoi the thiet bi (monitor dong/bars), drawer JSON */
:root{
  --bg:#eef2f6; --surface:#fff; --surface-2:#f1f5f9; --border:#d5dee7;
  --fg:#0e1b24; --muted:#5a6c7a; --accent:#1667c9; --accent-weak:#d9e8fb;
  --good:#1f8a4c; --good-weak:#dcf0e4; --warn:#9a5b06; --warn-weak:#f6e8d2; --crit:#c0352f;
  --mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
  --sans:"IBM Plex Sans",system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
  --radius:12px; --shadow:0 1px 2px rgba(16,30,40,.06),0 4px 16px rgba(16,30,40,.05);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0b141b; --surface:#111d26; --surface-2:#17242e; --border:#243541;
  --fg:#e7eff5; --muted:#92a6b4; --accent:#5aa2f0; --accent-weak:#12304d;
  --good:#4fcc82; --good-weak:#133325; --warn:#e3a94f; --warn-weak:#352911; --crit:#eb6b63; color-scheme:dark;
}}
:root[data-theme="dark"]{
  --bg:#0b141b; --surface:#111d26; --surface-2:#17242e; --border:#243541;
  --fg:#e7eff5; --muted:#92a6b4; --accent:#5aa2f0; --accent-weak:#12304d;
  --good:#4fcc82; --good-weak:#133325; --warn:#e3a94f; --warn-weak:#352911; --crit:#eb6b63; color-scheme:dark;
}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font-family:var(--sans);line-height:1.5;margin:0}
body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);z-index:20;background:var(--surface)}
.wrap{padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));max-width:1180px;margin:0 auto}
h1,h2{text-wrap:balance;margin:0}.mono{font-family:var(--mono)}
header{position:sticky;top:env(safe-area-inset-top,0px);z-index:15;background:var(--surface);border-bottom:1px solid var(--border)}
.head-in{display:flex;align-items:center;gap:16px;flex-wrap:wrap;padding-block:14px}
.brand h1{font-size:1.15rem;font-weight:700;letter-spacing:-.01em}
.brand .sub{color:var(--muted);font-size:.8rem}
.head-meta{margin-left:auto;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
.kv{font-size:.72rem;color:var(--muted)}.kv b{display:block;color:var(--fg);font-size:.8rem;font-weight:600}
.toggle{border:1px solid var(--border);background:var(--surface-2);color:var(--fg);border-radius:8px;padding:7px 11px;font:inherit;font-size:.8rem;cursor:pointer}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:18px}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:14px 16px;box-shadow:var(--shadow)}
.tile .n{font-size:1.9rem;font-weight:700;letter-spacing:-.02em}.tile .l{color:var(--muted);font-size:.76rem;margin-top:2px}
.tile.ok .n{color:var(--good)}
.banner{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:16px 0 0;padding:10px 14px;background:var(--surface);border:1px solid var(--border);border-radius:10px;font-size:.78rem;color:var(--muted)}
.banner .mono{color:var(--fg)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(330px,1fr));gap:14px;margin:16px 0 30px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow);display:flex;flex-direction:column;overflow:hidden;cursor:pointer}
.card-h{display:flex;align-items:flex-start;gap:10px;padding:14px 16px 8px}
.card-h .id{font-family:var(--mono);font-weight:600;font-size:1rem}
.card-h .ty{color:var(--muted);font-size:.74rem;margin-top:1px}
.pill{margin-left:auto;display:inline-flex;align-items:center;gap:5px;font-size:.7rem;font-weight:600;padding:3px 9px;border-radius:999px;white-space:nowrap}
.pill.ok{background:var(--good-weak);color:var(--good)}.pill.warn{background:var(--warn-weak);color:var(--warn)}
.dot{width:6px;height:6px;border-radius:50%;background:currentColor}
.mtype{font-family:var(--mono);font-size:.66rem;color:var(--accent);background:var(--accent-weak);padding:2px 7px;border-radius:6px;display:inline-block;margin:0 16px}
.viz{margin:8px 16px 2px;border:1px solid var(--border);border-radius:9px;overflow:hidden;background:var(--surface-2)}
.viz canvas{display:block;width:100%}
.viz .caption{font-size:.62rem;color:var(--muted);padding:4px 8px;font-family:var(--mono);border-top:1px solid var(--border);background:var(--surface)}
.bars{display:flex;flex-direction:column;gap:9px;padding:12px 16px 4px}
.bar .top{display:flex;justify-content:space-between;align-items:baseline;font-size:.8rem;margin-bottom:3px;gap:8px}
.bar .top .lab{color:var(--muted);min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bar .top .v{font-family:var(--mono);font-weight:600}.bar .top .v .u{color:var(--muted);font-weight:400;font-size:.82em;margin-left:2px}
.bar .track{height:8px;border-radius:999px;background:var(--surface-2);border:1px solid var(--border);overflow:hidden}
.bar .fill{height:100%;background:var(--accent);border-radius:999px}
.bar .rng{display:flex;justify-content:space-between;font-size:.6rem;color:var(--muted);font-family:var(--mono);margin-top:2px}
.rows{padding:8px 16px 2px;display:flex;flex-direction:column;gap:6px}
.row{display:flex;gap:10px;font-size:.82rem}.row .lab{color:var(--muted)}.row .val{margin-left:auto;font-weight:600;font-family:var(--mono)}
.qpill{font-size:.62rem;font-weight:600;padding:1px 6px;border-radius:5px;margin-left:6px}
.q-good{background:var(--good-weak);color:var(--good)}.q-unavailable,.q-suspect{background:var(--warn-weak);color:var(--warn)}
.topic{margin:8px 16px 0;font-family:var(--mono);font-size:.66rem;color:var(--muted);background:var(--surface-2);border-radius:7px;padding:7px 9px;overflow-x:auto;white-space:nowrap}
.labmeta{margin:6px 16px 0;font-size:.7rem;color:var(--muted)}
.dicombox{aspect-ratio:16/10;background:linear-gradient(135deg,#0b1a22,#05272e);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;color:#bfe}
.dicombox .dic-ico{font-family:var(--mono);font-weight:700;font-size:1.3rem;border:2px solid rgba(190,238,255,.5);border-radius:10px;padding:8px 14px}
.dicombox .dic-t{font-size:.66rem;opacity:.8;padding:0 14px;text-align:center}
.wado{margin:6px 16px 0;font-family:var(--mono);font-size:.64rem;color:var(--accent);background:var(--accent-weak);border-radius:7px;padding:6px 9px;overflow-x:auto;white-space:nowrap}
.card-f{display:flex;gap:8px;padding:12px 16px 14px;margin-top:auto}
.btn{flex:1;border:1px solid var(--border);background:var(--surface-2);color:var(--fg);border-radius:8px;padding:8px;font:inherit;font-size:.78rem;font-weight:500;cursor:pointer}
.btn:hover{border-color:var(--accent);color:var(--accent)}
.section-title{font-size:1rem;font-weight:700;margin:14px 0 8px}
.vtable{width:100%;border-collapse:collapse;font-size:.8rem;margin-bottom:34px;background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);overflow:hidden}
.vtable th,.vtable td{text-align:left;padding:9px 12px;border-bottom:1px solid var(--border)}
.vtable th{background:var(--surface-2);font-size:.7rem;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
.vtable tr:last-child td{border-bottom:none}.vtable .mono{font-family:var(--mono)}
.overlay{position:fixed;inset:0;background:rgba(6,14,20,.55);z-index:30;display:none;padding:max(16px,env(safe-area-inset-top,0px)) 12px 12px}
.overlay[aria-hidden="false"]{display:flex;justify-content:center;align-items:flex-start}
.modal{background:var(--surface);border:1px solid var(--border);border-radius:14px;max-width:820px;width:100%;max-height:100%;display:flex;flex-direction:column;overflow:hidden;box-shadow:0 20px 60px rgba(0,0,0,.4)}
.modal-h{display:flex;align-items:center;gap:12px;padding:14px 16px;border-bottom:1px solid var(--border)}
.modal-h .id{font-family:var(--mono);font-weight:600}.modal-h .x{margin-left:auto;border:1px solid var(--border);background:var(--surface-2);color:var(--fg);border-radius:8px;width:32px;height:32px;cursor:pointer;font-size:1rem}
.tabs{display:flex;gap:4px;padding:10px 16px 0;flex-wrap:wrap}
.tab{border:none;background:none;color:var(--muted);font:inherit;font-size:.82rem;font-weight:600;padding:8px 12px;border-radius:8px 8px 0 0;cursor:pointer;border-bottom:2px solid transparent}
.tab[aria-selected="true"]{color:var(--accent);border-bottom-color:var(--accent)}
.code{margin:0;padding:16px;overflow:auto;font-family:var(--mono);font-size:.76rem;line-height:1.55;flex:1;background:var(--surface-2);white-space:pre}
.tok-key{color:var(--accent)}.tok-str{color:var(--good)}.tok-num{color:var(--warn)}.tok-bool{color:var(--crit)}.tok-null{color:var(--muted)}
footer{color:var(--muted);font-size:.74rem;padding:22px 0 40px;border-top:1px solid var(--border)}
@media (max-width:720px){.tiles{grid-template-columns:repeat(2,1fr)}.head-meta{width:100%;margin-left:0}}
@media (max-width:420px){.grid{grid-template-columns:1fr}}
@media (prefers-reduced-motion:reduce){*{transition:none!important}}
</style>

<header><div class="wrap head-in">
  <div class="brand"><h1>PavaLife — Device Data Contract</h1>
    <span class="sub">Thiết bị y tế · v<span id="sv"></span> · MQTT 5.0 over WSS · JSON Schema 2020-12</span></div>
  <div class="head-meta">
    <div class="kv">Facility<b class="mono" id="fac"></b></div>
    <div class="kv">Gateway<b class="mono" id="gw"></b></div>
    <button class="toggle" id="theme" type="button">◐ Giao diện</button>
  </div>
</div></header>

<main class="wrap">
  <div class="tiles" id="tiles"></div>
  <div class="banner">Broker <span class="mono" id="broker"></span> · Topic <span class="mono">pvl/v2/gw/{gateway}/up/{message_type}</span> — <b>patient_id KHÔNG nằm trong topic</b> (rule #10)</div>
  <div class="grid" id="grid"></div>

  <h2 class="section-title">Ví dụ thiếu dữ liệu (rule #7 — không gửi value:null)</h2>
  <table class="vtable"><thead><tr><th>Thiết bị</th><th>Chỉ số</th><th>data_absent_reason</th><th>quality</th></tr></thead>
    <tbody id="absent"></tbody></table>

  <footer class="wrap">Sinh tự động từ <span class="mono">samples/</span> · PavaLife Device Data Contract v2.1 · dữ liệu mô phỏng.</footer>
</main>

<div class="overlay" id="overlay" aria-hidden="true" role="dialog" aria-modal="true" aria-labelledby="m-id">
  <div class="modal"><div class="modal-h"><span class="id" id="m-id"></span><span class="mtype" id="m-type" style="margin:0"></span>
    <button class="x" id="m-close" type="button" aria-label="Đóng">×</button></div>
    <div class="tabs" role="tablist">
      <button class="tab" role="tab" data-tab="visual" aria-selected="true">Trực quan</button>
      <button class="tab" role="tab" data-tab="detail" aria-selected="false">Chỉ số</button>
      <button class="tab" role="tab" data-tab="msg" aria-selected="false">Bản tin (MQTT)</button>
    </div>
    <div class="code" id="m-visual" hidden></div><pre class="code" id="m-body"></pre>
  </div>
</div>

<script type="application/json" id="d">__DATA__</script>
<script>
"use strict";
const DATA=JSON.parse(document.getElementById("d").textContent);
const $=s=>document.querySelector(s);
const el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e;};
$("#sv").textContent=DATA.schema_version;$("#fac").textContent=DATA.facility;$("#gw").textContent=DATA.gateway_id;$("#broker").textContent=DATA.broker;

(function(){let s=null;try{s=localStorage.getItem("pvl-theme");}catch(e){}if(s)document.documentElement.setAttribute("data-theme",s);
 $("#theme").onclick=()=>{const c=document.documentElement.getAttribute("data-theme");const pd=matchMedia("(prefers-color-scheme:dark)").matches;const n=(c==="dark"||(!c&&pd))?"light":"dark";document.documentElement.setAttribute("data-theme",n);try{localStorage.setItem("pvl-theme",n);}catch(e){}runDraws();};})();

// Tiles
const nAll=DATA.devices.length, nOK=DATA.devices.filter(d=>d.valid).length+ (DATA.status.valid?1:0);
[[String(nAll),"thiết bị"],["vitals · lab · imaging","message_type"],[(nOK)+"/"+(nAll+1),"bản tin hợp lệ (schema)"],[DATA.absent.length,"ví dụ thiếu dữ liệu"]]
.forEach((t,i)=>{const d=el("div","tile"+(i===2?" ok":""));d.append(el("div","n",String(t[0])),el("div","l",t[1]));$("#tiles").append(d);});

// ==== ĐẨY DỮ LIỆU LÊN (PUSH) — mỗi 500ms một dữ liệu ====
const N_POINTS=120, PUSH_MS=500;
const AMP_BY_UNIT={"%":1.6,"beats/minute":6,"mmHg":7,"degree Celsius":0.25,"kilogram":0.2};
const COLORS=["#38bdf8","#4ade80","#f472b6","#fbbf24","#a78bfa"];
let pushStreams=[],liveCharts=[];
function pushOne(st){st.phase+=0.35;let v=st.base+st.amp*Math.sin(st.phase)+st.amp*0.4*Math.sin(st.phase*2.3)+(Math.random()-0.5)*st.amp*0.5;st.buf.push(v);if(st.buf.length>N_POINTS)st.buf.shift();st.cur=v;}
function newStream(label,unit,color,base,amp){const st={label,unit,color,base,amp,phase:Math.random()*6.28,buf:[],cur:base,min:base-amp*2.4,max:base+amp*2.4};for(let i=0;i<N_POINTS;i++)pushOne(st);return st;}
setInterval(()=>{for(const s of pushStreams)pushOne(s);},PUSH_MS);  // <<< BỘ ĐẾM ĐẨY 500ms
function ensureSize(cv,cssH){const w=cv.clientWidth||cv.parentNode.clientWidth||320;if(cv._w!==w||cv._hh!==cssH){const dpr=Math.min(2,devicePixelRatio||1);cv.width=Math.round(w*dpr);cv.height=Math.round(cssH*dpr);cv._ctx=cv.getContext("2d");cv._ctx.setTransform(dpr,0,0,dpr,0,0);cv._w=w;cv._hh=cssH;}return{ctx:cv._ctx,w,h:cssH};}
function drawMonitor(cv,streams,cssH){const {ctx,w,h}=ensureSize(cv,cssH);ctx.fillStyle="#06151c";ctx.fillRect(0,0,w,h);
 for(let x=0;x<w;x+=26){ctx.strokeStyle="#0e2b36";ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,h);ctx.stroke();}
 const band=h/Math.max(1,streams.length);
 streams.forEach((s,si)=>{const y0=si*band,N=s.buf.length,yOf=v=>y0+band-6-Math.max(0,Math.min(1,(v-s.min)/(s.max-s.min)))*(band-14);
  ctx.strokeStyle="#0e2b36";ctx.beginPath();ctx.moveTo(0,y0);ctx.lineTo(w,y0);ctx.stroke();
  ctx.strokeStyle=s.color;ctx.lineWidth=1.7;ctx.lineJoin="round";ctx.beginPath();
  for(let i=0;i<N;i++){const x=i/(N-1)*w;i?ctx.lineTo(x,yOf(s.buf[i])):ctx.moveTo(x,yOf(s.buf[i]));}ctx.stroke();
  ctx.fillStyle=s.color;ctx.beginPath();ctx.arc(w-2,yOf(s.cur),2.6,0,6.28);ctx.fill();
  ctx.font="bold 12px monospace";ctx.fillText(s.label+"  "+(Math.round(s.cur*10)/10)+" "+s.unit,8,y0+15);});}
function runDraws(){liveCharts=liveCharts.filter(c=>c.cv.isConnected);for(const c of liveCharts){try{c.fn();}catch(e){}}requestAnimationFrame(runDraws);}
requestAnimationFrame(runDraws);

function buildBars(summary){const box=el("div","bars");summary.forEach(r=>{const b=el("div","bar");const top=el("div","top");top.append(el("span","lab",r.label));
 const v=el("span","v");v.append(document.createTextNode(r.absent!=null?"—":r.value));if(r.unit&&r.absent==null)v.append(Object.assign(el("span","u"),{textContent:r.unit}));top.append(v);b.append(top);
 if(r.absent==null&&r.min!=null){const frac=Math.max(0,Math.min(1,(r.value-r.min)/(r.max-r.min)));const tr=el("div","track"),fl=el("div","fill");fl.style.width=(frac*100).toFixed(1)+"%";tr.append(fl);b.append(tr);
  const rg=el("div","rng");rg.append(el("span",null,String(r.min)),el("span",null,"ngưỡng KT"),el("span",null,String(r.max)));b.append(rg);}
 box.append(b);});return box;}
function buildMonitor(summary,big){const rows=summary.filter(r=>typeof r.value==="number");
 const streams=rows.map((r,i)=>{const amp=AMP_BY_UNIT[r.unit]!=null?AMP_BY_UNIT[r.unit]:Math.max(1,Math.abs(r.value)*0.04);const st=newStream(r.label,r.unit,COLORS[i%5],r.value,amp);pushStreams.push(st);return st;});
 const cssH=big?Math.max(170,streams.length*60):Math.max(112,streams.length*46);
 const wrap=el("div","viz"),cv=document.createElement("canvas");wrap.append(cv);
 wrap.append(Object.assign(el("div","caption"),{textContent:"Monitor · đẩy 1 điểm / "+PUSH_MS+"ms · cửa sổ "+N_POINTS+" điểm (mô phỏng)"}));
 liveCharts.push({cv,fn:()=>drawMonitor(cv,streams,cssH)});return wrap;}
function buildViz(d,big){
 if(d.kind==="vitals")return buildMonitor(d.summary,big);
 if(d.kind==="imaging"){const wrap=el("div","viz"),box=el("div","dicombox");
  box.append(Object.assign(el("div","dic-ico"),{textContent:"US"}));
  box.append(Object.assign(el("div","dic-t"),{textContent:"Ảnh DICOM · tải qua WADO-RS (pixel KHÔNG nhúng trong MQTT)"}));
  wrap.append(box,Object.assign(el("div","caption"),{textContent:"imaging.study · chỉ tham chiếu study + storage"}));return wrap;}
 return buildBars(d.summary);}

function render(){const g=$("#grid");g.innerHTML="";pushStreams=[];liveCharts=[];
 DATA.devices.forEach(d=>{const c=el("div","card");
  const h=el("div","card-h"),ib=el("div");ib.append(el("div","id",d.device_id),el("div","ty",d.device_key+" · "+d.source_type));
  const pill=el("span","pill "+(d.valid?"ok":"warn"));pill.append(el("span","dot"),document.createTextNode(d.valid?"hợp lệ":"lỗi"));h.append(ib,pill);
  c.append(h,el("span","mtype",d.message_type),buildViz(d,false));
  if(d.kind==="lab")c.append(Object.assign(el("div","labmeta"),{textContent:"Bệnh phẩm "+d.specimen.specimen_type+" · report "+d.report.status}));
  if(d.kind==="imaging"){c.append(buildBars(d.summary));if(d.wado)c.append(Object.assign(el("div","wado"),{textContent:"WADO-RS  "+d.wado}));}
  c.append(Object.assign(el("div","topic"),{textContent:d.topic}));
  const f=el("div","card-f");const b1=el("button","btn","Chỉ số");b1.onclick=e=>{e.stopPropagation();openModal(d,"detail");};
  const b2=el("button","btn","Bản tin JSON");b2.onclick=e=>{e.stopPropagation();openModal(d,"msg");};f.append(b1,b2);c.append(f);
  c.onclick=()=>openModal(d,"visual");g.append(c);});
 // the device.status
 const s=DATA.status,c=el("div","card");const h=el("div","card-h"),ib=el("div");ib.append(el("div","id",s.device_id),el("div","ty","device.status · robot_doctor"));
 const pill=el("span","pill ok");pill.append(el("span","dot"),document.createTextNode("hợp lệ"));h.append(ib,pill);
 c.append(h,el("span","mtype","device.status"));
 const rows=el("div","rows");const p=s.payload;
 [["connectivity",p.connectivity],["battery_percent",p.battery_percent+" %"],["sensor_health",p.sensor_health],["fault_codes",(p.hardware_fault_codes||[]).length?p.hardware_fault_codes.join(","):"—"]]
  .forEach(([k,v])=>{const r=el("div","row");r.append(el("div","lab",k));r.append(Object.assign(el("div","val"),{textContent:String(v)}));rows.append(r);});
 c.append(rows,Object.assign(el("div","topic"),{textContent:s.topic}));
 const f=el("div","card-f");const b2=el("button","btn","Bản tin JSON");b2.onclick=e=>{e.stopPropagation();openModal({device_id:s.device_id,message_type:"device.status",msg:s.msg,kind:"status",summary:[]},"msg");};f.append(b2);c.append(f);
 c.onclick=()=>openModal({device_id:s.device_id,message_type:"device.status",msg:s.msg,kind:"status",summary:[]},"msg");g.append(c);
 requestAnimationFrame(()=>{});}
let rT;addEventListener("resize",()=>{clearTimeout(rT);rT=setTimeout(()=>{},150);});

// Bang thieu du lieu
DATA.absent.forEach(a=>{const tr=el("tr");tr.append(Object.assign(el("td","mono"),{textContent:a.device_id}),el("td",null,a.label),Object.assign(el("td","mono"),{textContent:a.reason}),Object.assign(el("td","mono"),{textContent:a.quality.status+(a.quality.reason?" ("+a.quality.reason+")":"")}));$("#absent").append(tr);});

// Modal
let cur=null;
function hl(o){const s=JSON.stringify(o,null,2);return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+\-]?\d+)?/g,m=>{let c="tok-num";if(/^"/.test(m))c=/:$/.test(m)?"tok-key":"tok-str";else if(/true|false/.test(m))c="tok-bool";else if(/null/.test(m))c="tok-null";return `<span class="${c}">${m}</span>`;});}
function detailHTML(d){let s=`<span class="tok-key">Thiết bị</span> ${d.device_id} — ${d.message_type}\n<span class="tok-key">Topic</span> ${d.topic||""}\n\n`;
 d.summary.forEach(r=>{if(r.absent!=null)s+=`${r.label}: <span class="tok-bool">THIẾU (${r.absent})</span>  [${r.quality}]\n`;else s+=`${r.label}: ${r.value} ${r.unit||""}  [${r.quality}]\n`;});
 if(d.kind==="lab")s+=`\n<span class="tok-key">Specimen</span> ${d.specimen.specimen_type}\n<span class="tok-key">Report</span> ${d.report.status}`;
 return s;}
function showTab(t){[...document.querySelectorAll(".tab")].forEach(b=>b.setAttribute("aria-selected",b.dataset.tab===t?"true":"false"));if(!cur)return;
 const vis=$("#m-visual"),body=$("#m-body");
 if(t==="visual"){body.hidden=true;vis.hidden=false;vis.innerHTML="";if(cur.kind==="status"){vis.textContent="device.status — xem tab Bản tin JSON";}else{liveCharts=liveCharts.filter(c=>c.cv&&c.cv.isConnected);vis.append(buildViz(cur,true));}return;}
 vis.hidden=true;body.hidden=false;
 if(t==="detail")body.innerHTML=detailHTML(cur);else body.innerHTML=hl(cur.msg);}
function openModal(d,tab){cur=d;$("#m-id").textContent=d.device_id;$("#m-type").textContent=d.message_type;$("#overlay").setAttribute("aria-hidden","false");showTab(tab);}
function closeModal(){$("#overlay").setAttribute("aria-hidden","true");cur=null;}
document.querySelectorAll(".tab").forEach(b=>b.onclick=()=>showTab(b.dataset.tab));
$("#m-close").onclick=closeModal;$("#overlay").onclick=e=>{if(e.target===$("#overlay"))closeModal();};
addEventListener("keydown",e=>{if(e.key==="Escape")closeModal();});
render();
</script>
"""


def main():
    os.makedirs(OUT, exist_ok=True)
    data = build_data()
    html = HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  wrote viewer/index.html ({round(len(html.encode())/1024)} KB)")


if __name__ == "__main__":
    main()
