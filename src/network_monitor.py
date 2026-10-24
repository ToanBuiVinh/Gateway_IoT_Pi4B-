"""Network Monitor Worker: giám sát kết nối cloud theo chu kỳ (mặc định 5s).

paho đã tự cập nhật online/offline qua callback, nhưng broker có thể "chết
lặng" (half-open). Worker này chủ động thăm dò TCP tới cloud broker để phát
hiện sớm và đồng bộ lại cờ ``AppState.online``.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict

from .state import AppState

log = logging.getLogger("gateway.netmon")


async def network_monitor_worker(cfg: Dict[str, Any], cloud_cfg: Dict[str, Any],
                                 state: AppState) -> None:
    interval = float(cfg.get("interval_sec", 5))
    timeout = float(cfg.get("probe_timeout_sec", 3))
    host = cloud_cfg.get("host", "")
    port = int(cloud_cfg.get("port", 8883))
    enabled = bool(cloud_cfg.get("enabled", False))

    if not enabled:
        log.info("Cloud disabled -> Network Monitor khong thang do")
        return

    while True:
        reachable = await _probe(host, port, timeout)
        if not reachable and state.is_online:
            log.warning("Tham do %s:%s that bai -> danh dau OFFLINE", host, port)
            state.set_offline()
        # Khi reachable: để callback on_connect của paho set ONLINE (đã có handshake
        # MQTT thực sự), tránh báo online giả khi mới chỉ mở được TCP.
        await asyncio.sleep(interval)


async def _probe(host: str, port: int, timeout: float) -> bool:
    """Thử mở kết nối TCP; True nếu tới được broker."""
    try:
        fut = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(fut, timeout=timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass
        return True
    except (OSError, asyncio.TimeoutError):
        return False
