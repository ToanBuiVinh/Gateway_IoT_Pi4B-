"""mini_broker.py — MQTT broker THUAN PYTHON (chi thu vien chuan).

Dung de TEST CUC BO khi khong cai duoc Mosquitto / khong co Docker.
Khong can tai gi: chi can Python. Ho tro MQTT 3.1.1 (CONNECT/SUBSCRIBE/
PUBLISH/PINGREQ), QoS 0 & 1, wildcard + va #.

Chay:
    python mini_broker.py            # lang nghe 127.0.0.1:1883
    python mini_broker.py --port 1883 --host 0.0.0.0
Dung Ctrl+C de thoat.
"""
from __future__ import annotations

import argparse
import socket
import threading

_subs: dict = {}          # conn -> set(topic_filter)
_lock = threading.Lock()  # bao ve _subs + gui socket


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = b""
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise ConnectionError("closed")
        buf += chunk
    return buf


def _read_remaining_length(sock: socket.socket) -> int:
    mult, value = 1, 0
    while True:
        b = _recv_exact(sock, 1)[0]
        value += (b & 0x7F) * mult
        if not (b & 0x80):
            return value
        mult *= 128


def _encode_remaining_length(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n % 128
        n //= 128
        if n > 0:
            b |= 0x80
        out.append(b)
        if n == 0:
            return bytes(out)


def _topic_match(filt: str, topic: str) -> bool:
    f, t = filt.split("/"), topic.split("/")
    i = 0
    for i, part in enumerate(f):
        if part == "#":
            return True
        if i >= len(t):
            return False
        if part != "+" and part != t[i]:
            return False
    return len(f) == len(t)


def _send(sock: socket.socket, data: bytes) -> None:
    with _lock:
        try:
            sock.sendall(data)
        except OSError:
            pass


def _forward_publish(topic: str, payload: bytes) -> None:
    pkt_vh = len(topic).to_bytes(2, "big") + topic.encode() + payload   # QoS0 -> khong packet id
    pkt = bytes([0x30]) + _encode_remaining_length(len(pkt_vh)) + pkt_vh
    with _lock:
        targets = [c for c, filts in _subs.items() if any(_topic_match(f, topic) for f in filts)]
    for c in targets:
        _send(c, pkt)


def _handle(conn: socket.socket, addr) -> None:
    with _lock:
        _subs[conn] = set()
    try:
        while True:
            header = _recv_exact(conn, 1)[0]
            ptype = header >> 4
            rl = _read_remaining_length(conn)
            body = _recv_exact(conn, rl) if rl else b""

            if ptype == 1:          # CONNECT
                _send(conn, b"\x20\x02\x00\x00")            # CONNACK ok
            elif ptype == 12:       # PINGREQ
                _send(conn, b"\xd0\x00")                    # PINGRESP
            elif ptype == 8:        # SUBSCRIBE
                pid = body[0:2]
                i, codes = 2, bytearray()
                while i < len(body):
                    tlen = int.from_bytes(body[i:i + 2], "big"); i += 2
                    topic = body[i:i + tlen].decode(); i += tlen
                    i += 1                                   # qos byte
                    with _lock:
                        _subs[conn].add(topic)
                    codes.append(0x00)                       # granted QoS0
                suback = pid + bytes(codes)
                _send(conn, bytes([0x90]) + _encode_remaining_length(len(suback)) + suback)
            elif ptype == 3:        # PUBLISH
                qos = (header >> 1) & 0x03
                tlen = int.from_bytes(body[0:2], "big")
                topic = body[2:2 + tlen].decode()
                i = 2 + tlen
                if qos > 0:
                    pid = body[i:i + 2]; i += 2
                payload = body[i:]
                _forward_publish(topic, payload)
                if qos == 1:
                    _send(conn, b"\x40\x02" + pid)           # PUBACK
            elif ptype == 10:       # UNSUBSCRIBE
                pid = body[0:2]
                _send(conn, bytes([0xB0]) + _encode_remaining_length(2) + pid)
            elif ptype == 14:       # DISCONNECT
                break
    except (ConnectionError, OSError, IndexError):
        pass
    finally:
        with _lock:
            _subs.pop(conn, None)
        try:
            conn.close()
        except OSError:
            pass


def main() -> int:
    ap = argparse.ArgumentParser(description="MQTT broker thuan Python (test cuc bo)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=1883)
    args = ap.parse_args()

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((args.host, args.port))
    srv.listen(50)
    print(f"mini_broker: dang lang nghe mqtt://{args.host}:{args.port}  (Ctrl+C de dung)")
    try:
        while True:
            conn, addr = srv.accept()
            threading.Thread(target=_handle, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\nDung mini_broker.")
    finally:
        srv.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
