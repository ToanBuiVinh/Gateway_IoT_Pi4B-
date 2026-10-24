"""gen_live_dashboard.py — sinh trang DASHBOARD tự chứa (xem được ngay trên trình duyệt).

Hiển thị:
  • Đồ thị vitals CHẠY LIÊN TỤC (HR, SpO2, nhiệt độ, huyết áp) — cửa sổ cuộn, chu kỳ 10 giá trị lặp lại.
  • Ống nghe: PHÁT ÂM THANH tim (WAV nhúng data-URI, loop) + dạng sóng chạy.
  • Siêu âm: cine B-mode mô phỏng (canvas) chạy liên tục.

Dữ liệu mô phỏng nhưng đúng đơn vị/ngưỡng theo contract v2.1. Output: viewer/live_dashboard.html
"""
from __future__ import annotations
import base64, io, json, math, os, random, struct, wave

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "live_dashboard.html")


def heart_wav_loop(beats=5, hr=75, fs=8000, seed=3):
    """Sinh WAV int16 nghe tim, SỐ NHỊP NGUYÊN để phát loop liền mạch."""
    rng = random.Random(seed)
    rr = 60.0 / hr
    n = int(round(beats * rr * fs))
    samples = []
    for i in range(n):
        t = i / fs
        ph = t % rr
        s1 = math.exp(-((ph - 0.04) ** 2) / (2 * 0.018 ** 2)) * math.sin(2 * math.pi * 55 * ph)
        s2 = 0.7 * math.exp(-((ph - 0.34) ** 2) / (2 * 0.016 ** 2)) * math.sin(2 * math.pi * 75 * ph)
        v = 0.6 * (s1 + s2) + rng.uniform(-0.015, 0.015)
        samples.append(max(-32768, min(32767, int(v * 30000))))
    return samples, fs, rr, beats


def wav_bytes(samples, fs):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(fs)
        w.writeframes(b"".join(struct.pack("<h", s) for s in samples))
    return buf.getvalue()


def envelope(samples, points=360):
    step = max(1, len(samples) // points)
    return [max(abs(x) for x in samples[i:i + step]) or 0 for i in range(0, len(samples), step)]


def audio_asset():
    """Trả (wav_bytes, env, fs, beats, duration) cho ống nghe (dùng chung)."""
    samples, fs, rr, beats = heart_wav_loop()
    wb = wav_bytes(samples, fs)
    return wb, envelope(samples), fs, beats, round(len(samples) / fs, 2)


def build_data(audio_src=None):
    """Dữ liệu dashboard. audio_src=None -> nhúng WAV base64; hoặc truyền URL (vd '/audio.wav')."""
    wb, env, fs, beats, dur = audio_asset()
    wav = audio_src or ("data:audio/wav;base64," + base64.b64encode(wb).decode("ascii"))
    data = {
        "audio": {"wav": wav, "env": env, "env_max": 32768, "fs": fs, "beats": beats, "duration": dur},
        "signals": [
            {"key": "hr",   "label": "Nhịp tim",    "unit": "bpm",  "loinc": "8867-4",
             "lo": 60, "hi": 100, "min": 55, "max": 110, "color": "accent",
             "cycle": [72, 74, 76, 78, 77, 75, 73, 72, 74, 76]},
            {"key": "spo2", "label": "SpO₂",        "unit": "%",    "loinc": "2708-6",
             "lo": 94, "hi": 100, "min": 88, "max": 100, "color": "good",
             "cycle": [98, 98, 97, 98, 99, 98, 97, 98, 98, 97]},
            {"key": "temp", "label": "Nhiệt độ",    "unit": "°C",   "loinc": "8310-5",
             "lo": 36.1, "hi": 37.5, "min": 35.5, "max": 38.5, "color": "warn",
             "cycle": [36.6, 36.7, 36.7, 36.8, 36.8, 36.7, 36.6, 36.7, 36.8, 36.7]},
            {"key": "sys",  "label": "HA tâm thu",  "unit": "mmHg", "loinc": "8480-6",
             "lo": 90, "hi": 140, "min": 80, "max": 160, "color": "imaging",
             "cycle": [120, 122, 119, 121, 123, 120, 118, 121, 122, 120]},
            {"key": "dia",  "label": "HA tâm trương", "unit": "mmHg", "loinc": "8462-4",
             "lo": 60, "hi": 90, "min": 50, "max": 110, "color": "imaging2",
             "cycle": [80, 81, 79, 80, 82, 80, 79, 81, 80, 80]},
        ],
        "labs": [
            {"label": "Axit uric", "value": 360, "unit": "µmol/L", "loinc": "14933-6", "lo": 150, "hi": 420},
            {"label": "Đường huyết", "value": 5.6, "unit": "mmol/L", "loinc": "14743-9", "lo": 3.9, "hi": 7.8},
        ],
        # siêu âm thật (chỉ local viewer tải được; artifact bị CSP chặn -> dùng canvas mô phỏng)
        "ultrasound_real": {
            "image": "https://upload.wikimedia.org/wikipedia/commons/c/c7/CRL_Crown_rump_length_12_weeks_ecografia_Dr._Wolfgang_Moroder.jpg",
            "image_credit": "Dr. Wolfgang Moroder, CC BY-SA 3.0, Wikimedia Commons",
            "cine": "https://upload.wikimedia.org/wikipedia/commons/4/41/Doppler_mitral_valve.gif",
            "cine_credit": "Kjetil Lenes, CC BY-SA 3.0, Wikimedia Commons",
        },
    }
    return data


def render(data, use_real_us=False, extra_script=""):
    """Dựng HTML dashboard từ data. use_real_us=True để tải ảnh/cine Wikimedia (chỉ hợp local viewer)."""
    html = PAGE.replace("/*__DATA__*/null", json.dumps(data, ensure_ascii=False))
    html = html.replace("__USE_REAL_US__", "true" if use_real_us else "false")
    if extra_script:
        i = html.rfind("</script>")
        html = html[:i] + "\n" + extra_script + "\n" + html[i:]
    return html


def main():
    data = build_data()                      # artifact: nhúng WAV, siêu âm mô phỏng (CSP)
    html = render(data, use_real_us=False)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"wrote {OUT} ({len(html)//1024} KB)  | {data['audio']['beats']} nhịp loop, env {len(data['audio']['env'])} điểm")


# ------------------------------------------------------------------ TRANG
PAGE = r"""<title>PavaLife Live Monitor</title>
<meta name="claude:viewport-fit-sides" content="cover">
<meta name="description" content="Dashboard đồ thị chạy liên tục (vitals), nghe âm tim ống nghe, và cine siêu âm — mô phỏng theo Device Data Contract v2.1.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
/* Layout: monitor y tế — hàng số liệu, lưới đồ thị cuộn, panel ống nghe + siêu âm */
:root{
  --bg:#eef2f6;--surface:#fff;--surface-2:#f1f5f9;--border:#d5dee7;--fg:#0e1b24;--muted:#5a6c7a;
  --accent:#1667c9;--good:#1f8a4c;--warn:#b4710a;--imaging:#7b3fb0;--imaging2:#b0529a;--crit:#c0352f;
  --grid:rgba(90,108,122,.16);--scr:#06151c;
  --mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;
  --sans:"IBM Plex Sans",system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
  --radius:12px;--shadow:0 1px 2px rgba(16,30,40,.06),0 4px 16px rgba(16,30,40,.05);
}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){
  --bg:#0b141b;--surface:#111d26;--surface-2:#17242e;--border:#243541;--fg:#e7eff5;--muted:#92a6b4;
  --accent:#5aa2f0;--good:#4fcc82;--warn:#e3a94f;--imaging:#b98be0;--imaging2:#e085c5;--crit:#eb6b63;
  --grid:rgba(146,166,180,.16);color-scheme:dark;}}
:root[data-theme="dark"]{
  --bg:#0b141b;--surface:#111d26;--surface-2:#17242e;--border:#243541;--fg:#e7eff5;--muted:#92a6b4;
  --accent:#5aa2f0;--good:#4fcc82;--warn:#e3a94f;--imaging:#b98be0;--imaging2:#e085c5;--crit:#eb6b63;
  --grid:rgba(146,166,180,.16);color-scheme:dark;}
*{box-sizing:border-box}
body{background:var(--bg);color:var(--fg);font-family:var(--sans);line-height:1.5;margin:0}
body::before{content:"";position:fixed;inset:0 0 auto;height:env(safe-area-inset-top,0px);background:var(--surface);z-index:10}
.wrap{max-width:1000px;margin:0 auto;padding-left:max(16px,env(safe-area-inset-left,0px));padding-right:max(16px,env(safe-area-inset-right,0px))}
h1,h2{text-wrap:balance;margin:0}.mono{font-family:var(--mono)}
header{background:var(--surface);border-bottom:1px solid var(--border);padding-block:16px;margin-bottom:18px;position:sticky;top:env(safe-area-inset-top,0px);z-index:9}
header h1{font-size:1.25rem;font-weight:700;letter-spacing:-.01em}
header .sub{color:var(--muted);font-size:.8rem;margin-top:3px}
.live{display:inline-flex;align-items:center;gap:6px;font-size:.72rem;font-weight:600;color:var(--good)}
.live .d{width:8px;height:8px;border-radius:50%;background:var(--good);animation:pulse 1.4s ease-in-out infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.25}}
.toggle{float:right;border:1px solid var(--border);background:var(--surface-2);color:var(--fg);border-radius:8px;padding:6px 10px;font:inherit;font-size:.76rem;cursor:pointer}
.toggle:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
h2{font-size:1rem;margin:22px 0 10px;display:flex;align-items:center;gap:8px}
.grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}
.card{background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);box-shadow:var(--shadow);padding:13px 15px}
.chart .top{display:flex;align-items:baseline;gap:8px}
.chart .lbl{font-weight:600;font-size:.86rem}.chart .lo{color:var(--muted);font-size:.68rem;font-family:var(--mono)}
.chart .val{margin-left:auto;font-family:var(--mono);font-weight:700;font-size:1.15rem;font-variant-numeric:tabular-nums}
.chart .u{font-size:.68rem;color:var(--muted);font-weight:500}
.chart canvas{width:100%;height:72px;display:block;margin-top:6px;background:var(--scr);border-radius:8px}
.pill{font-size:.64rem;font-weight:700;padding:1px 7px;border-radius:999px;margin-left:6px}
.pill.ok{background:color-mix(in srgb,var(--good) 18%,transparent);color:var(--good)}
.pill.sus{background:color-mix(in srgb,var(--warn) 22%,transparent);color:var(--warn)}
.two{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.media{min-width:0}
.scope{width:100%;height:120px;display:block;background:var(--scr);border-radius:9px}
.usbox{position:relative;width:100%;aspect-ratio:4/3;max-width:100%;background:var(--scr);border-radius:9px;overflow:hidden}
.usbox canvas,.usbox img{position:absolute;inset:0;width:100%;height:100%;object-fit:cover;display:block}
.row{display:flex;align-items:center;gap:10px;margin-top:10px;flex-wrap:wrap}
button.play{border:1px solid var(--accent);background:var(--accent);color:#fff;border-radius:8px;padding:7px 14px;font:inherit;font-size:.82rem;font-weight:600;cursor:pointer}
button.play:focus-visible{outline:2px solid var(--fg);outline-offset:2px}
.cap{font-size:.72rem;color:var(--muted);font-family:var(--mono);margin-top:8px;word-break:break-word}
.labrow{display:flex;align-items:center;gap:10px;margin:8px 0}
.labrow .k{min-width:120px;font-size:.84rem}.labrow .bar{flex:1;height:10px;border-radius:999px;background:var(--surface-2);border:1px solid var(--border);overflow:hidden;min-width:0}
.labrow .fill{height:100%;background:var(--good)}.labrow .v{font-family:var(--mono);font-weight:600;font-size:.84rem;white-space:nowrap}
.note{font-size:.76rem;color:var(--muted);border-left:3px solid var(--accent);padding:6px 0 6px 12px;margin:10px 0;background:linear-gradient(90deg,var(--surface-2),transparent)}
footer{color:var(--muted);font-size:.74rem;border-top:1px solid var(--border);margin-top:26px;padding:16px 0 44px}
@media (max-width:720px){.grid{grid-template-columns:1fr}.two{grid-template-columns:1fr}.toggle{float:none;display:block;margin-bottom:8px}}
@media (prefers-reduced-motion:reduce){.live .d{animation:none}}
</style>

<header><div class="wrap">
  <button class="toggle" id="theme" type="button">◐ Giao diện</button>
  <h1>PavaLife — Live Monitor</h1>
  <div class="sub"><span class="live"><span class="d"></span>LIVE</span> · đồ thị chạy liên tục · nghe âm tim · cine siêu âm — mô phỏng theo <span class="mono">contract v2.1</span></div>
</div></header>

<main class="wrap">
  <h2>Sinh hiệu — đồ thị cuộn liên tục</h2>
  <div class="grid" id="charts"></div>

  <h2>Xét nghiệm</h2>
  <div class="card" id="labs"></div>

  <div class="two" style="margin-top:18px">
    <div>
      <h2>🩺 Ống nghe (observation.audio)</h2>
      <div class="card media">
        <canvas class="scope" id="scope"></canvas>
        <div class="row">
          <button class="play" id="play" type="button">▶ Nghe âm tim</button>
          <span class="mono" style="font-size:.74rem;color:var(--muted)" id="ainfo"></span>
        </div>
        <div class="cap">WAV/FLAC lossless raw · phát loop · dạng sóng chạy theo nhịp tim (S1/S2).</div>
      </div>
    </div>
    <div>
      <h2>🖼️ Siêu âm (imaging.study)</h2>
      <div class="card media">
        <div class="usbox" id="usbox"><canvas id="us"></canvas></div>
        <div class="cap" id="uscap">Cine B-mode mô phỏng (canvas) — quét quạt + đốm speckle chạy liên tục.</div>
      </div>
    </div>
  </div>

  <div class="note" id="srcnote"></div>

  <footer>Sinh từ <span class="mono">viewer/gen_live_dashboard.py</span> · dữ liệu mô phỏng đúng đơn vị/ngưỡng contract v2.1.
    Ảnh/cine siêu âm thật (bản local) từ Wikimedia Commons (CC BY-SA).</footer>
</main>

<audio id="aud" loop></audio>
<script>
"use strict";
const D=/*__DATA__*/null;
const USE_REAL_US=__USE_REAL_US__;
const $=s=>document.querySelector(s), cvar=n=>getComputedStyle(document.documentElement).getPropertyValue("--"+n).trim();

/* theme toggle */
(function(){const r=document.documentElement,b=$("#theme");
 try{const s=localStorage.getItem("pvl-mon");if(s)r.setAttribute("data-theme",s);}catch(e){}
 b.onclick=()=>{const c=r.getAttribute("data-theme"),pd=matchMedia("(prefers-color-scheme:dark)").matches;
   const n=(c==="dark"||(!c&&pd))?"light":"dark";r.setAttribute("data-theme",n);
   try{localStorage.setItem("pvl-mon",n);}catch(e){}};})();

/* ---------- đồ thị vitals cuộn liên tục ---------- */
const WIN=14;                     // số điểm hiển thị trong cửa sổ
const charts=D.signals.map(sig=>{
  const card=document.createElement("div");card.className="card chart";
  card.innerHTML='<div class="top"><span class="lbl">'+sig.label+'</span>'
    +'<span class="lo">'+sig.lo+'–'+sig.hi+' '+sig.unit+' · LOINC '+sig.loinc+'</span>'
    +'<span class="val"><span id="v-'+sig.key+'">–</span> <span class="u">'+sig.unit+'</span>'
    +'<span class="pill ok" id="p-'+sig.key+'">bình thường</span></span></div>'
    +'<canvas id="c-'+sig.key+'"></canvas>';
  $("#charts").appendChild(card);
  const buf=[]; let idx=0;
  // nạp sẵn đầy cửa sổ để không trống lúc mở
  for(let i=0;i<WIN;i++){buf.push(sig.cycle[i%sig.cycle.length]);}
  idx=WIN%sig.cycle.length;
  return {sig,buf,get idx(){return idx;},set idx(v){idx=v;},
    canvas:$("#c-"+sig.key),val:$("#v-"+sig.key),pill:$("#p-"+sig.key)};
});

function jitter(v,unit){const j=unit==="°C"?0.05:(unit==="%"?0.3:1.1);return v+(Math.random()*2-1)*j;}

function drawChart(c){
  const sig=c.sig,cv=c.canvas,dpr=Math.min(2,devicePixelRatio||1);
  const w=cv.clientWidth||300,h=72;cv.width=w*dpr;cv.height=h*dpr;
  const g=cv.getContext("2d");g.setTransform(dpr,0,0,dpr,0,0);
  g.fillStyle=cvar("scr");g.fillRect(0,0,w,h);
  // lưới
  g.strokeStyle=cvar("grid");g.lineWidth=1;
  for(let k=1;k<4;k++){const y=h*k/4;g.beginPath();g.moveTo(0,y);g.lineTo(w,y);g.stroke();}
  // dải bình thường (lo..hi)
  const sc=v=>h-((v-sig.min)/(sig.max-sig.min))*h;
  g.fillStyle="color-mix(in srgb,"+cvar(col(sig.color))+" 12%,transparent)";
  g.fillRect(0,sc(sig.hi),w,sc(sig.lo)-sc(sig.hi));
  // đường tín hiệu
  const n=c.buf.length,col1=cvar(col(sig.color));
  g.strokeStyle=col1;g.lineWidth=2;g.lineJoin="round";g.beginPath();
  c.buf.forEach((v,i)=>{const x=i/(WIN-1)*w,y=sc(v);i?g.lineTo(x,y):g.moveTo(x,y);});
  g.stroke();
  // điểm đầu (mới nhất)
  const lx=(n-1)/(WIN-1)*w,ly=sc(c.buf[n-1]);
  g.fillStyle=col1;g.beginPath();g.arc(lx,ly,3,0,7);g.fill();
}
function col(name){return name==="imaging2"?"imaging2":name;}

function tickVitals(){
  charts.forEach(c=>{
    const sig=c.sig, raw=sig.cycle[c.idx%sig.cycle.length];
    c.idx=c.idx+1;
    const v=jitter(raw,sig.unit);
    c.buf.push(v); if(c.buf.length>WIN)c.buf.shift();
    const disp=sig.unit==="°C"?v.toFixed(1):Math.round(v);
    c.val.textContent=disp;
    const ok=v>=sig.lo&&v<=sig.hi;
    c.pill.className="pill "+(ok?"ok":"sus");c.pill.textContent=ok?"bình thường":"theo dõi";
    drawChart(c);
  });
}

/* ---------- xét nghiệm (thanh) ---------- */
$("#labs").innerHTML=D.labs.map(l=>{
  const pct=Math.max(4,Math.min(100,Math.round((l.value-l.lo)/(l.hi-l.lo)*100)));
  const ok=l.value>=l.lo&&l.value<=l.hi;
  return '<div class="labrow"><span class="k">'+l.label+' <span class="lo mono" style="color:var(--muted);font-size:.68rem">'+l.loinc+'</span></span>'
    +'<span class="bar"><span class="fill" style="width:'+pct+'%;background:'+(ok?'var(--good)':'var(--warn)')+'"></span></span>'
    +'<span class="v">'+l.value+' '+l.unit+'</span></div>';
}).join("");

/* ---------- ống nghe: âm thanh + sóng chạy ---------- */
const aud=$("#aud");aud.src=D.audio.wav;
$("#ainfo").textContent=D.audio.fs+" Hz · 16-bit · "+D.audio.beats+" nhịp loop · "+D.audio.duration+"s";
$("#play").onclick=()=>{if(aud.paused){aud.play();$("#play").textContent="⏸ Tạm dừng";}else{aud.pause();$("#play").textContent="▶ Nghe âm tim";}};
let scrollX=0;
function drawScope(){
  const cv=$("#scope"),dpr=Math.min(2,devicePixelRatio||1),w=cv.clientWidth||400,h=120;
  cv.width=w*dpr;cv.height=h*dpr;const g=cv.getContext("2d");g.setTransform(dpr,0,0,dpr,0,0);
  g.fillStyle=cvar("scr");g.fillRect(0,0,w,h);
  const env=D.audio.env,N=env.length,mid=h/2,amp=(h*0.46)/D.audio.env_max;
  g.strokeStyle=cvar("good");g.lineWidth=1;
  for(let x=0;x<w;x++){const i=Math.floor((x+scrollX)% w / w * N)%N;const a=env[i]*amp;
    g.beginPath();g.moveTo(x,mid-a);g.lineTo(x,mid+a);g.stroke();}
  g.fillStyle="rgba(190,238,255,.7)";g.font="10px monospace";g.fillText("Âm tim S1/S2 · "+D.audio.fs+" Hz",8,14);
}

/* ---------- siêu âm: cine B-mode mô phỏng hoặc ảnh thật ---------- */
let usCanvas=$("#us"),speck=null,sweep=0;
function initUS(){
  const cv=usCanvas,dpr=Math.min(2,devicePixelRatio||1),w=cv.clientWidth||300,h=cv.clientHeight||225;
  cv.width=w*dpr;cv.height=h*dpr;cv._g=cv.getContext("2d");cv._g.setTransform(dpr,0,0,dpr,0,0);cv._w=w;cv._h=h;
  speck=new Float32Array(2600);for(let i=0;i<speck.length;i++)speck[i]=Math.random();
}
function drawUS(ph){
  const cv=usCanvas,g=cv._g,w=cv._w,h=cv._h;if(!g)return;
  g.fillStyle="#04101a";g.fillRect(0,0,w,h);
  const apexX=w/2,apexY=h*0.04,R=h*0.96,half=Math.PI/5;         // quạt quét
  g.save();g.beginPath();g.moveTo(apexX,apexY);
  g.arc(apexX,apexY,R,Math.PI/2-half,Math.PI/2+half);g.closePath();g.clip();
  // nền speckle + 1 cấu trúc tròn đập theo nhịp
  const blobY=apexY+R*0.55, blobR=R*(0.12+0.02*Math.sin(ph*2*Math.PI));
  let si=0;
  for(let rr=0.08;rr<1;rr+=0.012){
    for(let a=-half;a<=half;a+=0.03){
      const x=apexX+Math.sin(a)*R*rr, y=apexY+Math.cos(a)*R*rr;
      const d=Math.hypot(x-apexX,y-blobY);
      let b=speck[(si++)%speck.length]*0.5+0.12;
      if(d<blobR)b+=0.45*(1-d/blobR);                           // cấu trúc sáng
      b*=(1-rr*0.35);                                           // mờ dần theo độ sâu
      const v=Math.max(0,Math.min(255,b*255))|0;
      g.fillStyle="rgb("+v+","+v+","+((v*0.96)|0)+")";
      g.fillRect(x,y,2.2,2.2);
    }
  }
  // đường quét sáng
  const sa=-half+((sweep%100)/100)*(2*half);
  g.strokeStyle="rgba(180,245,255,.35)";g.lineWidth=2;
  g.beginPath();g.moveTo(apexX,apexY);g.lineTo(apexX+Math.sin(sa)*R,apexY+Math.cos(sa)*R);g.stroke();
  g.restore();
  g.fillStyle="rgba(190,238,255,.75)";g.font="10px monospace";g.fillText("US B-mode · cine (mô phỏng)",8,14);
}

/* ---------- vòng lặp hoạt hoạ ---------- */
function resizeAll(){charts.forEach(drawChart);if(usCanvas&&usCanvas._g)drawUS(phase());}
let t0=performance.now();
function phase(){return ((performance.now()-t0)/ (D.audio.duration*1000))%1;}
function raf(){
  scrollX=(scrollX+1.6);sweep+=1.4;
  drawScope();
  if(usCanvas&&usCanvas._g)drawUS(phase());
  requestAnimationFrame(raf);
}

/* siêu âm thật (chỉ local viewer): thử ảnh Wikimedia, lỗi -> canvas mô phỏng */
function setupUS(){
  const note=$("#srcnote");
  if(USE_REAL_US && D.ultrasound_real){
    const box=$("#usbox");
    const img=new Image();img.alt="Siêu âm (Wikimedia Commons)";
    img.onload=()=>{box.innerHTML="";const im=document.createElement("img");im.src=D.ultrasound_real.cine;box.appendChild(im);
      $("#uscap").innerHTML="Cine siêu âm thật (Doppler van 2 lá) — "+D.ultrasound_real.cine_credit;};
    img.onerror=()=>{initUS();};                 // không tải được -> mô phỏng
    img.src=D.ultrasound_real.cine;
    note.innerHTML="Bản local hiển thị <b>ảnh/cine siêu âm thật</b> từ Wikimedia Commons (CC BY-SA). "
      +"Nếu không tải được sẽ tự chuyển sang cine mô phỏng.";
  }else{
    initUS();
    note.innerHTML="Bản xem tại đây dùng <b>cine B-mode mô phỏng</b> (canvas) vì trang artifact chặn ảnh từ host ngoài. "
      +"Chạy <span class='mono'>web_viewer.py</span> trên máy để xem <b>ảnh/cine siêu âm thật</b> (Wikimedia CC).";
  }
}

setupUS();
tickVitals();
setInterval(tickVitals,700);          // đẩy 1 điểm mỗi 700ms -> chạy liên tục
addEventListener("resize",resizeAll);
requestAnimationFrame(raf);
</script>
"""

if __name__ == "__main__":
    main()
