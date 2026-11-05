"""Tests for ingest.runner_checks with a fake opener (no network)."""

import io
import unittest
import urllib.error
from datetime import datetime, timezone

from ingest.runner_checks import check_run, installed_packages, mirror_check


class _Resp(io.BytesIO):
    def __enter__(self) -> "_Resp":
        return self

    def __exit__(self, *a: object) -> None:
        self.close()


def _clock(*ticks: float):
    it = iter(ticks)
    return lambda: next(it)


class TestMirrorCheck(unittest.TestCase):
    def test_success_records_size_time_md5(self) -> None:
        r = mirror_check("https://example.test/a.index", opener=lambda req, timeout: _Resp(b"abc"),
                         clock=_clock(10.0, 12.5))
        # md5("abc") = 900150983cd24fb0d6963f7d28e17f72
        self.assertEqual(r, {"url": "https://example.test/a.index", "status": 200, "bytes": 3, "seconds": 2.5,
                             "md5": "90015098"})

    def test_http_error_recorded_not_raised(self) -> None:
        def opener(req, timeout):
            raise urllib.error.HTTPError(req.full_url, 404, "Not Found", None, None)
        r = mirror_check("https://example.test/a.index", opener=opener, clock=_clock(0.0, 0.25))
        self.assertEqual((r["status"], r["seconds"]), (404, 0.25))

    def test_timeout_recorded_not_raised(self) -> None:
        def opener(req, timeout):
            raise TimeoutError("timed out")
        r = mirror_check("https://example.test/a.index", opener=opener, clock=_clock(0.0, 60.0))
        self.assertIsNone(r["status"])
        self.assertIn("TimeoutError", r["error"])


class TestHelpers(unittest.TestCase):
    def test_check_run_is_yesterday_00z(self) -> None:
        self.assertEqual(check_run(datetime(2026, 11, 5, 0, 23, tzinfo=timezone.utc)),
                         datetime(2026, 11, 4, tzinfo=timezone.utc))

    def test_installed_packages_lists_numpy(self) -> None:
        self.assertTrue(any(p.lower().startswith("numpy==") for p in installed_packages()))


if __name__ == "__main__":
    unittest.main()
