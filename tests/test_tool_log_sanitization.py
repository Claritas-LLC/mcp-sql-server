import unittest

from mcp_sqlserver import server


class TestToolLogSanitization(unittest.TestCase):
    def test_sanitizes_sensitive_keys_recursively(self):
        payload = {
            "database": "master",
            "config": {
                "password": "secret-pass",
                "token": "abc123",
                "nested": {
                    "Authorization": "Bearer xyz",
                    "safe": "ok",
                },
            },
            "items": [
                {"api_key": "k1", "name": "first"},
                {"prompt_context": "raw prompt", "meta": {"secret": "s"}},
                "plain-item",
            ],
        }

        sanitized = server._sanitize_tool_log_context(payload)

        self.assertEqual(sanitized["database"], "master")
        self.assertEqual(sanitized["config"]["password"], "[redacted]")
        self.assertEqual(sanitized["config"]["token"], "[redacted]")
        self.assertEqual(sanitized["config"]["nested"]["Authorization"], "[redacted]")
        self.assertEqual(sanitized["config"]["nested"]["safe"], "ok")
        self.assertEqual(sanitized["items"][0]["api_key"], "[redacted]")
        self.assertEqual(sanitized["items"][0]["name"], "first")
        self.assertEqual(sanitized["items"][1]["prompt_context"], "[redacted]")
        self.assertEqual(sanitized["items"][1]["meta"]["secret"], "[redacted]")
        self.assertEqual(sanitized["items"][2], "plain-item")

    def test_non_container_values_remain_unchanged(self):
        payload = {
            "count": 3,
            "enabled": True,
            "message": "hello",
            "none_value": None,
        }

        sanitized = server._sanitize_tool_log_context(payload)

        self.assertEqual(sanitized, payload)


if __name__ == "__main__":
    unittest.main()
