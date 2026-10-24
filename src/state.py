"""Trạng thái dùng chung giữa các worker (cờ online + thống kê)."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

log = logging.getLogger("gateway.state")


@dataclass
class Stats:
    received: int = 0          # tổng tin nhận từ node
    published_direct: int = 0  # gửi thẳng cloud (online)
    buffered: int = 0          # ghi vào SQLite (offline/lỗi)
    forwarded: int = 0         # gửi bù thành công từ buffer
    dropped: int = 0           # bị loại (payload lỗi / node lạ)
    rate_limited: int = 0      # bị chặn do vượt tốc độ (flood guard)
    oversized: int = 0         # bị chặn do payload quá lớn
    commands_relayed: int = 0  # lệnh downlink đã relay xuống node
    commands_dropped: int = 0  # lệnh bị loại (node lạ / lệnh hỏng)
    acks_relayed: int = 0      # phản hồi (ack) từ node đã relay lên cloud
    acks_dropped: int = 0      # ack bị loại (node lạ / ack hỏng / cloud offline)


class AppState:
    """Cờ kết nối cloud + số liệu vận hành.

    ``online`` là asyncio.Event: set = cloud sẵn sàng, clear = mất kết nối.
    Các worker chờ dữ liệu offline chỉ cần ``await state.online.wait()``.
    """

    def __init__(self) -> None:
        self.online = asyncio.Event()
        self.stats = Stats()
        self._last_transition = 0.0

    def set_online(self) -> None:
        if not self.online.is_set():
            self.online.set()
            self._last_transition = time.time()
            log.info("Cloud: ONLINE")

    def set_offline(self) -> None:
        if self.online.is_set():
            self.online.clear()
            self._last_transition = time.time()
            log.warning("Cloud: OFFLINE")

    @property
    def is_online(self) -> bool:
        return self.online.is_set()
