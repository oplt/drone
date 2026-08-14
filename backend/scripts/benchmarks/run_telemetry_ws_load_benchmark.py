#!/usr/bin/env python3
"""Telemetry WebSocket fan-out load harness.

Simulates N connected clients with per-client bounded queues and measures how
many broadcast messages are dropped by ``TelemetryWebSocketManager._enqueue_latest``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[3]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from starlette.websockets import WebSocketState

from backend.infrastructure.messaging.websocket_publisher import Client, TelemetryWebSocketManager


@dataclass
class _SimClient:
    queue: asyncio.Queue[bytes] = field(default_factory=lambda: asyncio.Queue(maxsize=10))
    received: int = 0
    dropped_estimate: int = 0


class _FakeWebSocket:
    client_state = WebSocketState.CONNECTED


async def _run_benchmark(
    *,
    clients: int,
    messages: int,
    message_rate_hz: float,
    queue_size: int,
) -> dict[str, Any]:
    manager = TelemetryWebSocketManager()
    sim_clients: list[_SimClient] = []
    fake_sockets: list[_FakeWebSocket] = []

    for _ in range(clients):
        fake = _FakeWebSocket()
        sim = _SimClient(queue=asyncio.Queue(maxsize=queue_size))
        fake_sockets.append(fake)
        sim_clients.append(sim)
        manager._clients[fake] = Client(  # type: ignore[index]
            ws=fake,  # type: ignore[arg-type]
            q=sim.queue,
            task=asyncio.create_task(asyncio.sleep(3600)),
            connected_time=time.time(),
            org_id=1,
        )

    payload = json.dumps({"type": "telemetry", "data": {"position": {"lat": 1.0, "lon": 2.0}}}).encode(
        "utf-8"
    )
    interval_s = 1.0 / max(message_rate_hz, 0.001)
    sent = 0
    started = time.perf_counter()

    for _ in range(messages):
        await manager._local_broadcast(payload, org_id=1)
        sent += 1
        await asyncio.sleep(interval_s)

    # Drain queues without blocking — count what arrived vs what was sent per client.
    for sim in sim_clients:
        while True:
            try:
                sim.queue.get_nowait()
                sim.received += 1
            except asyncio.QueueEmpty:
                break
        sim.dropped_estimate = max(0, sent - sim.received)

    elapsed_s = time.perf_counter() - started
    total_received = sum(c.received for c in sim_clients)
    total_capacity = clients * queue_size
    drop_rate = 0.0
    if sent * clients:
        drop_rate = 1.0 - (total_received / float(sent * clients))

    return {
        "version": 1,
        "clients": clients,
        "messages_broadcast": sent,
        "message_rate_hz": message_rate_hz,
        "queue_size": queue_size,
        "elapsed_seconds": round(elapsed_s, 3),
        "total_client_receipts": total_received,
        "estimated_drop_rate": round(drop_rate, 4),
        "per_client": [
            {"received": c.received, "estimated_dropped": c.dropped_estimate}
            for c in sim_clients
        ],
        "notes": (
            "Drop rate is estimated from queue capacity and unreceived messages; "
            "matches TelemetryWebSocketManager._enqueue_latest coalescing behavior."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clients", type=int, default=32)
    parser.add_argument("--messages", type=int, default=500)
    parser.add_argument("--rate-hz", type=float, default=20.0)
    parser.add_argument("--queue-size", type=int, default=10)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("telemetry_ws_load_report.json"),
        help="JSON report path",
    )
    args = parser.parse_args(argv)

    report = asyncio.run(
        _run_benchmark(
            clients=max(1, args.clients),
            messages=max(1, args.messages),
            message_rate_hz=max(0.1, args.rate_hz),
            queue_size=max(1, args.queue_size),
        )
    )
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
