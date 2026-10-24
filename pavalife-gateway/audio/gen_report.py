"""gen_report.py — dung report HTML truc quan cho pipeline luu ho so am thanh.

Doc audio/out/summary.json (+ delivery.json neu co) -> audio/report.html.
Chay sau record_and_publish.py.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "audio", "out")


HTML = r"""<title>PavaLife Audio Pipeline</title>
<meta name="claude:viewport-fit-sides" content="cover">
<meta name="description" content="Report pipeline luu ho so am thanh ong nghe: synth -> FLAC lossless -> publish MQTT">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
/* Layout: report doc - hero so lieu, stepper doc, dang song, panel FLAC & MQTT, JSON */
:root{
  --bg:#eef2f6; --surface:#fff; --surface-2:#f1f5f9; --border:#d5dee7;
  --fg:#0e1b24; --muted:#5a6c7a; --accent:#1667c9; --accent-weak:#d9e8fb;
  --good:#1f8a4c; --good-weak:#dcf0e4; --warn:#9a5b06; --crit:#c0352f;
  --mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
  --sans:"IBM Plex Sans",system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
  --radius:12px; --shadow:0 1px 2px rgba(16,30,40,.06),0 4px 16px rgba(16,30,40,.05);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0b141b;--surface:#111d26;--surface-2:#17242e;--border:#243541;--fg:#e7eff5;
  --muted:#92a6b4;--accent:#5aa2f0;--accent-weak:#12304d;--good:#4fcc82;--good-weak:#133325;
  --warn:#e3a94f;--crit:#eb6b63;color-scheme:dark;}}
:root[data-theme="dark"]{--bg:#0b141b;--surface:#111d26;--surface-2:#17242e;--border:#243541;--fg:#e7eff5;
  --muted:#92a6b4;--accent:#5aa2f0;--accent-weak:#12304d;--good:#4fcc82;--good-weak:#133325;
  --warn:#e3a94f;--crit:#eb6b63;color-scheme:dark;}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font-family:var(--sans);line-height:1.5;margin:0}
body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);background:var(--surface);z-index:9}
.wrap{padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px));max-width:860px;margin:0 auto}
h1,h2{text-wrap:balance;margin:0}.mono{font-family:var(--mono)}
header{background:var(--surface);border-bottom:1px solid var(--border);padding-block:18px;margin-bottom:18px}
header h1{font-size:1.3rem;font-weight:700;letter-spacing:-.01em}
header .sub{color:var(--muted);font-size:.82rem;margin-top:3px}
.toggle{float:right;border:1px solid var(--border);background:var(--surface-2);color:var(--fg);border-radius:8px;padding:6px 10px;font:inherit;font-size:.78rem;cursor:pointer}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}
.tile{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:13px 15px;box-shadow:var(--shadow)}
.tile .n{font-size:1.5rem;font-weight:700;letter-spacing:-.02em}.tile .n.ok{color:var(--good)}
.tile .l{color:var(--muted);font-size:.72rem;margin-top:2px}
h2{font-size:1rem;margin:22px 0 10px;display:flex;align-items:center;gap:8px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow);padding:16px;margin-bottom:6px}
/* stepper */
.step{display:flex;gap:12px;align-items:flex-start;padding:9px 0;border-bottom:1px solid var(--border)}
.step:last-child{border-bottom:none}
.badge{flex:none;width:22px;height:22px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:.72rem;font-weight:700}
.badge.ok{background:var(--good-weak);color:var(--good)}.badge.no{background:#f6d9d6;color:var(--crit)}
.step .t{font-weight:600;font-size:.88rem}.step .d{color:var(--muted);font-size:.78rem;font-family:var(--mono);word-break:break-all}
.step .arrow{position:absolute}
/* waveform */
.wave{width:100%;height:120px;display:block;background:#06151c;border-radius:9px}
.wavecap{font-family:var(--mono);font-size:.68rem;color:var(--muted);margin-top:6px}
/* flac compare */
.flac{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.flac .b{background:var(--surface-2);border:1px solid var(--border);border-radius:9px;padding:12px}
.flac .b .k{color:var(--muted);font-size:.72rem}.flac .b .v{font-size:1.4rem;font-weight:700;font-variant-numeric:tabular-nums}
.bar{height:12px;border-radius:999px;background:var(--surface-2);border:1px solid var(--border);overflow:hidden;margin-top:10px}
.bar .fill{height:100%;background:var(--accent)}
.pill{display:inline-flex;align-items:center;gap:5px;font-size:.74rem;font-weight:600;padding:3px 10px;border-radius:999px;background:var(--good-weak);color:var(--good)}
.kv{display:flex;gap:10px;font-size:.82rem;padding:5px 0}.kv .k{color:var(--muted);min-width:150px}.kv .v{font-family:var(--mono);word-break:break-all}
.code{margin:0;padding:14px;overflow:auto;font-family:var(--mono);font-size:.74rem;line-height:1.5;background:var(--surface-2);border-radius:9px;white-space:pre;max-height:420px}
.tok-key{color:var(--accent)}.tok-str{color:var(--good)}.tok-num{color:var(--warn)}.tok-bool{color:var(--crit)}.tok-null{color:var(--muted)}
footer{color:var(--muted);font-size:.74rem;padding:20px 0 40px;border-top:1px solid var(--border);margin-top:22px}
@media (max-width:620px){.tiles{grid-template-columns:repeat(2,1fr)}.flac{grid-template-columns:1fr}}
</style>

<header><div class="wrap">
  <button class="toggle" id="theme" type="button">◐ Giao diện</button>
  <h1>PavaLife — Audio Pipeline (lưu hồ sơ ống nghe)</h1>
  <div class="sub">synth → WAV → <b>FLAC lossless</b> → publish MQTT · thiết bị <span class="mono" id="dev"></span> · <span id="gen"></span></div>
</div></header>

<main class="wrap">
  <div class="tiles" id="tiles"></div>

  <h2>1 · Pipeline: server → publish</h2>
  <div class="card" id="steps"></div>

  <h2>2 · Tín hiệu nghe tim (dạng sóng)</h2>
  <div class="card"><canvas class="wave" id="wave"></canvas>
    <div class="wavecap" id="wavecap"></div></div>

  <h2>3 · Nén FLAC (lossless)</h2>
  <div class="card">
    <div class="flac">
      <div class="b"><div class="k">WAV gốc (PCM)</div><div class="v" id="wavb"></div></div>
      <div class="b"><div class="k">FLAC (--best)</div><div class="v" id="flacb"></div></div>
    </div>
    <div class="bar"><div class="fill" id="ratiofill"></div></div>
    <div style="margin-top:10px;display:flex;gap:12px;align-items:center;flex-wrap:wrap">
      <span class="pill" id="llpill">● lossless</span>
      <span class="mono" style="font-size:.78rem;color:var(--muted)" id="ratiotxt"></span>
    </div>
    <div class="kv"><span class="k">sha256</span><span class="v" id="sha"></span></div>
  </div>

  <h2>4 · Publish MQTT (đã nhận tại subscriber)</h2>
  <div class="card" id="mqtt"></div>

  <h2>5 · Bản tin observation.audio</h2>
  <div class="card" style="padding:0"><pre class="code" id="msg"></pre></div>

  <footer>Sinh tự động từ <span class="mono">audio/record_and_publish.py</span> + <span class="mono">gen_report.py</span> · dữ liệu mô phỏng, FLAC &amp; MQTT là thật.</footer>
</main>

<script type="application/json" id="d">__DATA__</script>
<script>
"use strict";
const D=JSON.parse(document.getElementById("d").textContent);
const $=s=>document.querySelector(s), el=(t,c,x)=>{const e=document.createElement(t);if(c)e.className=c;if(x!=null)e.textContent=x;return e;};
(function(){let s=null;try{s=localStorage.getItem("pvl-rep");}catch(e){}if(s)document.documentElement.setAttribute("data-theme",s);
 $("#theme").onclick=()=>{const c=document.documentElement.getAttribute("data-theme");const pd=matchMedia("(prefers-color-scheme:dark)").matches;const n=(c==="dark"||(!c&&pd))?"light":"dark";document.documentElement.setAttribute("data-theme",n);try{localStorage.setItem("pvl-rep",n);}catch(e){}draw();};})();
$("#dev").textContent=D.device_id; $("#gen").textContent=D.generated_at;

const f=D.flac, allok=D.steps.every(s=>s.ok);
[[D.steps.length+"/"+D.steps.length,"bước pipeline",allok],
 [f.ratio_pct+"%","FLAC/WAV (lossless)",false],
 [f.lossless?"✓":"✗","bit-exact",f.lossless],
 [(D.delivery&&D.delivery.received)?"✓":"—","đã publish",D.delivery&&D.delivery.received]]
.forEach(t=>{const d=el("div","tile");const n=el("div","n"+(t[2]?" ok":""),String(t[0]));d.append(n,el("div","l",t[1]));$("#tiles").append(d);});

// steps
D.steps.forEach(s=>{const row=el("div","step");row.append(Object.assign(el("div","badge "+(s.ok?"ok":"no")),{textContent:s.ok?"✓":"✗"}));
 const box=el("div");box.append(el("div","t",s.step),el("div","d",s.detail));row.append(box);$("#steps").append(row);});

// flac panel
$("#wavb").textContent=f.wav_bytes.toLocaleString()+" B";
$("#flacb").textContent=f.flac_bytes.toLocaleString()+" B";
$("#ratiofill").style.width=f.ratio_pct+"%";
$("#ratiotxt").textContent="FLAC = "+f.ratio_pct+"% của WAV · giảm "+(100-f.ratio_pct).toFixed(1)+"% mà KHÔNG mất dữ liệu";
$("#sha").textContent=f.sha256;
if(!f.lossless){$("#llpill").className="pill";$("#llpill").style.background="#f6d9d6";$("#llpill").style.color="var(--crit)";$("#llpill").textContent="● KHÔNG lossless";}

// mqtt
const dl=D.delivery;
if(dl){[["Trạng thái", dl.received?"ĐÃ NHẬN ✓":"chưa"],["Topic",dl.topic],
  ["message_type",dl.message_type+"  (seq "+dl.seq+")"],["Định dạng",dl.format+" / "+dl.codec+" · "+dl.size_bytes.toLocaleString()+" B"],
  ["patient_id trong topic?", String(dl.patient_id_in_topic)+"  (rule #10)"]]
 .concat(dl.via?[["Đường truyền", dl.via]]:[])
 .forEach(([k,v])=>{const r=el("div","kv");r.append(el("span","k",k),el("span","v",v));$("#mqtt").append(r);});}
else $("#mqtt").append(el("div","d","Chạy với --publish --local để gửi thật và bắt bản tin."));

// message json
function hl(o){const s=JSON.stringify(o,null,2);return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/"(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d+)?/g,m=>{let c="tok-num";if(/^"/.test(m))c=/:$/.test(m)?"tok-key":"tok-str";else if(/true|false/.test(m))c="tok-bool";else if(/null/.test(m))c="tok-null";return `<span class="${c}">${m}</span>`;});}
$("#msg").innerHTML=hl(D.message);

// waveform
function draw(){const cv=$("#wave");const dpr=Math.min(2,devicePixelRatio||1),w=cv.clientWidth||800,h=120;
 cv.width=w*dpr;cv.height=h*dpr;const ctx=cv.getContext("2d");ctx.setTransform(dpr,0,0,dpr,0,0);
 ctx.fillStyle="#06151c";ctx.fillRect(0,0,w,h);
 const env=D.envelope,N=env.length,mid=h/2,g=(h*0.46)/D.env_max;
 ctx.strokeStyle="#4fcc82";ctx.lineWidth=1;
 for(let i=0;i<N;i++){const x=i/(N-1)*w,a=env[i]*g;ctx.beginPath();ctx.moveTo(x,mid-a);ctx.lineTo(x,mid+a);ctx.stroke();}
 ctx.fillStyle="rgba(190,238,255,.7)";ctx.font="10px monospace";ctx.fillText("Nghe tim (S1/S2) · "+D.signal.fs+" Hz · 16-bit · "+D.signal.duration_sec+"s",8,14);}
$("#wavecap").textContent=D.signal.samples.toLocaleString()+" mẫu · envelope "+D.envelope.length+" điểm (rút gọn để vẽ)";
draw();addEventListener("resize",draw);
</script>
"""


def main():
    with open(os.path.join(OUT, "summary.json"), encoding="utf-8") as f:
        data = json.load(f)
    dpath = os.path.join(OUT, "delivery.json")
    if os.path.exists(dpath):
        with open(dpath, encoding="utf-8") as f:
            data["delivery"] = json.load(f)
    html = HTML.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    out = os.path.join(ROOT, "audio", "report.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  wrote {out} ({round(len(html.encode())/1024)} KB)")


if __name__ == "__main__":
    main()
