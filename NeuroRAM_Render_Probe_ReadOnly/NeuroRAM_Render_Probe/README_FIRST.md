# NeuroRAM: Authorized Public Wetware Connectivity Probe

**Actual status (November 18, 2026): NOT CONNECTED TO LIVE WETWARE.** This release is a public, read-only network probe. The development container failed to resolve both vendor hostnames, and an attempted Render free-service creation returned `403 Forbidden`. No Render service was created, no biological recording was produced, and no stimulation was attempted.

## What it does

- Uses FinalSpark's two publicly published read-only LiveMEA endpoints:
  - https://livemeaservice.finalspark.com
  - https://livemeaservice2.alpvision.com
- Checks public `/check` and `/islive` HTTP status endpoints.
- Attempts **one** publicly exposed Socket.IO `livedata` packet per endpoint, with the vendor-documented `meaid=0` selection event. It sends no stimulation events.
- Validates the incoming 32- or 128-channel float32 packet size, checks for finite values and reports only statistics and an SHA-256 digest of the selected MEA. It does **not** store, upload, or publish raw signal values.
- Exposes JSON results at `/status`, a lightweight `/health`, and starts its probe once per service startup. All network attempts have time limits.
- **It cannot prove the origin or vitality of the neural preparation**, nor any biological memory or human-augmentation claim. Network provenance must be independently checked with the provider.

## Option A: Run locally on Windows

Install Python 3.10+, extract this folder, open PowerShell there, then run:

```powershell
py -3 -m pip install -r requirements.txt
$env:PORT = '8765'
py -3 neuroram_probe.py
```

Open http://localhost:8765/status to read the report. This machine must have internet access and permission to access the vendor's public read-only service. Results are emitted once after service launch. Close PowerShell to stop it.

## Option B: Free Render web service

The Render connector can list the user's workspace but service creation returned **403 Forbidden**. Because the provided Git-backed tools require a repository, deploy only when the account permits service creation:

1. Put the contents of this folder in a **new dedicated GitHub repository**, not in an existing unrelated game or application project.
2. In the Render Dashboard, link that repository for a new Web Service, choose a **free** plan if actually available, Python runtime, build command `pip install -r requirements.txt`, start command `python neuroram_probe.py`.
3. Set **Auto Deploy off**. Do not attach databases or paid storage. Review any billing or account confirmation before submitting.
4. Inspect the Render service logs for `NEURORAM_PROBE_COMPLETE` and visit `https://<your-service>.onrender.com/status` to see metadata. Avoid treating free-tier availability or the external live service as guaranteed.
5. Do not publish the resulting dashboard/status URL if you prefer keeping observational metadata private. The endpoint itself does not require authentication.

The `render.yaml` is included as an optional deployment description, but the README's manual Dashboard steps are sufficient.

## Expected outcomes

- `frame_received_origin_not_independently_verified`: the designated public endpoint delivered a packet consistent with the published live format. This supports network acquisition, but not biological provenance or stored memory.
- `connection_or_frame_failed`: network, origin/TLS, Socket.IO handshake, or stream timeout problem. This does **not** prove the laboratory's service is offline.
- `missing_dependency`: Python Socket.IO dependency was not installed.
- JSON `http` error entries: independent HTTP availability diagnostics.

No access controls are bypassed. Do not use private lab endpoints, others' credentials, undocumented commands, or electrical stimulation. For controlled training experiments, obtain explicit approval from FinalSpark or Cortical Labs.

Official vendor code: https://github.com/FinalSpark-np/LiveMEA and https://github.com/FinalSpark-np/LiveMEA_ts
