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
    result = {"mode": "public_view_read_only_start_subscription",
              "public_endpoint": ORIGIN, "data_event_received": False,
              "biological_origin_independently_verified": False,
              "stimulation_commands_sent": 0}
    try:
        payload, selection = fetch_selection()
        result["selection"] = selection
        if payload is None:
            result["status"] = "not_subscribed_no_eligible_controller"
            return result
        import socketio
        client = socketio.AsyncClient(reconnection=False, request_timeout=6)
        received = asyncio.Event()

        @client.on("data")
        async def got_data(data):
            if received.is_set():
                return
            try:
                if isinstance(data, (bytes, bytearray)):
                    serialized = bytes(data)
                else:
                    serialized = json.dumps(data, separators=(",", ":"), sort_keys=True, default=str).encode()
                result["frame"] = {
                    "payload_type": type(data).__name__,
                    "serialized_bytes": len(serialized),
                    "payload_sha256": hashlib.sha256(serialized).hexdigest(),
                    "top_level_keys": sorted(map(str, data.keys()))[:20] if isinstance(data, dict) else [],
                    "top_level_length": len(data) if isinstance(data, (dict, list, tuple)) else None,
                }
                result["data_event_received"] = True
            except Exception as exc:
                result["frame_parse_error"] = type(exc).__name__
            finally:
                received.set()

        @client.on("maintenance")
        async def on_maintenance(data):
            result["maintenance_event_received"] = True

        try:
            await asyncio.wait_for(client.connect(ORIGIN, transports=["websocket"], wait_timeout=6), timeout=9)
            # The only emitted event is the live viewer's published read-only
            # subscription; it is NOT a stimulus or experimental command.
            await client.emit("start", payload)
            try:
                await asyncio.wait_for(received.wait(), timeout=12)
            except asyncio.TimeoutError:
                pass
            result["status"] = "data_event_received" if result["data_event_received"] else "subscribed_no_data_event"
        finally:
            if client.connected:
                await client.disconnect()
    except Exception as exc:
        result["status"] = "public_subscription_failed"
        result["error"] = type(exc).__name__
        result["detail"] = str(exc)[:180]
    return result
