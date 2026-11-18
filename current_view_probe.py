"""Inspect FinalSpark's currently published public live viewer (read-only).

This checks public HTML only. An HTTP 200 is NOT proof that living neurons
are connected, nor is a JavaScript frontend proof of incoming electrode data.
No authentication, stimulation, or private endpoints are accessed.
"""
from datetime import datetime, timezone
from hashlib import sha256
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse
from urllib.request import urlopen

PUBLIC_VIEW_URL = "https://livenp.finalspark.com/client/"
MAX_HTML_BYTES = 200000

class _ScriptReferences(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() != "script":
            return
        src = dict(attrs).get("src")
        if not src:
            return
        url = urljoin(PUBLIC_VIEW_URL, src)
        parsed = urlparse(url)
        if parsed.scheme == "https" and parsed.hostname == "livenp.finalspark.com":
            if url not in self.scripts and len(self.scripts) < 12:
                self.scripts.append(url)

def diagnose_public_view(fetch=urlopen):
    result = {
        "url": PUBLIC_VIEW_URL,
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "kind": "official_public_web_view_not_live_signal",
        "frame_received": False,
        "biological_origin_verified": False,
    }
    try:
        with fetch(PUBLIC_VIEW_URL, timeout=10) as response:
            body = response.read(MAX_HTML_BYTES)
            parser = _ScriptReferences()
            parser.feed(body.decode("utf-8", errors="replace"))
            result.update({
                "http_code": response.status,
                "content_type": response.headers.get("Content-Type", ""),
                "html_bytes_read": len(body),
                "html_sha256": sha256(body).hexdigest(),
                "same_origin_script_urls": parser.scripts,
            })
    except Exception as exc:
        result["error"] = type(exc).__name__
        result["error_detail"] = str(exc)[:180]
    return result
