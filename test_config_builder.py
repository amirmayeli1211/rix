import base64
import unittest
from urllib.parse import parse_qs, unquote, urlparse

from config_builder import generate_artifacts


class ConfigBuilderTests(unittest.TestCase):
    def test_builds_vless_ws_artifacts_and_subscription(self):
        user_uuid = "123e4567-e89b-12d3-a456-426614174000"

        result = generate_artifacts(
            {
                "name": "خانه",
                "server": "example.com",
                "port": 443,
                "uuid": user_uuid,
                "sni": "example.com",
                "host": "cdn.example.com",
                "path": "/panel-ws",
                "tls": True,
                "allow_insecure": 0,
                "remark": "اتصال اصلی",
            }
        )

        outbound = result["config"]["outbounds"][0]
        user = outbound["settings"]["vnext"][0]["users"][0]
        stream = outbound["streamSettings"]
        self.assertEqual(user["id"], user_uuid)
        self.assertEqual(user["encryption"], "none")
        self.assertEqual(stream["network"], "ws")
        self.assertEqual(stream["security"], "tls")
        self.assertEqual(stream["tlsSettings"], {"serverName": "example.com", "allowInsecure": False})
        self.assertEqual(stream["wsSettings"], {"path": "/panel-ws", "headers": {"Host": "cdn.example.com"}})

        parsed = urlparse(result["vless_uri"])
        self.assertEqual(parsed.scheme, "vless")
        self.assertEqual(parsed.hostname, "example.com")
        self.assertEqual(parsed.port, 443)
        self.assertEqual(unquote(parsed.fragment), "خانه")
        query = parse_qs(parsed.query)
        self.assertEqual(query["type"], ["ws"])
        self.assertEqual(query["security"], ["tls"])
        self.assertEqual(query["sni"], ["example.com"])
        self.assertEqual(query["host"], ["cdn.example.com"])
        self.assertEqual(query["path"], ["/panel-ws"])
        self.assertEqual(query["allowInsecure"], ["0"])

        decoded = base64.b64decode(result["subscription_base64"], validate=True).decode("utf-8")
        self.assertEqual(decoded, result["vless_uri"] + "\n")


if __name__ == "__main__":
    unittest.main()
