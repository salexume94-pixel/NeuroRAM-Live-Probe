"""NeuroRAM FinalSpark public read-only network probe.

Fetches public status and attempts one 32-channel buffer from each vendor-
published LiveMEA Socket.IO endpoint. Never sends stimulation commands,
credentialed requests or writes data to the provider. Reports only receipt
metadata, not biological memory or verified culture origin.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import os
import socket
import struct
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import URLError, HTTPError
from urllib.request import urlopen

HOSTS = (
    "https://livemeaservice.finalspark.com",
    "https://livemeaservice2.alpvision.com",
)
FRAME_BYTES = 32 * 4096 * 4
RESULT = {
    "project": "NeuroRAM",
    "mode": "public_read_only_probe",
    "state": "starting",
    "provider": "FinalSpark LiveMEA",
    "access_authorized": "public_unauthenticated_endpoint_only",
    "biological_origin_verified": False,
    "human_memory_augmented": False,
    "stimulation_commands_sent": 0,
    "results": [],
}
LOCK = threading.Lock()


def utc():
    return datetime.now(timezone.utc).isoformat()


def check_http(host):
    info = {}
    for endpoint in ("/check", "/islive"):
        try:
            with urlopen(host + endpoint, timeout=7) as response:
                raw = response.read(2048).decode("utf-8", errors="replace")
                info[endpoint] = {"http_code": response.status, "body_excerpt": raw[:150]}
        except Exception as e:
            info[endpoint] = {"error": type(e).__name__, "detail": str(e)[:180]}
    return info


def analyze_frame(raw, chosen_mea=1):
    if not isinstance(raw, (bytes, bytearray, memoryview)):
        raise ValueError("Unexpected non-binary signal payload")
    n = len(raw)
    if n not in (FRAME_BYTES, 4 * FRAME_BYTES):
        raise ValueError(f"Unexpected wire frame length {n}")
    wire_channels = n // (4096 * 4)
    offset = 0 if wire_channels == 32 else (chosen_mea - 1) * FRAME_BYTES
    block = bytes(raw[offset:offset + FRAME_BYTES])
    if len(block) != FRAME_BYTES:
        raise ValueError("Selected MEA block truncated")
    values = struct.unpack("<131072f", block)
    if not all(math.isfinite(v) for v in values):
        raise ValueError("Nonfinite signal samples")
    count = len(values)
    rms = math.sqrt(sum(v * v for v in values) / count)
    return {
        "source": "vendor_published_public_stream",
        "status": "frame_received_origin_not_independently_verified",
        "wire_channels": wire_channels,
        "saved_channels": 32,
        "samples_per_channel": 4096,
        "frame_bytes": len(block),
        "sha256": hashlib.sha256(block).hexdigest(),
        "rms_source_units": round(rms, 6),
        "min_source_units": round(min(values), 6),
        "max_source_units": round(max(values), 6),
        "host_receipt_utc": utc(),
        "independent_biological_verification": False,
    }


async def try_socket(host):
    try:
        import socketio
    except ImportError:
        return {"status": "missing_dependency", "detail": "python-socketio package unavailable"}
    s = socketio.AsyncClient(reconnection=False, request_timeout=6)
    result = asyncio.get_running_loop().create_future()

    @s.event
    async def connect():
        await s.emit("meaid", 0)  # Vendor-published, zero-based MEA selection only.

    @s.on("livedata")
    async def on_data(data):
        if result.done():
            return
        try:
            payload = data.get("buffer") if isinstance(data, dict) else None
            result.set_result(analyze_frame(payload, 1))
        except Exception as e:
            result.set_exception(e)

    try:
        await asyncio.wait_for(s.connect(host, transports=["websocket"], wait_timeout=6), timeout=9)
        return await asyncio.wait_for(result, timeout=15)
    except Exception as e:
        return {"status": "connection_or_frame_failed", "error": type(e).__name__, "detail": str(e)[:200]}
    finally:
        if s.connected:
            await s.disconnect()


async def probe_public_view_socket():
    """One public, unauthenticated Socket.IO handshake; no emissions or commands."""
    url = "https://livenp.finalspark.com"
    try:
        import socketio
    except ImportError:
        return {"url": url, "status": "missing_dependency", "signal_verified": False}
    client = socketio.AsyncClient(reconnection=False, request_timeout=6)
    events = []

    @client.on("*")
    async def observe_event(event, *args):
        # Only store event names; never log or retain unknown payloads.
        if len(events) < 16:
            events.append(str(event)[:64])

    try:
        await asyncio.wait_for(client.connect(url, transports=["websocket"], wait_timeout=6), timeout=9)
        await client.sleep(3)
        return {"url": url, "status": "public_socketio_handshake_completed",
                "event_names": sorted(set(events)), "signal_verified": False,
                "biological_origin_verified": False}
    except Exception as exc:
        return {"url": url, "status": "public_socketio_handshake_failed",
                "error": type(exc).__name__, "detail": str(exc)[:180],
                "signal_verified": False, "biological_origin_verified": False}
    finally:
        if client.connected:
            await client.disconnect()


def do_probe():
    print("NEURORAM_PROBE_BEGIN", utc(), flush=True)
    from current_view_probe import diagnose_public_view
    public_view = diagnose_public_view()
    with LOCK:
        RESULT["public_view"] = public_view
    print("NEURORAM_PUBLIC_VIEW", json.dumps(public_view, sort_keys=True), flush=True)
    if public_view.get("same_origin_script_urls"):
        from current_view_probe import inspect_public_script
        public_script = inspect_public_script(public_view["same_origin_script_urls"][0])
        with LOCK:
            RESULT["public_script"] = public_script
        print("NEURORAM_PUBLIC_SCRIPT", json.dumps(public_script, sort_keys=True), flush=True)
        if public_script.get("connection_hints", {}).get("socket.io"):
            public_socket = asyncio.run(probe_public_view_socket())
            with LOCK:
                RESULT["public_view_socket"] = public_socket
            print("NEURORAM_PUBLIC_VIEW_SOCKET", json.dumps(public_socket, sort_keys=True), flush=True)
    for host in HOSTS:
        record = {"endpoint": host, "http": check_http(host), "attempted_at_utc": utc()}
        try:
            record["socketio"] = asyncio.run(try_socket(host))
        except Exception as e:
            record["socketio"] = {"status": "probe_error", "error": type(e).__name__, "detail": str(e)[:200]}
        with LOCK:
            RESULT["results"].append(record)
        # No bytes of biological voltage signal are logged or exposed.
        print("NEURORAM_ENDPOINT_RESULT", json.dumps(record, sort_keys=True), flush=True)
    with LOCK:
        RESULT["state"] = "complete"
        RESULT["finished_utc"] = utc()
    print("NEURORAM_PROBE_COMPLETE", flush=True)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path not in ("/", "/status", "/health"):
            self.send_error(404)
            return
        with LOCK:
            data = dict(RESULT)
            data["results"] = list(RESULT["results"])
        if self.path == "/health":
            data = {"service": "ok", "probe_state": data["state"]}
        payload = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        pass


def main():
    port = int(os.getenv("PORT", "10000"))
    with LOCK:
        RESULT["state"] = "running"
        RESULT["started_utc"] = utc()
    threading.Thread(target=do_probe, daemon=True).start()
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print(f"NEURORAM_HTTP_BOUND 0.0.0.0:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
