"""broker_check.py — KIỂM TRA KẾT NỐI tới broker MQTT (bất kỳ) theo từng bước.

Dùng để chuẩn bị/khắc phục khi kết nối broker production hoặc bên thứ ba. Chạy từng
bước rõ ràng [OK]/[FAIL] + gợi ý khắc phục, rồi gửi thử 1 bản tin device.status và
tự nhận lại (round-trip) để xác nhận cả publish lẫn subscribe.

Ví dụ:
  # broker cục bộ (mini_broker / Mosquitto):
  python tools/broker_check.py --broker mqtt://localhost:1883 --mqtt-version 311

  # production PavaLife (WSS + MQTT 5 + user/pass):
  python tools/broker_check.py \
      --broker wss://mqtt-hn-n1.pavalife.com:443/mqtt --mqtt-version 5 \
      --username GW-ROBOT-DEV-001 --password '<secret>' --ca-cert pavalife-ca.pem

Thoát code 0 nếu round-trip thành công, != 0 nếu có bước thất bại.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import socket
import ssl
import sys
import time
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_PORT = {"wss": 443, "ws": 9001, "mqtts": 8883, "mqtt": 1883, "tcp": 1883}


def ok(msg):   print(f"  [OK]   {msg}")
def fail(msg): print(f"  [FAIL] {msg}")
def info(msg): print(f"         {msg}")


def parse(url):
    if "://" not in url:
        url = "mqtt://" + url
    u = urlparse(url)
    scheme = u.scheme or "mqtt"
    return {
        "scheme": scheme, "host": u.hostname or "localhost",
        "port": u.port or _PORT.get(scheme, 1883),
        "path": u.path or "/mqtt",
        "ws": scheme in ("ws", "wss"), "tls": scheme in ("wss", "mqtts"),
    }


def step_tcp(cfg, timeout):
    print("[1] TCP reachability")
    try:
        s = socket.create_connection((cfg["host"], cfg["port"]), timeout=timeout)
        s.close()
        ok(f"mở được TCP tới {cfg['host']}:{cfg['port']}")
        return True
    except Exception as e:
        fail(f"không mở được TCP {cfg['host']}:{cfg['port']} — {e}")
        info("→ kiểm tra DNS, firewall/VPN, cổng đúng chưa; proxy có chặn 443/8883 không.")
        return False


def step_tls(cfg, timeout, ca_cert, insecure):
    print("[2] TLS handshake + chứng chỉ")
    if not cfg["tls"]:
        info("bỏ qua (scheme không TLS: " + cfg["scheme"] + ")")
        return True
    try:
        ctx = ssl.create_default_context(cafile=ca_cert) if ca_cert else ssl.create_default_context()
        if insecure:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        with socket.create_connection((cfg["host"], cfg["port"]), timeout=timeout) as sock:
            with ctx.wrap_socket(sock, server_hostname=cfg["host"]) as ss:
                cert = ss.getpeercert()
                ok(f"TLS {ss.version()} bắt tay thành công")
                if cert:
                    subj = dict(x[0] for x in cert.get("subject", []))
                    iss = dict(x[0] for x in cert.get("issuer", []))
                    info(f"CN={subj.get('commonName','?')}  issuer={iss.get('commonName','?')}  hết hạn={cert.get('notAfter','?')}")
        return True
    except ssl.SSLCertVerificationError as e:
        fail(f"xác minh chứng chỉ thất bại — {e}")
        info("→ thêm --ca-cert <CA nội bộ>.pem; chỉ dùng --insecure để THỬ (không cho production).")
        return False
    except Exception as e:
        fail(f"TLS lỗi — {e}")
        return False


def make_client(cfg, args):
    import paho.mqtt.client as mqtt
    proto = mqtt.MQTTv311 if str(args.mqtt_version) in ("311", "3.1.1") else mqtt.MQTTv5
    cid = args.client_id or "pvl-broker-check"
    transport = "websockets" if cfg["ws"] else "tcp"
    if hasattr(mqtt, "CallbackAPIVersion"):
        c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=cid, protocol=proto, transport=transport)
    else:
        c = mqtt.Client(client_id=cid, protocol=proto, transport=transport)
    if cfg["ws"]:
        headers = cfg.get("ws_headers")
        c.ws_set_options(path=cfg["path"], headers=headers)
    if cfg["tls"]:
        c.tls_set(ca_certs=args.ca_cert)
        if args.insecure:
            c.tls_insecure_set(True)
    if args.username:
        c.username_pw_set(args.username, args.password)
    return c, proto


def _ws_upgrade_status(host, port, tls, path, ca_cert, insecure, auth=None, timeout=8):
    """Gửi 1 yêu cầu nâng cấp WebSocket thô, trả (status_code, status_line)."""
    key = base64.b64encode(os.urandom(16)).decode()
    lines = [f"GET {path} HTTP/1.1", f"Host: {host}", "Upgrade: websocket",
             "Connection: Upgrade", f"Sec-WebSocket-Key: {key}",
             "Sec-WebSocket-Version: 13", "Sec-WebSocket-Protocol: mqtt"]
    if auth:
        lines.append("Authorization: Basic " + base64.b64encode(auth.encode()).decode())
    req = ("\r\n".join(lines) + "\r\n\r\n").encode()
    raw = socket.create_connection((host, port), timeout=timeout)
    try:
        if tls:
            ctx = ssl.create_default_context(cafile=ca_cert) if ca_cert else ssl.create_default_context()
            if insecure:
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
            s = ctx.wrap_socket(raw, server_hostname=host)
        else:
            s = raw
        s.sendall(req)
        resp = s.recv(2048).decode("latin-1", "replace")
        line = resp.split("\r\n", 1)[0].strip()
        parts = line.split(" ")
        code = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else None
        return code, line
    finally:
        try:
            raw.close()
        except OSError:
            pass


def probe_ws_paths(cfg, args, timeout):
    """Dò các đường dẫn WebSocket phổ biến. Trả (good_path, need_auth)."""
    print("         ↪ Dò đường dẫn WebSocket (status 101 = đúng):")
    cands = []
    for p in [cfg["path"], "/mqtt", "/", "/ws", "/mqtt/", "/mqtt-ws", "/ws/mqtt", "/mqtt/v2"]:
        if p and p not in cands:
            cands.append(p)
    auth = f"{args.username}:{args.password}" if args.username else None
    good, need_auth = None, False
    for p in cands:
        try:
            code, line = _ws_upgrade_status(cfg["host"], cfg["port"], cfg["tls"], p,
                                            args.ca_cert, args.insecure, timeout=timeout)
            tag = ""
            if code == 101:
                tag = "  ← 101 UPGRADED ✓"
            elif code == 401 and auth:                      # cần Basic auth ở tầng WS?
                code2, line2 = _ws_upgrade_status(cfg["host"], cfg["port"], cfg["tls"], p,
                                                  args.ca_cert, args.insecure, auth=auth, timeout=timeout)
                if code2 == 101:
                    line, code, tag = line2, 101, "  ← 101 UPGRADED (cần Basic auth) ✓"
            print(f"            {p:<10} {line}{tag}")
            if code == 101 and good is None:
                good = p
                need_auth = "Basic auth" in tag
        except Exception as e:
            print(f"            {p:<10} lỗi: {e}")
    return good, need_auth


def step_mqtt(cfg, args, timeout):
    print("[3] MQTT CONNECT + [4] publish/subscribe round-trip (device.status)")
    try:
        import paho.mqtt.client as mqtt
    except Exception as e:
        fail(f"thiếu paho-mqtt — {e}. Cài: pip install paho-mqtt")
        return False

    from gateway import contract as C, registry as reg
    topic = reg.topic_for("device.status")
    state = {"connected": False, "rc": None, "got": False}

    def on_connect(cl, u, flags, rc, props=None):
        state["connected"] = (int(rc) == 0 if hasattr(rc, "__int__") else rc == 0)
        state["rc"] = rc
        cl.subscribe(topic, qos=1)

    def on_message(cl, u, msg):
        try:
            d = json.loads(msg.payload.decode("utf-8"))
            if d.get("message_type") == "device.status":
                state["got"] = True
        except Exception:
            pass

    c, proto = make_client(cfg, args)
    c.on_connect = on_connect
    c.on_message = on_message
    connect_err = None
    try:
        c.connect(cfg["host"], cfg["port"], keepalive=30)
        c.loop_start()
    except Exception as e:
        connect_err = e

    # Lỗi nâng cấp WebSocket (handshake "not upgraded"/sai path) -> tự DÒ path
    if connect_err is not None:
        fail(f"connect() ném lỗi — {connect_err}")
        if not cfg["ws"]:
            return False
        good, need_auth = probe_ws_paths(cfg, args, timeout)
        if not good:
            info("→ không path WebSocket nào trả 101. Hỏi bên vận hành đường dẫn WS đúng,")
            info("  hoặc thử scheme khác (mqtts://host:8883 cho MQTT-over-TLS thuần).")
            return False
        info(f"→ TÌM THẤY path WebSocket: {good}" + ("  (cần Basic auth header)" if need_auth else ""))
        info(f"  Sửa gateway/registry.py: BROKER_URL = \"wss://{cfg['host']}:{cfg['port']}{good}\"")
        cfg = dict(cfg)
        cfg["path"] = good
        if need_auth:
            cfg["ws_headers"] = {"Authorization": "Basic " +
                                 base64.b64encode(f"{args.username}:{args.password}".encode()).decode()}
        state.update({"connected": False, "rc": None, "got": False})
        c, proto = make_client(cfg, args)
        c.on_connect = on_connect
        c.on_message = on_message
        try:
            c.connect(cfg["host"], cfg["port"], keepalive=30)
            c.loop_start()
        except Exception as e2:
            fail(f"vẫn lỗi với path {good} — {e2}")
            return False
        ok(f"nâng cấp WebSocket OK với path {good}")

    t0 = time.time()
    while time.time() - t0 < timeout and not state["connected"] and state["rc"] is None:
        time.sleep(0.05)
    time.sleep(0.3)
    if not state["connected"]:
        fail(f"CONNECT bị từ chối (reason={state['rc']})")
        info("→ sai username/password, client_id trùng/không được phép, hoặc TLS/ACL chặn.")
        c.loop_stop(); c.disconnect()
        return False
    ver = "3.1.1" if str(args.mqtt_version) in ("311", "3.1.1") else "5.0"
    ok(f"CONNECT thành công (MQTT {ver}) → subscribe {topic}")

    # publish device.status
    et = dt.datetime.now(dt.timezone(dt.timedelta(hours=7))).isoformat(timespec="milliseconds")
    msg = C.build_device_status(et) if hasattr(C, "build_device_status") else None
    if msg is None:
        info("không có builder device.status; publish payload tối thiểu.")
        payload = json.dumps({"message_type": "device.status", "schema_version": "2.1"})
    else:
        payload = json.dumps(msg, ensure_ascii=False)
    assert "patient" not in topic.lower(), "rule #10: patient_id khong duoc vao topic"
    pub = c.publish(topic, payload, qos=1)
    pub.wait_for_publish(timeout=timeout)
    if not pub.is_published():
        fail("publish KHÔNG được broker xác nhận (PUBACK) — có thể ACL chặn quyền publish.")
        info(f"→ xin mở quyền publish topic: {reg.topic_for('device.status').rsplit('/',1)[0]}/#")
        c.loop_stop(); c.disconnect()
        return False
    ok(f"publish device.status được broker xác nhận (QoS {pub.rc if hasattr(pub,'rc') else 1})")

    t0 = time.time()
    while time.time() - t0 < timeout and not state["got"]:
        time.sleep(0.05)
    c.loop_stop(); c.disconnect()
    if state["got"]:
        ok("ROUND-TRIP: tự nhận lại bản tin đã gửi → publish + subscribe đều hoạt động")
        return True
    fail("đã publish nhưng KHÔNG nhận lại được (subscribe/ACL subscribe có thể bị chặn)")
    info(f"→ xin mở quyền subscribe topic: {topic}")
    return False


def main():
    ap = argparse.ArgumentParser(description="Kiểm tra kết nối broker MQTT theo từng bước.")
    ap.add_argument("--broker", default=None, help="mac dinh = registry.BROKER_URL")
    ap.add_argument("--mqtt-version", choices=["5", "311"], default="5")
    ap.add_argument("--username", default="")
    ap.add_argument("--password", default="")
    ap.add_argument("--ca-cert", default=None)
    ap.add_argument("--insecure", action="store_true")
    ap.add_argument("--client-id", default="")
    ap.add_argument("--ws-path", default=None, help="ep duong dan WebSocket (vd / hoac /ws)")
    ap.add_argument("--timeout", type=float, default=10.0)
    args = ap.parse_args()

    # Nhanh PavaLife: mac dinh dung broker + thong tin dang nhap trong registry
    try:
        from gateway import registry as _reg
        if not args.broker:
            args.broker = getattr(_reg, "BROKER_URL", "mqtt://localhost:1883")
        if not args.username:
            args.username = getattr(_reg, "BROKER_USERNAME", "")
            args.password = args.password or getattr(_reg, "BROKER_PASSWORD", "")
    except Exception:
        if not args.broker:
            args.broker = "mqtt://localhost:1883"

    cfg = parse(args.broker)
    if args.ws_path:
        cfg["path"] = args.ws_path if args.ws_path.startswith("/") else "/" + args.ws_path
    print("=" * 62)
    print(f" BROKER CHECK  {args.broker}")
    print(f"   scheme={cfg['scheme']} host={cfg['host']} port={cfg['port']} "
          f"path={cfg['path']} tls={cfg['tls']} ws={cfg['ws']} mqtt={args.mqtt_version}")
    print("=" * 62)

    results = []
    results.append(step_tcp(cfg, args.timeout))
    if results[-1]:
        results.append(step_tls(cfg, args.timeout, args.ca_cert, args.insecure))
    if all(results):
        results.append(step_mqtt(cfg, args, args.timeout))

    print("-" * 62)
    passed = all(results) and len(results) >= 3
    print((" KẾT QUẢ: TẤT CẢ PASS — broker sẵn sàng dùng." if passed
           else " KẾT QUẢ: CÓ BƯỚC THẤT BẠI — xem gợi ý [→] ở trên."))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
