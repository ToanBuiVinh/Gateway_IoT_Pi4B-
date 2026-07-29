"""Các kiểu dữ liệu dùng chung."""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Dict


@dataclass
class Reading:
    """Một bản ghi đo được từ node."""

    node_id: str
    gateway_id: str
    metrics: Dict[str, Any]                         # {"temperature": 25.4, ...}
    ts: float = field(default_factory=time.time)    # epoch giây (UTC)

    def to_cloud_dict(self, buffered: bool = False) -> Dict[str, Any]:
        """Dạng dict để publish lên cloud.

        buffered=True gắn cờ để cloud biết đây là dữ liệu lịch sử gửi bù.
        """
        d: Dict[str, Any] = {
            "node_id": self.node_id,
            "gateway_id": self.gateway_id,
            "ts": self.ts,
            "metrics": self.metrics,
        }
        if buffered:
            d["buffered"] = True
        return d

    def payload_json(self) -> str:
        """JSON gốc (chưa gắn cờ buffered) để lưu vào SQLite."""
        return json.dumps(self.to_cloud_dict(False), ensure_ascii=False,
                          separators=(",", ":"))


@dataclass
class NodeStatus:
    """Trạng thái theo dõi realtime của một node."""

    node_id: str
    name: str = ""
    online: bool = False
    last_seen: float = 0.0
    messages: int = 0
    errors: int = 0

    def as_dict(self) -> Dict[str, Any]:
        return asdict(self)
