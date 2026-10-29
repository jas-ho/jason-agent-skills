"""Self-contained offline fixtures for snow measurements and forecast selection."""

import datetime
import json
import os
import re
import subprocess
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("skitour.sh")
SOURCE = SCRIPT.read_text().rsplit('main "$@"', 1)[0]


def run_shell(body, **env):
    return subprocess.run(
        ["bash", "-c", SOURCE + "\n" + body],
        env=dict(os.environ, **env),
        text=True,
        capture_output=True,
        check=False,
    )


class SnowDepthTests(unittest.TestCase):
    def measurement(self, depth):
        return run_shell(
            'curl() { printf "time,snow_depth\\n2026-01-01,%s\\n" "$DEPTH"; }; '
            "get_snow_depth 47 15",
            DEPTH=depth,
        )

    def test_invalid_measurements_are_unavailable(self):
        for depth in (
            "NaN",
            "nan",
            "Inf",
            "-Inf",
            "null",
            "",
            "snow_depth",
            "oops",
            "-1",
        ):
            with self.subTest(depth=depth):
                result = self.measurement(depth)
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertEqual(result.stdout.strip(), "N/A")

    def test_valid_measurements_include_real_zero(self):
        for depth, expected in (
            ("0", "0"),
            ("0.42", "42"),
            ("1.25", "125"),
            (".5", "50"),
        ):
            with self.subTest(depth=depth):
                result = self.measurement(depth)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected)

    def test_network_failure_is_unavailable(self):
        result = run_shell("curl() { return 22; }; get_snow_depth 47 15")
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), "N/A")


class ForecastTests(unittest.TestCase):
    def forecast(self, now, count=48):
        start = datetime.datetime(2026, 1, 1)
        times = [
            (start + datetime.timedelta(hours=i)).isoformat(timespec="minutes")
            for i in range(count)
        ]
        hourly = {"time": times}
        for key in (
            "temperature_2m",
            "windspeed_10m",
            "cloudcover",
            "precipitation_probability",
        ):
            hourly[key] = list(range(count))
        result = run_shell(
            """
curl() { echo "unexpected network" >&2; exit 99; }
get_avalanche_data() { return 1; }
get_snow_depth() { return 1; }
get_weather() { printf '%s' "$WEATHER"; }
date() {
    if [[ "${TZ:-}" != Europe/Vienna ]]; then
        echo "wrong forecast timezone" >&2
        return 1
    fi
    printf '%s\\n' "$NOW"
}
show_location fixture 47 15 AT-03 AT-03-04
""",
            NOW=now,
            WEATHER=json.dumps({"hourly": hourly}),
            TZ="UTC",
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        rows = re.findall(r"^\s+(\d\d):00\s+([\d.]+)°C", result.stdout, re.MULTILINE)
        return [(int(hour), float(temp)) for hour, temp in rows]

    def test_afternoon_and_midnight_crossing(self):
        self.assertEqual(
            self.forecast("2026-01-01T15:30"),
            [(i % 24, float(i)) for i in range(16, 28)],
        )

    def test_exact_hour_included(self):
        self.assertEqual(
            self.forecast("2026-01-01T15:00"),
            [(i % 24, float(i)) for i in range(15, 27)],
        )

    def test_short_and_exhausted_responses(self):
        self.assertEqual(self.forecast("2026-01-01T22:30", 24), [(23, 23.0)])
        self.assertEqual(self.forecast("2026-01-02T00:00", 24), [])


if __name__ == "__main__":
    unittest.main()
