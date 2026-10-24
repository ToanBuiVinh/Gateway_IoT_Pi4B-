"""web_viewer.py — XEM DỮ LIỆU MQTT TRÊN TRANG HTML (trực tiếp).

Trình duyệt KHÔNG nói được MQTT/TCP thẳng, nên công cụ này làm cầu nối:
  broker  --(MQTT/TCP, paho)-->  web_viewer  --(HTTP + SSE)-->  trình duyệt

Chạy được với BẤT KỲ broker nào: mini_broker.py, Mosquitto, hay production.
Chỉ dùng thư viện chuẩn + paho-mqtt (đã có trong requirements.txt).

Chạy:
    python tools/web_viewer.py                 # nghe mqtt://localhost:1883, mở http://localhost:8080
    python tools/web_viewer.py --broker mqtt://localhost:1883 --http-port 8080

Rồi mở trình duyệt vào  http://localhost:8080  — bản tin hiện LIVE khi gateway publish.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import paho.mqtt.client as mqtt   # noqa: E402

_DEFAULT_PORT = {"wss": 443, "ws": 9001, "mqtts": 8883, "mqtt": 1883, "tcp": 1883}

MESSAGES: "deque" = deque(maxlen=200)   # bộ đệm bản tin gần đây
SUBSCRIBERS: list = []                  # hàng đợi SSE cho mỗi trình duyệt
_lock = threading.Lock()
_seq = 0


def _parse(url):
    if "://" not in url:
        url = "mqtt://" + url
    u = urlparse(url)
    ws = u.scheme in ("ws", "wss")
    tls = u.scheme in ("wss", "mqtts")
    return (u.hostname or "localhost"), (u.port or _DEFAULT_PORT.get(u.scheme, 1883)), (u.path or "/mqtt"), ws, tls


def _dget(x, *keys, default=None):
    """Lấy lồng nhau an toàn: trả default nếu gặp thứ không phải dict."""
    for k in keys:
        if not isinstance(x, dict):
            return default
        x = x.get(k)
    return default if x is None else x


def _digest(topic: str, data: dict) -> dict:
    """Rút các trường chính để hiển thị gọn trên thẻ (chịu lỗi: không bao giờ raise)."""
    p = data.get("payload", {}) if isinstance(data, dict) else {}
    if not isinstance(p, dict):
        p = {}
    d = {
        "topic": topic,
        "message_type": data.get("message_type", "?") if isinstance(data, dict) else "?",
        "seq": data.get("sequence_no") if isinstance(data, dict) else None,
        "event_time": data.get("event_time") if isinstance(data, dict) else None,
        "source_type": _dget(data, "source", "source_type"),
        "patient_id_in_topic": "patient" in topic.lower(),
        "patient_id": _dget(data, "patient_context", "patient_id"),
        "raw": data,
    }
    items = []
    try:
        # observation.vitals / observation.lab -> measurements
        for m in (p.get("measurements") or []):
            if not isinstance(m, dict):
                continue
            code = _dget(m, "code", "display") or m.get("local_code") or "?"
            if "value" in m:
                unit = m.get("unit")
                unit = unit.get("code", "") if isinstance(unit, dict) else (unit or "")
                items.append(f"{code}: {m['value']} {unit}".strip())
            elif "components" in m:
                parts = ", ".join(f"{c.get('local_code')}={c.get('value')}"
                                  for c in m["components"] if isinstance(c, dict))
                items.append(f"{code}: [{parts}]")
            elif "data_absent_reason" in m:
                items.append(f"{code}: (thiếu: {m['data_absent_reason']})")
        # observation.audio
        if isinstance(p.get("recording"), dict):
            r = p["recording"]; st = p.get("storage") if isinstance(p.get("storage"), dict) else {}
            items.append(f"audio {r.get('format')}/{r.get('codec')} · lossless={r.get('lossless')} · {st.get('size_bytes', '?')} B")
            if st.get("url"):
                items.append("storage: " + str(st["url"]))
        # imaging.study
        if ("study" in p) or ("series" in p):
            st = p.get("storage") if isinstance(p.get("storage"), dict) else {}
            items.append("DICOM study · " + str(st.get("wado_rs_study") or st.get("type", "ref")))
        # device.status (schema v2.1: connectivity str, battery_percent, sensor_health)
        if ("connectivity" in p) or ("battery_percent" in p) or ("sensor_health" in p):
            pin = p.get("battery_percent")
            if pin is None:
                pin = _dget(p, "battery", "level_pct")
            conn = p.get("connectivity")
            if isinstance(conn, dict):
                conn = conn.get("state")
            items.append(f"pin {pin if pin is not None else '?'}% · {conn or '?'} · sensor {p.get('sensor_health', '?')}")
    except Exception as e:   # không để một bản tin lạ làm hỏng viewer
        items.append(f"(không đọc được chi tiết: {e})")
    d["items"] = items
    return d


def on_connect(c, u, f, rc, props=None):
    c.subscribe("pvl/v2/gw/+/up/#", qos=1)
    print("[viewer] da ket noi broker, subscribe pvl/v2/gw/+/up/#")


def on_message(c, u, msg):
    global _seq
    try:
        try:
            data = json.loads(msg.payload.decode("utf-8"))
        except Exception:
            data = {"_raw": msg.payload[:200].decode("latin-1", "replace")}
        dig = _digest(msg.topic, data if isinstance(data, dict) else {})
        with _lock:
            _seq += 1
            dig["_id"] = _seq
            MESSAGES.append(dig)
            payload = "data: " + json.dumps(dig, ensure_ascii=False) + "\n\n"
            for q in list(SUBSCRIBERS):
                q.append(payload)
        print(f"[viewer] nhan {dig['message_type']} seq {dig['seq']} <- {msg.topic}")
    except Exception as e:   # tuyet doi khong de callback raise -> giet loop subscriber
        print(f"[viewer] bo qua ban tin loi: {e}")


def start_subscriber(broker_url: str):
    host, port, path, ws, tls = _parse(broker_url)
    if hasattr(mqtt, "CallbackAPIVersion"):
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="pvl-web-viewer",
                        protocol=mqtt.MQTTv311, transport="websockets" if ws else "tcp")
    else:
        c = mqtt.Client(client_id="pvl-web-viewer", protocol=mqtt.MQTTv311,
                        transport="websockets" if ws else "tcp")
    if ws:
        c.ws_set_options(path=path)
    if tls:
        c.tls_set()
    c.on_connect = on_connect
    c.on_message = on_message
    c.connect(host, port, keepalive=30)
    c.loop_start()
    return c


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _html(self, page):
        body = page.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._html(DASH_PAGE or PAGE)        # dashboard (do thi/audio/sieu am); fallback trang log
        elif self.path == "/log":
            self._html(PAGE)                     # danh sach ban tin dang the
        elif self.path == "/audio.wav":
            self.send_response(200 if WAV_BYTES else 404)
            self.send_header("Content-Type", "audio/wav")
            self.send_header("Content-Length", str(len(WAV_BYTES)))
            self.send_header("Accept-Ranges", "none")
            self.end_headers()
            if WAV_BYTES:
                self.wfile.write(WAV_BYTES)
        elif self.path == "/messages":
            with _lock:
                body = json.dumps(list(MESSAGES), ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/stream":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            q: "deque" = deque()
            with _lock:
                SUBSCRIBERS.append(q)
            try:
                self.wfile.write(b": connected\n\n")
                self.wfile.flush()
                while True:
                    if q:
                        chunk = q.popleft()
                        self.wfile.write(chunk.encode("utf-8"))
                        self.wfile.flush()
                    else:
                        self.wfile.write(b": ping\n\n")
                        self.wfile.flush()
                        time.sleep(1)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                with _lock:
                    if q in SUBSCRIBERS:
                        SUBSCRIBERS.remove(q)
        else:
            self.send_error(404)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--broker", default="mqtt://localhost:1883")
    ap.add_argument("--http-port", type=int, default=8080)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    start_subscriber(args.broker)
    httpd = ThreadingHTTPServer((args.host, args.http_port), Handler)
    print(f"[viewer] MO TRINH DUYET: http://{args.host}:{args.http_port}")
    print(f"[viewer]   /      -> dashboard (do thi chay lien tuc + nghe am tim + cine sieu am)")
    print(f"[viewer]   /log   -> danh sach ban tin dang the")
    print(f"[viewer] dang cau noi broker {args.broker} -> trang HTML (SSE). Ctrl+C de dung.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nDung web_viewer.")


# ------------------------------- TRANG HTML -------------------------------
PAGE = r"""<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>PavaLife — Live MQTT Viewer</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
:root{--bg:#eef2f6;--surface:#fff;--surface-2:#f1f5f9;--border:#d5dee7;--fg:#0e1b24;--muted:#5a6c7a;
 --accent:#1667c9;--good:#1f8a4c;--good-weak:#dcf0e4;--warn:#9a5b06;--warn-weak:#f6ecd6;--crit:#c0352f;--crit-weak:#f6d9d6;
 --mono:"IBM Plex Mono",ui-monospace,Menlo,Consolas,monospace;--sans:"IBM Plex Sans",system-ui,Segoe UI,Roboto,sans-serif;
 --radius:12px;--shadow:0 1px 2px rgba(16,30,40,.06),0 4px 16px rgba(16,30,40,.05);}
@media (prefers-color-scheme:dark){:root{--bg:#0b141b;--surface:#111d26;--surface-2:#17242e;--border:#243541;--fg:#e7eff5;
 --muted:#92a6b4;--accent:#5aa2f0;--good:#4fcc82;--good-weak:#133325;--warn:#e3a94f;--warn-weak:#2e2410;--crit:#eb6b63;--crit-weak:#331715;color-scheme:dark;}}
*{box-sizing:border-box}body{background:var(--bg);color:var(--fg);font-family:var(--sans);margin:0;line-height:1.5}
.wrap{max-width:900px;margin:0 auto;padding:0 16px}
header{background:var(--surface);border-bottom:1px solid var(--border);padding:16px 0;margin-bottom:16px;position:sticky;top:0;z-index:5}
h1{font-size:1.2rem;margin:0;font-weight:700}.sub{color:var(--muted);font-size:.8rem;margin-top:3px}
.dot{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--crit);margin-right:6px;vertical-align:middle}
.dot.on{background:var(--good);box-shadow:0 0 0 3px var(--good-weak)}
.bar{display:flex;gap:14px;flex-wrap:wrap;font-size:.78rem;color:var(--muted);margin-top:8px}
.bar b{color:var(--fg);font-variant-numeric:tabular-nums}
.empty{color:var(--muted);text-align:center;padding:50px 0;font-size:.9rem}
.card{background:var(--surface);border:1px solid var(--border);border-left:4px solid var(--accent);border-radius:var(--radius);
 box-shadow:var(--shadow);padding:13px 15px;margin-bottom:10px;animation:in .35s ease}
@keyframes in{from{opacity:0;transform:translateY(-6px)}to{opacity:1;transform:none}}
.card.vitals{border-left-color:#1667c9}.card.lab{border-left-color:#9a5b06}.card.imaging{border-left-color:#7b3fb0}
.card.audio{border-left-color:#1f8a4c}.card.status{border-left-color:#5a6c7a}
.row1{display:flex;align-items:center;gap:8px;flex-wrap:wrap}
.type{font-weight:700;font-size:.92rem}.seq{font-family:var(--mono);font-size:.72rem;color:var(--muted)}
.tg{margin-left:auto;font-family:var(--mono);font-size:.7rem;color:var(--muted);word-break:break-all}
.pill{font-size:.68rem;font-weight:600;padding:2px 8px;border-radius:999px;background:var(--good-weak);color:var(--good)}
.pill.no{background:var(--crit-weak);color:var(--crit)}
.items{margin:8px 0 0;padding:0;list-style:none;font-family:var(--mono);font-size:.78rem}
.items li{padding:2px 0;color:var(--fg);word-break:break-all}.items li::before{content:"• ";color:var(--muted)}
.meta{color:var(--muted);font-size:.72rem;margin-top:6px}
details{margin-top:8px}summary{cursor:pointer;font-size:.74rem;color:var(--accent)}
pre{background:var(--surface-2);border-radius:8px;padding:10px;overflow:auto;font-family:var(--mono);font-size:.72rem;max-height:320px;margin:6px 0 0}
</style></head><body>
<header><div class="wrap">
 <h1>PavaLife — Live MQTT Viewer</h1>
 <div class="sub"><span class="dot" id="dot"></span><span id="conn">đang kết nối…</span> · cầu nối broker → HTTP/SSE · topic <span class="mono">pvl/v2/gw/+/up/#</span></div>
 <div class="bar"><span>Tổng: <b id="cnt">0</b></span><span>vitals <b id="c-vitals">0</b></span><span>lab <b id="c-lab">0</b></span>
  <span>imaging <b id="c-imaging">0</b></span><span>audio <b id="c-audio">0</b></span><span>status <b id="c-status">0</b></span></div>
</div></header>
<main class="wrap"><div id="list"><div class="empty" id="empty">Chưa có bản tin. Hãy publish: <span class="mono">python pvl_send.py all --local --publish</span></div></div></main>
<script>
"use strict";
const list=document.getElementById("list"), counts={vitals:0,lab:0,imaging:0,audio:0,status:0};
let total=0;
function kind(mt){if(mt.indexOf("vitals")>=0)return"vitals";if(mt.indexOf("lab")>=0)return"lab";
 if(mt.indexOf("imaging")>=0)return"imaging";if(mt.indexOf("audio")>=0)return"audio";return"status";}
function esc(s){return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;");}
function add(d){
 const e=document.getElementById("empty"); if(e)e.remove();
 const k=kind(d.message_type); counts[k]=(counts[k]||0)+1; total++;
 document.getElementById("cnt").textContent=total;
 const cc=document.getElementById("c-"+k); if(cc)cc.textContent=counts[k];
 const c=document.createElement("div"); c.className="card "+k;
 const items=(d.items||[]).map(x=>"<li>"+esc(x)+"</li>").join("");
 const p10=d.patient_id_in_topic?'<span class="pill no">patient_id trong topic ✗</span>'
                                 :'<span class="pill">rule #10 ✓ (không patient_id trong topic)</span>';
 c.innerHTML=
  '<div class="row1"><span class="type">'+esc(d.message_type)+'</span>'
  +'<span class="seq">seq '+esc(d.seq)+'</span>'+p10
  +'<span class="tg">'+esc(d.topic)+'</span></div>'
  +(items?'<ul class="items">'+items+'</ul>':'')
  +'<div class="meta">'+esc(d.event_time||'')+(d.patient_id?' · bệnh nhân '+esc(d.patient_id)+' (chỉ trong payload)':'')+'</div>'
  +'<details><summary>Xem JSON đầy đủ</summary><pre>'+esc(JSON.stringify(d.raw,null,2))+'</pre></details>';
 list.insertBefore(c,list.firstChild);
}
fetch("/messages").then(r=>r.json()).then(a=>a.forEach(add)).catch(()=>{});
const es=new EventSource("/stream");
es.onopen=()=>{document.getElementById("dot").classList.add("on");document.getElementById("conn").textContent="đã kết nối (live)";};
es.onerror=()=>{document.getElementById("dot").classList.remove("on");document.getElementById("conn").textContent="mất kết nối — thử lại…";};
es.onmessage=ev=>{try{add(JSON.parse(ev.data));}catch(e){}};
</script></body></html>"""


# ---- Dashboard (đồ thị + âm thanh + siêu âm) dùng chung template với artifact ----
# Script nhúng thêm: hút dữ liệu THẬT từ broker (SSE) vào đồ thị + log bản tin.
LIVE_WIRING = r"""
/* ----- LIVE: hut du lieu that tu broker vao do thi + log ----- */
(function(){
  if(typeof charts==="undefined")return;
  var byLoinc={}; charts.forEach(function(c){byLoinc[c.sig.loinc]=c;});
  function flash(c){try{c.val.animate([{opacity:.25},{opacity:1}],{duration:400});}catch(e){}}
  function pushReal(c,v){v=+v;if(isNaN(v))return;
    c.buf.push(v);if(c.buf.length>WIN)c.buf.shift();
    c.val.textContent=(c.sig.unit==="°C")?v.toFixed(1):Math.round(v);
    var ok=v>=c.sig.lo&&v<=c.sig.hi;c.pill.className="pill "+(ok?"ok":"sus");
    c.pill.textContent=ok?"bình thường":"theo dõi";drawChart(c);flash(c);}
  function absorb(raw){var p=raw&&raw.payload;if(!p)return;
    (p.measurements||[]).forEach(function(m){
      var loinc=m.code&&m.code.loinc;
      if(("value" in m)&&byLoinc[loinc])pushReal(byLoinc[loinc],m.value);
      (m.components||[]).forEach(function(cp){var lc=(cp.local_code||"").toLowerCase();
        if(lc.indexOf("systol")>=0&&byLoinc["8480-6"])pushReal(byLoinc["8480-6"],cp.value);
        if(lc.indexOf("diastol")>=0&&byLoinc["8462-4"])pushReal(byLoinc["8462-4"],cp.value);});});}
  var main=document.querySelector("main");
  var h2=document.createElement("h2");h2.textContent="Kết nối broker (MQTT → SSE)";
  var box=document.createElement("div");box.className="card";box.style.marginTop="10px";
  box.innerHTML='<div style="font-size:.8rem;color:var(--muted)">Bản tin nhận từ broker (LIVE): <b id="lc">0</b></div>'
    +'<div id="lg" class="mono" style="font-size:.74rem;margin-top:6px;max-height:150px;overflow:auto"></div>';
  main.appendChild(h2);main.appendChild(box);
  var lg=box.querySelector("#lg"),lc=box.querySelector("#lc"),cnt=0;
  function addlog(d){cnt++;lc.textContent=cnt;var r=document.createElement("div");
    r.textContent="← "+d.message_type+" seq "+d.seq+(d.items&&d.items[0]?"  · "+d.items[0]:"");
    lg.insertBefore(r,lg.firstChild);while(lg.childNodes.length>50)lg.removeChild(lg.lastChild);}
  function handle(d){addlog(d);if(d.raw)absorb(d.raw);}
  fetch("/messages").then(function(r){return r.json();}).then(function(a){a.forEach(handle);}).catch(function(){});
  try{var es=new EventSource("/stream");es.onmessage=function(ev){try{handle(JSON.parse(ev.data));}catch(e){}};}catch(e){}
})();
"""

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "viewer"))
try:
    import gen_live_dashboard as _dash          # noqa: E402
    WAV_BYTES = _dash.audio_asset()[0]
    DASH_PAGE = _dash.render(_dash.build_data(audio_src="/audio.wav"),
                             use_real_us=True, extra_script=LIVE_WIRING)
except Exception as _e:                          # thieu viewer/ -> van chay trang log
    WAV_BYTES, DASH_PAGE = b"", None
    print("[viewer] khong dung duoc dashboard, chi chay trang log:", _e)


if __name__ == "__main__":
    main()
