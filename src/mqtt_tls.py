"""Áp cấu hình TLS/SSL cho MQTT client (dùng chung cho local & cloud).

Hỗ trợ:
- TLS một chiều: xác thực server bằng CA (khuyến nghị tối thiểu).
- mTLS (hai chiều): thêm client_cert + client_key để server xác thực gateway.
- insecure: bỏ kiểm tra chứng chỉ — CHỈ dùng khi phát triển/tự ký, KHÔNG dùng thật.
"""
from __future__ import annotations

import logging
import ssl
from typing import Any, Dict

log = logging.getLogger("gateway.tls")


def apply_tls(client, cfg: Dict[str, Any], *,
              enabled_key: str = "tls",
              ca_key: str = "ca_cert",
              cert_key: str = "client_cert",
              key_key: str = "client_key",
              insecure_key: str = "tls_insecure",
              name: str = "mqtt") -> bool:
    """Cấu hình TLS cho `client` (paho) theo `cfg`. Trả về True nếu đã bật TLS."""
    if not cfg.get(enabled_key):
        return False

    ca = cfg.get(ca_key) or None
    cert = cfg.get(cert_key) or None
    key = cfg.get(key_key) or None
    insecure = bool(cfg.get(insecure_key, False))

    client.tls_set(
        ca_certs=ca,
        certfile=cert,
        keyfile=key,
        cert_reqs=ssl.CERT_NONE if insecure else ssl.CERT_REQUIRED,
    )
    if insecure:
        client.tls_insecure_set(True)
        log.warning("[%s] TLS INSECURE -> bo kiem tra chung chi (CHI DUNG DEV!)", name)
    else:
        log.info("[%s] TLS bat (mTLS=%s)", name, bool(cert))
    return True
