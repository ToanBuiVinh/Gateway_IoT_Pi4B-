"""Điểm khởi chạy gateway (asyncio).

Chạy:  python -m src.main
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys

# Cho phép chạy trực tiếp `python src/main.py`
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import Config       # noqa: E402
from src.gateway import Gateway     # noqa: E402


def setup_logging(cfg: dict) -> None:
    level = getattr(logging, str(cfg.get("level", "INFO")).upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]
    log_file = cfg.get("file")
    if log_file:
        os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        handlers=handlers,
    )


async def _run(config: Config) -> None:
    gw = Gateway(config)
    loop = asyncio.get_running_loop()
    main_task = asyncio.current_task()

    # Bắt SIGINT/SIGTERM để dừng gọn gàng (systemd gửi SIGTERM khi stop/restart).
    def _stop() -> None:
        logging.getLogger("gateway").info("Nhan tin hieu dung")
        if main_task:
            main_task.cancel()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _stop)
        except NotImplementedError:
            pass  # một số nền tảng (Windows) không hỗ trợ

    try:
        await gw.run()
    except asyncio.CancelledError:
        pass


def main() -> int:
    parser = argparse.ArgumentParser(description="IoT Gateway cho Raspberry Pi 4B")
    parser.add_argument("--gateway", default="config/gateway.yaml")
    parser.add_argument("--nodes", default="config/nodes.yaml")
    args = parser.parse_args()

    config = Config(args.gateway, args.nodes)
    setup_logging(config.logging_cfg)

    try:
        asyncio.run(_run(config))
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
