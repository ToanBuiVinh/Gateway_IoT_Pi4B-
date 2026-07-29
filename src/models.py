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
    metrics: Dict[str, Any]           # {"temperature": 25.4, "humidity": 60}
    ts: float = field(default_factory=time.time)  # epoch giây (UTC)

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False, separators=(",", ":"))

    def to_json_metrics(self) -> str:
        """Chỉ serialize phần metrics (để lưu vào cột riêng trong DB)."""
        return json.dumps(self.metrics, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def from_row(row: tuple) -> "Reading":
        # row = (id, node_id, gateway_id, ts, metrics_json, sent)
        return Reading(
            node_id=row[1],
            gateway_id=row[2],
            ts=row[3],
            metrics=json.loads(row[4]),
        )


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
