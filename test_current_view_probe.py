import unittest
from current_view_probe import PUBLIC_VIEW_URL, _ScriptReferences, diagnose_public_view, inspect_public_script

class FakeResponse:
    status = 200
    headers = {"Content-Type": "text/html"}
    def __init__(self, body):
        self.body = body
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self, size):
        return self.body[:size]

class PublicViewTests(unittest.TestCase):
    def test_published_page_url_is_https(self):
        self.assertEqual(PUBLIC_VIEW_URL, "https://livenp.finalspark.com/client/")

    def test_extract_only_same_origin_scripts(self):
        p = _ScriptReferences()
        p.feed('<script src="/client/app.js"></script><script src="https://elsewhere.example/hidden.js"></script><script src="app2.js"></script>')
        self.assertEqual(p.scripts, ["https://livenp.finalspark.com/client/app.js", "https://livenp.finalspark.com/client/app2.js"])

    def test_success_is_not_neural_evidence(self):
        calls = []
        def fake_fetch(url, timeout):
            calls.append((url, timeout))
            return FakeResponse(b'<script src="assets/main.js"></script>')
        data = diagnose_public_view(fake_fetch)
        self.assertEqual(calls, [(PUBLIC_VIEW_URL, 10)])
        self.assertEqual(data["http_code"], 200)
        self.assertEqual(data["same_origin_script_urls"], ["https://livenp.finalspark.com/client/assets/main.js"])
        self.assertFalse(data["frame_received"])
        self.assertFalse(data["biological_origin_verified"])

    def test_network_failure_is_explicit(self):
        def fake_fetch(url, timeout):
            raise OSError("DNS unavailable")
        data = diagnose_public_view(fake_fetch)
        self.assertEqual(data["error"], "OSError")
        self.assertFalse(data["frame_received"])


class PublicScriptTests(unittest.TestCase):
    def test_rejects_unlinked_or_foreign_domains(self):
        result = inspect_public_script("https://untrusted.example/client/assets/evil.js")
        self.assertEqual(result["error"], "not_a_public_linked_viewer_asset")
        self.assertFalse(result["frame_received"])

    def test_public_script_diagnostic_is_not_biological_recording(self):
        js = b'const stream = "https://livemeaservice.finalspark.com/socket.io/"; const connector = new WebSocket("wss://livenp.finalspark.com");'
        result = inspect_public_script("https://livenp.finalspark.com/client/assets/main.js", lambda url, timeout: FakeResponse(js))
        self.assertEqual(result["http_code"], 200)
        self.assertIn("livemeaservice.finalspark.com", result["public_provider_hostnames"])
        self.assertTrue(result["connection_hints"]["websocket"])
        self.assertFalse(result["frame_received"])
        self.assertFalse(result["biological_origin_verified"])

if __name__ == "__main__":
    unittest.main()
