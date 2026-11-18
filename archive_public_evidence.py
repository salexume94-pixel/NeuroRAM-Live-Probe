"""Archive and independently validate NeuroRAM's first public live signal capture."""
import gzip
import hashlib
import json
import math
import os
import time
from pathlib import Path
from urllib.request import Request, urlopen

SOURCE = "https://neuroram-live-probe.onrender.com/public-recording.json.gz"
OUT = Path("evidence")

def verify_recording(compressed):
    data = json.loads(gzip.decompress(compressed))
    if data.get("source_origin") != "https://livenp.finalspark.com":
        raise ValueError("Unexpected source")
    if data.get("stimulation_commands_sent") != 0:
        raise ValueError("Stimulation must be zero")
    channels = data.get("channels")
    samples_per_channel = data.get("samples_per_channel")
    frames = data.get("frames")
    if not isinstance(channels, list) or len(channels) != 8 or samples_per_channel != 1600:
        raise ValueError("Unexpected recording geometry")
    if not isinstance(frames, list) or len(frames) != 3:
        raise ValueError("Expected exactly three captured frames")
    summaries = []
    for frame in frames:
        values = frame["values"]
        summary = frame["summary"]
        if len(values) != 12800 or not all(type(x) in (int, float) and math.isfinite(x) for x in values):
            raise ValueError("Invalid sample values")
        canonical = json.dumps(values, separators=(",", ":"), allow_nan=False).encode()
        digest = hashlib.sha256(canonical).hexdigest()
        if digest != summary.get("payload_sha256"):
            raise ValueError("Frame SHA256 mismatch")
        if all(x == 0 for x in values):
            raise ValueError("All-zero frame")
        summaries.append({"received_utc": summary["received_utc"],
                          "samples": len(values), "sha256": digest,
                          "min": min(values), "max": max(values)})
    if len({frame["sha256"] for frame in summaries}) != len(summaries):
        raise ValueError("Repeated frame hashes")
    return {
        "source_url": SOURCE,
        "source_type": "vendor_public_live_view_stream",
        "compressed_sha256": hashlib.sha256(compressed).hexdigest(),
        "compressed_bytes": len(compressed),
        "frames_validated": 3,
        "total_samples": 38400,
        "distinct_frame_hashes": 3,
        "electrode_channels": channels,
        "biological_origin_independently_verified": False,
        "memory_retention_demonstrated": False,
        "frames": summaries,
    }

def main():
    OUT.mkdir(exist_ok=True)
    last_error = None
    for attempt in range(3):
        try:
            with urlopen(Request(SOURCE, headers={"User-Agent": "NeuroRAM-Archive-Validation/1.0"}), timeout=120) as response:
                compressed = response.read(4000000)
            report = verify_recording(compressed)
            (OUT / "public_live_signal.json.gz").write_bytes(compressed)
            (OUT / "verification.json").write_text(json.dumps(report, indent=2) + "\n")
            print("NEURORAM_ARCHIVE_VERIFIED", json.dumps({
                "frames": report["frames_validated"],
                "samples": report["total_samples"],
                "compressed_sha256": report["compressed_sha256"]}, sort_keys=True))
            return
        except Exception as exc:
            last_error = repr(exc)
            if attempt < 2:
                time.sleep(10)
    raise RuntimeError(f"Could not archive and validate public recording: {last_error}")

if __name__ == "__main__":
    main()
