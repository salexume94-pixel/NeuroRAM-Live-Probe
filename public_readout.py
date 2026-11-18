"""One read-only subscription to the publicly embedded FinalSpark live viewer.

Replicates the public client's 'start' subscription for a controller that the
public '/controllers' metadata marks online and not in maintenance.
Does not use Neuroplatform credentials, private API routes or stimulation.
"""
import asyncio
import hashlib
import json
from urllib.request import urlopen

ORIGIN = "https://livenp.finalspark.com"

def choose_public_selection(controllers, numbersample):
    if not isinstance(numbersample, int) or isinstance(numbersample, bool) or numbersample <= 0:
        return None, {"status": "invalid_or_empty_sample_window"}
    if not isinstance(controllers, list):
        return None, {"status": "invalid_controller_list"}
    for controller in controllers:
        if not isinstance(controller, dict):
            continue
        if controller.get("online") is not True or controller.get("maintenance") is not False:
            continue
        cid = controller.get("_id")
        if not isinstance(cid, (str, int)) or isinstance(cid, bool):
            continue
        channel_counts = controller.get("channels") or []
        if not isinstance(channel_counts, list):
            continue
        for mea_index, count in enumerate(channel_counts[:4]):
            if not isinstance(count, int) or count <= 0:
                continue
            layout = controller.get("electrode_layout") or []
            candidates = sorted(set(
                row["channel_index"] for row in layout
                if isinstance(row, dict)
                and row.get("mea_index") == mea_index
                and type(row.get("channel_index")) is int
                and 0 <= row["channel_index"] < count
            )) if isinstance(layout, list) else []
            if not candidates:
                candidates = list(range(min(count, 8)))
            channel_index = candidates[:8]
            payload = {"id_intan": cid, "mea_index": mea_index, "channel_index": channel_index}
            return payload, {
                "status": "eligible_public_view_controller_found",
                "controller_id_hash": hashlib.sha256(str(cid).encode()).hexdigest()[:12],
                "mea_index": mea_index,
                "channel_index": channel_index,
                "numbersample": numbersample,
            }
    return None, {"status": "no_online_nonmaintenance_controller"}

def fetch_selection(fetch=urlopen):
    records = {}
    for path in ("/sample", "/controllers"):
        with fetch(ORIGIN + path, timeout=10) as response:
            if response.status != 200:
                raise ValueError(f"public {path} returned HTTP {response.status}")
            records[path] = json.loads(response.read(1000000))
    return choose_public_selection(records["/controllers"].get("controllers"), records["/sample"].get("numbersample"))

async def subscribe_once():
    """Collect up to 3 consecutive public signal frames and persist the source values.

    The resulting gzip recording is ephemeral on Render's free filesystem.
    No stimulation or private data endpoints are used.
    """
    import gzip
    import math
    import os
    from datetime import datetime, timezone

    path = "/tmp/neuroram_public_signal.json.gz"
    result = {
        "mode": "public_view_read_only_start_subscription",
        "public_endpoint": ORIGIN,
        "data_event_received": False,
        "biological_origin_independently_verified": False,
        "stimulation_commands_sent": 0,
    }
    captures = []
    try:
        payload, selection = fetch_selection()
        result["selection"] = selection
        if payload is None:
            result["status"] = "not_subscribed_no_eligible_controller"
            return result
        import socketio
        client = socketio.AsyncClient(reconnection=False, request_timeout=6)
        done = asyncio.Event()
        samples_per_channel = selection["numbersample"]
        channel_count = len(payload["channel_index"])
        expected = channel_count * samples_per_channel

        @client.on("data")
        async def got_data(data):
            if len(captures) >= 3:
                return
            if not isinstance(data, list) or len(data) != expected:
                result["frame_validation_error"] = "wrong_type_or_sample_count"
                return
            if any(type(v) not in (int, float) or not math.isfinite(v) for v in data):
                result["frame_validation_error"] = "nonfinite_or_nonnumeric_values"
                return
            serialized = json.dumps(data, separators=(",", ":"), allow_nan=False).encode()
            digest = hashlib.sha256(serialized).hexdigest()
            groups = [data[i * samples_per_channel:(i + 1) * samples_per_channel]
                      for i in range(channel_count)]
            summary = {
                "received_utc": datetime.now(timezone.utc).isoformat(),
                "payload_sha256": digest,
                "sample_count": len(data),
                "serialized_bytes": len(serialized),
                "sample_min": round(min(data), 6),
                "sample_max": round(max(data), 6),
                "rms_source_units": round((sum(v * v for v in data) / len(data)) ** 0.5, 6),
                "nonzero_samples": sum(v != 0 for v in data),
                "channel_rms_source_units": [
                    round((sum(v*v for v in group) / len(group)) ** 0.5, 6)
                    for group in groups
                ],
            }
            captures.append({"summary": summary, "values": data})
            result["data_event_received"] = True
            if len(captures) >= 3:
                done.set()

        @client.on("maintenance")
        async def on_maintenance(data):
            result["maintenance_event_received"] = True

        try:
            await asyncio.wait_for(client.connect(ORIGIN, transports=["websocket"], wait_timeout=6), timeout=9)
            await client.emit("start", payload)  # Vendor public viewer's read-only event.
            try:
                await asyncio.wait_for(done.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass
        finally:
            if client.connected:
                await client.disconnect()

        result["frame_summaries"] = [frame["summary"] for frame in captures]
        result["frame_count"] = len(captures)
        result["distinct_frame_hashes"] = len(set(
            frame["summary"]["payload_sha256"] for frame in captures))
        if not captures:
            result["status"] = "subscribed_no_valid_data_event"
            return result
        evidence = {
            "source": "FinalSpark public live viewer read-only stream",
            "source_origin": ORIGIN,
            "biological_origin_independently_verified": False,
            "controller_id_hash": selection["controller_id_hash"],
            "mea_index": selection["mea_index"],
            "channels": selection["channel_index"],
            "samples_per_channel": samples_per_channel,
            "stimulation_commands_sent": 0,
            "frames": captures,
        }
        tmp_path = path + ".tmp"
        with gzip.open(tmp_path, "wt", encoding="utf-8", compresslevel=6) as f:
            json.dump(evidence, f, allow_nan=False, separators=(",", ":"))
        os.replace(tmp_path, path)
        result["recording_available"] = True
        result["recording_relative_url"] = "/public-recording.json.gz"
        result["recording_gzip_bytes"] = os.path.getsize(path)
        result["status"] = "public_signal_frames_recorded"
    except Exception as exc:
        result["status"] = "public_subscription_failed"
        result["error"] = type(exc).__name__
        result["detail"] = str(exc)[:180]
    return result
