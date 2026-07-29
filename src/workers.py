"""Các coroutine worker của pipeline asyncio.

    ingest_queue ──► ingestion_worker ──(online)──► CloudPublisher
                                       └─(offline/fail)─► db_queue
    db_queue ─────► database_worker ──(batch)──► SQLite (telemetry_buffer)
    (khi có mạng) store_and_forward_worker ─► đọc buffer FIFO ─► CloudPublisher
    disk_cleanup_worker ─► dọn đĩa định kỳ
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any, Dict

from .db import Database
from .node_manager import NodeManager
from .state import AppState

if TYPE_CHECKING:
    # Chỉ import lúc type-check: CloudPublisher kéo theo paho, còn lõi worker
    # (ingestion/batching/store-forward) không cần paho để chạy/kiểm thử.
    from .cloud_publisher import CloudPublisher

log = logging.getLogger("gateway.workers")


class Backoff:
    """Exponential backoff: start, x2 mỗi lần, trần maximum."""

    def __init__(self, start: float, maximum: float) -> None:
        self.start = start
        self.max = maximum
        self.cur = start

    def next(self) -> float:
        v = self.cur
        self.cur = min(self.cur * 2, self.max)
        return v

    def reset(self) -> None:
        self.cur = self.start


# ======================================================================
# 1) INGESTION WORKER: đọc RAM queue, online->publish thẳng, offline->DB
# ======================================================================
async def ingestion_worker(
    state: AppState,
    ingest_queue: "asyncio.Queue",
    db_queue: "asyncio.Queue",
    publisher: CloudPublisher,
    nodes: NodeManager,
) -> None:
    log.info("Ingestion worker: san sang")
    while True:
        node_id, payload, recv_ts = await ingest_queue.get()
        try:
            reading = nodes.handle_payload(node_id, payload)
            if reading is None:
                state.stats.dropped += 1
                continue
            state.stats.received += 1

            sent = False
            if state.is_online:
                sent = await publisher.publish(reading.to_cloud_dict(False))
                if sent:
                    state.stats.published_direct += 1

            if not sent:
                # Offline hoặc gửi trực tiếp thất bại -> định tuyến về Database Worker.
                await db_queue.put((reading.node_id, reading.payload_json(), recv_ts))
        finally:
            ingest_queue.task_done()


# ======================================================================
# 2) DATABASE WORKER: gom lô (10-20 tin hoặc 3s) -> 1 transaction
# ======================================================================
async def database_worker(
    cfg: Dict[str, Any],
    db: Database,
    db_queue: "asyncio.Queue",
    state: AppState,
) -> None:
    batch_min = int(cfg.get("db_batch_min", 10))
    batch_max = int(cfg.get("db_batch_max", 20))
    timeout = float(cfg.get("db_batch_timeout_sec", 3))
    loop = asyncio.get_running_loop()
    log.info("Database worker: batch %d-%d hoac %.1fs", batch_min, batch_max, timeout)

    while True:
        # Chờ tin đầu tiên (chặn cho tới khi có dữ liệu offline).
        first = await db_queue.get()
        batch = [first]
        db_queue.task_done()

        deadline = loop.time() + timeout
        while len(batch) < batch_max:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                item = await asyncio.wait_for(db_queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            batch.append(item)
            db_queue.task_done()
            # Đủ tối thiểu và hàng đợi tạm rỗng -> ghi ngay, không chờ hết 3s.
            if len(batch) >= batch_min and db_queue.empty():
                break

        written = await asyncio.to_thread(db.insert_batch, batch)
        state.stats.buffered += written
        log.info("Da buffer %d ban ghi (1 transaction) | cho gui: %d",
                 written, await asyncio.to_thread(db.pending_count))


# ======================================================================
# 3) STORE-AND-FORWARD WORKER: đẩy bù buffer khi có mạng lại
# ======================================================================
async def store_and_forward_worker(
    cfg: Dict[str, Any],
    db: Database,
    publisher: CloudPublisher,
    state: AppState,
) -> None:
    chunk = int(cfg.get("chunk_size", 50))
    throttle = float(cfg.get("throttle_ms", 50)) / 1000.0
    idle = float(cfg.get("idle_recheck_sec", 10))
    backoff = Backoff(
        float(cfg.get("backoff_start_sec", 2)),
        float(cfg.get("backoff_max_sec", 300)),
    )
    log.info("Store-and-Forward worker: chunk=%d throttle=%.0fms", chunk, throttle * 1000)

    while True:
        # Ngủ hoàn toàn khi offline (tiết kiệm CPU).
        await state.online.wait()

        rows = await asyncio.to_thread(db.fetch_pending, chunk)
        if not rows:
            backoff.reset()
            await asyncio.sleep(idle)      # hết buffer -> rà lại sau
            continue

        sent_ids = []
        for row_id, _node_id, payload_json, _created_at in rows:
            if not state.is_online:
                break                      # rớt mạng giữa chừng -> dừng
            payload = json.loads(payload_json)
            payload["buffered"] = True     # cờ báo cloud: dữ liệu gửi bù
            ok = await publisher.publish(payload)
            if not ok:
                break
            sent_ids.append(row_id)
            state.stats.forwarded += 1
            await asyncio.sleep(throttle)  # rate limiting giữa các bản ghi

        if sent_ids:
            await asyncio.to_thread(db.mark_sent, sent_ids)  # cập nhật sau PUBACK

        if len(sent_ids) < len(rows):
            # Có lỗi/rớt mạng -> backoff tăng dần trước khi thử lại.
            wait = backoff.next()
            log.warning("SF: gui %d/%d, backoff %.0fs", len(sent_ids), len(rows), wait)
            await asyncio.sleep(wait)
        else:
            backoff.reset()
            await asyncio.sleep(throttle)  # nghỉ ngắn giữa các lô


# ======================================================================
# 4) DISK CLEANUP WORKER: dọn đĩa khi vượt ngưỡng
# ======================================================================
async def disk_cleanup_worker(cfg: Dict[str, Any], db: Database) -> None:
    interval = float(cfg.get("disk_check_interval_sec", 300))
    threshold = float(cfg.get("disk_threshold_pct", 85))
    batch = int(cfg.get("cleanup_delete_batch", 5000))
    log.info("Disk cleanup worker: nguong %.0f%%, moi %.0fs", threshold, interval)

    while True:
        await asyncio.sleep(interval)
        used = await asyncio.to_thread(db.disk_usage_percent)
        if used < threshold:
            continue
        log.warning("Dia %.1f%% >= %.0f%% -> don du lieu da gui", used, threshold)
        deleted = await asyncio.to_thread(db.cleanup_sent, batch)
        await asyncio.to_thread(db.checkpoint)
        log.info("Da xoa %d ban ghi da dong bo, gop WAL", deleted)
