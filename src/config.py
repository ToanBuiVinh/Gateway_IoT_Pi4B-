"""Đọc và kiểm tra file cấu hình YAML."""
from __future__ import annotations

import os
from typing import Any, Dict

import yaml


def load_yaml(path: str) -> Dict[str, Any]:
    """Đọc một file YAML thành dict."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Khong tim thay file cau hinh: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


class Config:
    """Gom cấu hình gateway + danh sách node."""

    def __init__(self, gateway_path: str, nodes_path: str) -> None:
        self.gateway = load_yaml(gateway_path)
        nodes_doc = load_yaml(nodes_path)
        self.nodes = nodes_doc.get("nodes", [])
        self._validate()

    def _validate(self) -> None:
        if "gateway" not in self.gateway:
            raise ValueError("gateway.yaml thieu muc 'gateway'")
        if not self.nodes:
            raise ValueError("nodes.yaml khong co node nao")
        ids = [n.get("id") for n in self.nodes]
        if None in ids:
            raise ValueError("Co node thieu truong 'id'")
        if len(ids) != len(set(ids)):
            raise ValueError("Co node bi trung 'id'")

    # --- Truy cập nhanh (kèm giá trị mặc định an toàn) ---
    @property
    def gateway_id(self) -> str:
        return self.gateway["gateway"]["id"]

    @property
    def local_broker(self) -> Dict[str, Any]:
        return self.gateway["local_broker"]

    @property
    def cloud(self) -> Dict[str, Any]:
        return self.gateway.get("cloud", {})

    @property
    def storage(self) -> Dict[str, Any]:
        return self.gateway.get("storage", {})

    @property
    def pipeline(self) -> Dict[str, Any]:
        return self.gateway.get("pipeline", {})

    @property
    def store_forward(self) -> Dict[str, Any]:
        return self.gateway.get("store_forward", {})

    @property
    def network_monitor(self) -> Dict[str, Any]:
        return self.gateway.get("network_monitor", {})

    @property
    def maintenance(self) -> Dict[str, Any]:
        return self.gateway.get("maintenance", {})

    @property
    def logging_cfg(self) -> Dict[str, Any]:
        return self.gateway.get("logging", {})

    def enabled_nodes(self) -> list[dict]:
        return [n for n in self.nodes if n.get("enabled", True)]
