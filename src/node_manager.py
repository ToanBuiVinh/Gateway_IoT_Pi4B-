"""Quản lý 10 node: giải mã payload, kiểm tra hợp lệ, theo dõi trạng thái."""
from __future__ import annotations

import json
import logging
import time
from typing import Dict, Optional

from .models import NodeStatus, Reading

log = logging.getLogger("gateway.nodes")


class NodeManager:
    def __init__(self, gateway_id: str, node_defs: list[dict], offline_after: int = 120) -> None:
        self.gateway_id = gateway_id
        self.offline_after = offline_after
        self._defs: Dict[str, dict] = {n["id"]: n for n in node_defs}
        self._status: Dict[str, NodeStatus] = {
            n["id"]: NodeStatus(node_id=n["id"], name=n.get("name", "")) for n in node_defs
        }

    def known(self, node_id: str) -> bool:
        return node_id in self._defs

    def handle_payload(self, node_id: str, payload: bytes) -> Optional[Reading]:
        """Giải mã payload JSON từ node -> Reading (hoặc None nếu lỗi)."""
        status = self._status.get(node_id)
        if status is None:
            log.warning("Nhan du lieu tu node LA: %s (khong co trong nodes.yaml)", node_id)
            return None

        try:
            data = json.loads(payload.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            status.errors += 1
            log.warning("Node %s gui payload khong hop le: %s", node_id, exc)
            return None

        metrics = self._extract_metrics(node_id, data)
        if not metrics:
            status.errors += 1
            log.warning("Node %s: khong co metric hop le trong payload", node_id)
            return None

        # Cập nhật trạng thái
        status.messages += 1
        status.last_seen = time.time()
        status.online = True

        # Cho phép node tự gắn timestamp; nếu không có thì dùng giờ gateway.
        ts = data.get("ts")
        reading = Reading(
            node_id=node_id,
            gateway_id=self.gateway_id,
            metrics=metrics,
            ts=float(ts) if isinstance(ts, (int, float)) else time.time(),
        )
        return reading

    def _extract_metrics(self, node_id: str, data: dict) -> Dict[str, float]:
        """Lọc ra các metric đã khai báo và kiểm tra khoảng giá trị."""
        defs = self._defs[node_id].get("metrics", {})
        out: Dict[str, float] = {}
        for name, spec in defs.items():
            if name not in data:
                continue
            try:
                value = float(data[name])
            except (TypeError, ValueError):
                log.debug("Node %s: metric %s khong phai so", node_id, name)
                continue
            lo, hi = spec.get("min"), spec.get("max")
            if lo is not None and hi is not None and not (lo <= value <= hi):
                log.warning(
                    "Node %s: %s=%s ngoai khoang [%s,%s] -> bo qua",
                    node_id, name, value, lo, hi,
                )
                continue
            out[name] = value
        return out

    def refresh_offline(self) -> None:
        """Đánh dấu node OFFLINE nếu quá lâu không nhận dữ liệu."""
        now = time.time()
        for st in self._status.values():
            if st.online and (now - st.last_seen) > self.offline_after:
                st.online = False
                log.warning("Node %s (%s) chuyen sang OFFLINE", st.node_id, st.name)

    def snapshot(self) -> list[dict]:
        return [st.as_dict() for st in self._status.values()]
