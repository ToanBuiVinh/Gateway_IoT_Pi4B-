"""Chống flood ở tầng gateway: token-bucket per-node + giới hạn kích thước payload.

Mosquitto không có cơ chế giới hạn *tốc độ publish/giây* cho từng client, nên
gateway tự thực thi để bảo vệ pipeline (RAM queue) và thẻ SD khỏi node lỗi/bị
chiếm quyền phát tràn dữ liệu.

TokenBucket cho phép tốc độ trung bình `rate` msg/s và cụm ngắn tối đa `burst`.
Thiết kế nhận `now` tường minh để kiểm thử tất định (không phụ thuộc đồng hồ thật).
"""
from __future__ import annotations

import time
from typing import Dict, Iterable, Optional, Tuple


class TokenBucket:
    __slots__ = ("rate", "burst", "tokens", "last")

    def __init__(self, rate: float, burst: float) -> None:
        self.rate = float(rate)
        self.burst = float(burst)
        self.tokens = float(burst)
        self.last: Optional[float] = None

    def allow(self, now: float) -> bool:
        if self.last is None:
            self.last = now
        elapsed = now - self.last
        if elapsed > 0:
            self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
            self.last = now
        if self.tokens >= 1.0:
            self.tokens -= 1.0
            return True
        return False


class FloodGuard:
    """Kiểm soát flood cho mỗi node: kích thước payload + tốc độ bản tin."""

    def __init__(self, cfg: Dict, known_ids: Optional[Iterable[str]] = None) -> None:
        self.enabled = bool(cfg.get("enabled", False))
        self.rate = float(cfg.get("max_msgs_per_sec", 5))
        self.burst = float(cfg.get("burst", 10))
        self.max_payload = int(cfg.get("max_payload_bytes", 2048))
        self.warn_interval = float(cfg.get("warn_interval_sec", 10))
        self._known = set(known_ids) if known_ids is not None else None
        self._buckets: Dict[str, TokenBucket] = {}
        self._last_warn: Dict[str, float] = {}

    def check(self, node_id: str, payload: bytes,
              now: Optional[float] = None) -> Tuple[bool, Optional[str]]:
        """Trả về (ok, reason). reason ∈ {None, "size", "rate"}."""
        if not self.enabled:
            return True, None
        if self.max_payload and len(payload) > self.max_payload:
            return False, "size"
        # Node lạ: không cấp phát bucket (chống phình bộ nhớ do id ngẫu nhiên),
        # để tầng sau loại bỏ và đếm vào "dropped".
        if self._known is not None and node_id not in self._known:
            return True, None
        now = now if now is not None else time.monotonic()
        bucket = self._buckets.get(node_id)
        if bucket is None:
            bucket = TokenBucket(self.rate, self.burst)
            self._buckets[node_id] = bucket
        if bucket.allow(now):
            return True, None
        return False, "rate"

    def should_warn(self, node_id: str, now: Optional[float] = None) -> bool:
        """Giới hạn tần suất ghi log cảnh báo (tránh log cũng bị flood)."""
        now = now if now is not None else time.monotonic()
        if now - self._last_warn.get(node_id, 0.0) >= self.warn_interval:
            self._last_warn[node_id] = now
            return True
        return False
