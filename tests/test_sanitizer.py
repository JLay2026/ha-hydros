"""Tests for the debug payload sanitizer (Issue #6).

Loads ``sanitizer.py`` directly by file path so the test doesn't pull in
the full ``custom_components.hydros`` package (which transitively imports
``homeassistant.config_entries`` via ``__init__.py``). This keeps the
test runnable without a Home Assistant install.

Run standalone:
    python -m unittest tests.test_sanitizer

Or via pytest once the test runner is wired up in CI.
"""
from __future__ import annotations

import importlib.util
import pathlib
import re
import unittest


def _load_sanitizer():
    repo_root = pathlib.Path(__file__).resolve().parent.parent
    src = repo_root / "custom_components" / "hydros" / "sanitizer.py"
    spec = importlib.util.spec_from_file_location("hydros_sanitizer", src)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load sanitizer from {src}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sanitizer = _load_sanitizer()
sanitize_payload = sanitizer.sanitize_payload
REDACTED_PLACEHOLDER = sanitizer.REDACTED_PLACEHOLDER
REDACTED_EMAIL = sanitizer.REDACTED_EMAIL
REDACTED_TOKEN = sanitizer.REDACTED_TOKEN
REDACTED_PRESIGNED = sanitizer.REDACTED_PRESIGNED
REDACTED_MQTT_CREDS = sanitizer.REDACTED_MQTT_CREDS


class SanitizerTest(unittest.TestCase):
    def test_unsanitized_passthrough(self):
        payload = {"password": "secret123", "ok": "fine"}
        self.assertEqual(sanitize_payload(payload, unsanitized=True), payload)

    def test_keyed_redaction(self):
        payload = {
            "password": "secret123",
            "auth_token": "abc.def.ghi",
            "userEmail": "alice@example.com",
            "serialNum": "AB-12345",
            "accountId": "u_98765",
            "x-amz-signature": "xyz",
            "ok": "fine",
        }
        result = sanitize_payload(payload)
        for key in (
            "password",
            "auth_token",
            "userEmail",
            "serialNum",
            "accountId",
            "x-amz-signature",
        ):
            self.assertEqual(
                result[key],
                REDACTED_PLACEHOLDER,
                f"{key} not redacted",
            )
        self.assertEqual(result["ok"], "fine")

    def test_thing_ids_preserved(self):
        payload = {
            "thingId": "abc-123",
            "thingName": "Reef Tank",
            "thingType": "Collective",
        }
        result = sanitize_payload(payload)
        self.assertEqual(result, payload)

    def test_email_in_value(self):
        payload = {"log": "user alice@example.com signed in"}
        result = sanitize_payload(payload)["log"]
        self.assertIn(REDACTED_EMAIL, result)
        self.assertNotIn("alice@example.com", result)

    def test_jwt_in_value(self):
        token = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.sig_part"
        payload = {"log": f"Bearer {token}"}
        result = sanitize_payload(payload)["log"]
        self.assertIn(REDACTED_TOKEN, result)
        self.assertNotIn("eyJhbGciOiJIUzI1NiJ9", result)

    def test_mqtt_uri_with_creds(self):
        payload = {"broker": "mqtts://user:supersecret@mqtt.example.com:8883"}
        result = sanitize_payload(payload)["broker"]
        self.assertIn(REDACTED_MQTT_CREDS, result)
        self.assertNotIn("supersecret", result)
        self.assertIn("mqtt.example.com", result)

    def test_presigned_url(self):
        url = (
            "https://s3.amazonaws.com/bucket/file.json"
            "?X-Amz-Signature=abc123&X-Amz-Credential=AKIA"
        )
        payload = {"download_url": url}
        result = sanitize_payload(payload)["download_url"]
        self.assertIn(REDACTED_PRESIGNED, result)
        self.assertNotIn("X-Amz-Signature=abc123", result)
        self.assertIn("s3.amazonaws.com", result)
        self.assertIn("/bucket/file.json", result)

    def test_structure_preserved(self):
        payload = {
            "device": {
                "thingId": "abc-123",
                "thingName": "Reef Tank",
                "credentials": {"password": "x"},
                "sensors": [
                    {"name": "temp", "value": 78.5},
                    {
                        "name": "ph",
                        "value": 8.2,
                        "userEmail": "alice@example.com",
                    },
                ],
            }
        }
        result = sanitize_payload(payload)
        self.assertEqual(result["device"]["thingId"], "abc-123")
        self.assertEqual(result["device"]["thingName"], "Reef Tank")
        self.assertEqual(result["device"]["credentials"], REDACTED_PLACEHOLDER)
        self.assertEqual(len(result["device"]["sensors"]), 2)
        self.assertEqual(result["device"]["sensors"][0]["value"], 78.5)
        self.assertEqual(
            result["device"]["sensors"][1]["userEmail"],
            REDACTED_PLACEHOLDER,
        )

    def test_no_email_or_token_shaped_strings_survive(self):
        """Acceptance criterion: assert no email/token-shaped strings survive."""
        payload = {
            "log_lines": [
                "Authenticated alice@example.com",
                "Token: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abc",
                "URL: https://s3.amazonaws.com/x?X-Amz-Signature=secret",
            ],
            "config": {
                "password": "verysecret",
                "broker": "mqtt://user:pass@broker:1883",
            },
        }
        result = sanitize_payload(payload)
        flat = repr(result)
        # No raw email survived (only the [REDACTED_EMAIL] marker).
        self.assertNotRegex(flat, r"\balice@example\.com\b")
        # No raw JWT survived.
        self.assertNotRegex(
            flat, r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"
        )
        # No raw MQTT creds.
        self.assertNotIn("user:pass@", flat)
        # No raw password.
        self.assertNotIn("verysecret", flat)
        # No raw signature value.
        self.assertNotIn("X-Amz-Signature=secret", flat)


if __name__ == "__main__":
    unittest.main()
