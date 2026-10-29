"""Offline raw-output contract tests; curl always returns a fixture."""

import json
import os
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("weather.sh")


class RawWeatherTests(unittest.TestCase):
    def run_weather(self, payload, raw=True):
        return subprocess.run(
            [
                "bash",
                "-c",
                'curl() { printf "%s" "$PAYLOAD"; }; script="$1"; shift; source "$script"',
                "fixture",
                str(SCRIPT),
                *(["--raw"] if raw else []),
            ],
            env=dict(os.environ, PAYLOAD=json.dumps(payload)),
            text=True,
            capture_output=True,
            check=False,
        )

    def test_api_errors_fail_in_raw_and_formatted_modes(self):
        for raw in (True, False):
            with self.subTest(raw=raw):
                result = self.run_weather(
                    {"error": True, "reason": "fixture failure"}, raw
                )
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertIn("fixture failure", result.stdout + result.stderr)

    def test_successful_raw_output_remains_json(self):
        payload = {"hourly": {"time": []}}
        result = self.run_weather(payload)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), payload)


if __name__ == "__main__":
    unittest.main()
