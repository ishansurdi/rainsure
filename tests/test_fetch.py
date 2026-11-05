"""Tests for ingest.fetch: index parsing, member selection, URLs and retry logic (no network)."""

import io
import json
import unittest
import urllib.error
from datetime import datetime, timezone
from email.message import Message

from common import config
from ingest.fetch import DownloadError, file_url, http_get, parse_index, tp_member_entries

UTC = timezone.utc


def _row(number: int, param: str = "tp", typ: str = "pf", step: int = 24, offset: int = 0) -> str:
    """One .index line in the live format (fields seen in 20261104 IFS-ens index files)."""
    return json.dumps({"domain": "g", "date": "20261104", "time": "0000", "type": typ, "stream": "enfo",
                       "levtype": "sfc", "number": str(number), "step": str(step), "param": param,
                       "_offset": offset, "_length": 100 + number})


class TestParseIndex(unittest.TestCase):
    def test_parses_lines_and_skips_blanks(self) -> None:
        rows = parse_index(_row(1) + "\n\n" + _row(2) + "\n")
        self.assertEqual([r["number"] for r in rows], ["1", "2"])

    def test_bad_line_reports_line_number(self) -> None:
        with self.assertRaisesRegex(ValueError, "line 2"):
            parse_index(_row(1) + "\n{not json\n")


class TestTpMemberEntries(unittest.TestCase):
    def _all(self) -> list[str]:
        return [_row(n, offset=1000 * n) for n in range(1, config.EXPECTED_MEMBERS + 1)]

    def test_filters_param_and_type_and_sorts(self) -> None:
        lines = list(reversed(self._all())) + [_row(1, param="2t"), _row(0, typ="cf")]
        entries = tp_member_entries(parse_index("\n".join(lines)), "pf", 24)
        self.assertEqual(len(entries), 50)
        self.assertEqual(entries[0], (1, 1000, 101))
        self.assertEqual(entries[-1], (50, 50000, 150))

    def test_missing_member_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "members"):
            tp_member_entries(parse_index("\n".join(self._all()[:-1])), "pf", 24)

    def test_duplicate_member_rejected(self) -> None:
        with self.assertRaises(ValueError):
            tp_member_entries(parse_index("\n".join(self._all() + [_row(7)])), "pf", 24)

    def test_wrong_step_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "step"):
            tp_member_entries(parse_index(_row(1, step=18)), "pf", 24)


class TestFileUrl(unittest.TestCase):
    def test_ifs_matches_live_path(self) -> None:
        # Path verified to exist on data.ecmwf.int and the Google mirror (2026-11-05).
        url = file_url("google", datetime(2026, 11, 4, 0, tzinfo=UTC), "ifs-ens", 24, "index")
        self.assertEqual(url, "https://storage.googleapis.com/ecmwf-open-data/20261104/00z/ifs/0p25/enfo/"
                              "20261104000000-24h-enfo-ef.index")

    def test_aifs_12z(self) -> None:
        url = file_url("ecmwf", datetime(2026, 11, 4, 12, tzinfo=UTC), "aifs-ens", 6, "grib2")
        self.assertEqual(url, "https://data.ecmwf.int/forecasts/20261104/12z/aifs-ens/0p25/enfo/"
                              "20261104120000-6h-enfo-pf.grib2")


class _Resp(io.BytesIO):
    """Minimal stand-in for an HTTP response used as a context manager."""


def _http_error(code: int, retry_after: str | None = None) -> urllib.error.HTTPError:
    hdrs = Message()
    if retry_after is not None:
        hdrs["Retry-After"] = retry_after
    return urllib.error.HTTPError("u", code, "err", hdrs, None)


class FakeOpener:
    """Replays a scripted list of outcomes (bytes or exceptions) and records Range headers."""

    def __init__(self, outcomes: list[object]) -> None:
        self.outcomes, self.ranges = list(outcomes), []

    def __call__(self, req: object, timeout: float) -> _Resp:
        self.ranges.append(req.get_header("Range"))  # type: ignore[attr-defined]
        out = self.outcomes.pop(0)
        if isinstance(out, BaseException):
            raise out
        return _Resp(out)  # type: ignore[arg-type]


class TestHttpGet(unittest.TestCase):
    def setUp(self) -> None:
        self.sleeps: list[float] = []

    def _get(self, outcomes: list[object], byte_range: tuple[int, int] | None = (10, 4)) -> tuple[bytes, FakeOpener]:
        opener = FakeOpener(outcomes)
        return http_get("https://example.test/f.grib2", byte_range, opener=opener, sleep=self.sleeps.append), opener

    def test_range_header_and_success(self) -> None:
        body, opener = self._get([b"abcd"])
        self.assertEqual(body, b"abcd")
        self.assertEqual(opener.ranges, ["bytes=10-13"])

    def test_retries_5xx_with_backoff(self) -> None:
        body, _ = self._get([_http_error(503), _http_error(502), b"abcd"])
        self.assertEqual(body, b"abcd")
        self.assertEqual(self.sleeps, [2.0, 4.0])

    def test_honours_retry_after(self) -> None:
        self._get([_http_error(429, retry_after="7"), b"abcd"])
        self.assertEqual(self.sleeps, [7.0])

    def test_404_not_retried(self) -> None:
        with self.assertRaisesRegex(DownloadError, "404"):
            self._get([_http_error(404)])
        self.assertEqual(self.sleeps, [])

    def test_short_body_retried(self) -> None:
        body, _ = self._get([b"ab", b"abcd"])
        self.assertEqual(body, b"abcd")
        self.assertEqual(len(self.sleeps), 1)

    def test_whole_file_instead_of_range_is_rejected(self) -> None:
        with self.assertRaisesRegex(DownloadError, "expected 4"):
            self._get([b"whole file, range ignored"] * config.HTTP_MAX_ATTEMPTS)

    def test_network_errors_give_up_after_max_attempts(self) -> None:
        with self.assertRaisesRegex(DownloadError, "attempts"):
            self._get([ConnectionResetError("reset")] * config.HTTP_MAX_ATTEMPTS)
        self.assertEqual(len(self.sleeps), config.HTTP_MAX_ATTEMPTS - 1)

    def test_no_range_returns_full_body(self) -> None:
        body, opener = self._get([b"index text"], byte_range=None)
        self.assertEqual(body, b"index text")
        self.assertEqual(opener.ranges, [None])


if __name__ == "__main__":
    unittest.main()
