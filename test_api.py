import json
import tempfile
import unittest
import urllib.error
import urllib.request

from server import RixPanelServer


class ApiTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.server = RixPanelServer(self.temp_dir.name)
        self.server.start()
        self.base_url = self.server.base_url

    def tearDown(self):
        self.server.stop()
        self.temp_dir.cleanup()

    def request(self, method, path, payload=None, headers=None, raw_body=None):
        body = raw_body
        request_headers = dict(headers or {})
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            request_headers.setdefault("Content-Type", "application/json")
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            response = urllib.request.urlopen(request, timeout=3)
        except urllib.error.HTTPError as exc:
            response = exc
        response_body = response.read()
        parsed = None
        if response_body:
            try:
                parsed = json.loads(response_body)
            except json.JSONDecodeError:
                pass
        return response.status, parsed, response_body, response.headers


class HealthEndpointTests(ApiTestCase):
    def test_health_reports_ready_without_cors_or_secrets(self):
        status, payload, _, headers = self.request("GET", "/api/health")

        self.assertEqual(status, 200)
        self.assertEqual(payload, {"service": "rixpanel", "status": "ok", "version": 1})
        self.assertIsNone(headers.get("Access-Control-Allow-Origin"))
        self.assertIn("application/json", headers["Content-Type"])


class GenerateEndpointTests(ApiTestCase):
    def valid_payload(self):
        return {
            "name": "تنظیم تست",
            "server": "vpn.example.org",
            "port": 443,
            "uuid": "123e4567-e89b-12d3-a456-426614174000",
            "sni": "vpn.example.org",
            "host": "panel.example.org",
            "path": "/rix-ws",
            "tls": True,
            "allow_insecure": 0,
            "remark": "توضیح تست",
        }

    def test_generate_persists_and_returns_complete_artifacts(self):
        status, payload, _, _ = self.request("POST", "/api/v1/configs/generate", self.valid_payload())

        self.assertEqual(status, 201)
        self.assertEqual(payload["version"], 1)
        self.assertEqual(len(payload["id"]), 36)
        self.assertTrue(payload["created_at"].endswith("Z"))
        self.assertEqual(payload["vless_uri"], "vless://123e4567-e89b-12d3-a456-426614174000@vpn.example.org:443?encryption=none&security=tls&type=ws&host=panel.example.org&path=%2Frix-ws&sni=vpn.example.org&allowInsecure=0#%D8%AA%D9%86%D8%B8%DB%8C%D9%85%20%D8%AA%D8%B3%D8%AA")
        self.assertEqual(payload["allow_insecure"], 0)

        stored = json.loads((self.server.storage_dir / "configs.json").read_text("utf-8"))
        self.assertEqual([item["id"] for item in stored["configs"]], [payload["id"]])

    def test_generate_rejects_invalid_uuid_without_persisting(self):
        invalid = self.valid_payload()
        invalid["uuid"] = "not-a-uuid"

        status, payload, _, _ = self.request("POST", "/api/v1/configs/generate", invalid)

        self.assertEqual(status, 422)
        self.assertEqual(payload["error"], "validation_error")
        self.assertIn("uuid", payload["message"])
        self.assertFalse((self.server.storage_dir / "configs.json").exists())

    def test_generate_rejects_oversized_body(self):
        status, payload, _, _ = self.request(
            "POST",
            "/api/v1/configs/generate",
            raw_body=b"x" * (64 * 1024 + 1),
            headers={"Content-Type": "application/json"},
        )

        self.assertEqual(status, 422)
        self.assertEqual(payload["error"], "validation_error")
        self.assertIn("۶۴ کیلوبایت", payload["message"])

    def test_generate_rejects_insecure_opt_out(self):
        invalid = self.valid_payload()
        invalid["allow_insecure"] = 1

        status, payload, _, _ = self.request("POST", "/api/v1/configs/generate", invalid)

        self.assertEqual(status, 422)
        self.assertEqual(payload["error"], "validation_error")
        self.assertIn("allow_insecure", payload["message"])


class ConfigLifecycleEndpointTests(ApiTestCase):
    def valid_payload(self, name="اتصال اول"):
        return {
            "name": name,
            "server": "vpn.example.org",
            "port": 443,
            "uuid": "123e4567-e89b-12d3-a456-426614174000",
            "sni": "vpn.example.org",
            "host": "panel.example.org",
            "path": "/rix-ws",
            "tls": True,
            "allow_insecure": 0,
            "remark": "",
        }

    def create(self):
        status, payload, _, _ = self.request("POST", "/api/v1/configs/generate", self.valid_payload())
        self.assertEqual(status, 201)
        return payload

    def test_list_and_get_return_persisted_config(self):
        created = self.create()

        list_status, listed, _, _ = self.request("GET", "/api/v1/configs")
        get_status, fetched, _, _ = self.request("GET", f"/api/v1/configs/{created['id']}")

        self.assertEqual(list_status, 200)
        self.assertEqual(listed, {"version": 1, "configs": [created]})
        self.assertEqual(get_status, 200)
        self.assertEqual(fetched, created)

    def test_get_unknown_config_returns_404(self):
        unknown_id = "00000000-0000-4000-8000-000000000000"

        status, payload, _, _ = self.request("GET", f"/api/v1/configs/{unknown_id}")

        self.assertEqual(status, 404)
        self.assertEqual(payload["error"], "not_found")

    def test_delete_removes_config_and_returns_no_content(self):
        created = self.create()

        delete_status, _, body, _ = self.request("DELETE", f"/api/v1/configs/{created['id']}")
        list_status, listed, _, _ = self.request("GET", "/api/v1/configs")

        self.assertEqual(delete_status, 204)
        self.assertEqual(body, b"")
        self.assertEqual(listed, {"version": 1, "configs": []})


class SubscriptionEndpointTests(ApiTestCase):
    def test_subscription_returns_plain_base64_vless_uri(self):
        payload = {
            "name": "اشتراک تست",
            "server": "vpn.example.org",
            "port": 443,
            "uuid": "123e4567-e89b-12d3-a456-426614174000",
            "sni": "vpn.example.org",
            "host": "panel.example.org",
            "path": "/rix-ws",
            "tls": True,
            "allow_insecure": 0,
            "remark": "",
        }
        status, created, _, _ = self.request("POST", "/api/v1/configs/generate", payload)

        self.assertEqual(status, 201)
        subscription_status, body, decoded_body, headers = self.request(
            "GET", f"/api/v1/subscriptions/{created['id']}"
        )

        self.assertEqual(subscription_status, 200)
        self.assertIsNone(body)
        self.assertEqual(decoded_body, created["subscription_base64"].encode("ascii"))
        self.assertEqual(headers["Content-Type"], "text/plain; charset=utf-8")
        self.assertIn("attachment", headers["Content-Disposition"])
        self.assertIn(".txt", headers["Content-Disposition"])


if __name__ == "__main__":
    unittest.main()
