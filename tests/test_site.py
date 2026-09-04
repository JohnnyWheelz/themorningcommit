#!/usr/bin/env python3
from __future__ import annotations
import importlib.util
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build-site.py"
spec = importlib.util.spec_from_file_location("tmc_build", SCRIPT)
build = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(build)


class SiteBuildTests(unittest.TestCase):
    def test_write_text_lf_is_platform_stable(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "test.txt"
            build.write_text_lf(target, "one\r\ntwo\rthree\n")
            self.assertEqual(target.read_bytes(), b"one\ntwo\nthree\n")

    def test_parse_date(self) -> None:
        value = build.parse_date("<p><strong>Date</strong><br>September 3, 2026</p>")
        self.assertEqual(value.date().isoformat(), "2026-09-03")

    def test_decorate_adds_canonical_and_social_metadata(self) -> None:
        raw = '<!doctype html><html><head><title>Old</title></head><body data-style-system="themorningcommit"><p><strong>Date</strong><br>September 3, 2026</p></body></html>'
        date = build.parse_date(raw)
        output = build.decorate(raw, date, "https://themorningcommit.com/")
        self.assertIn('<link rel="canonical" href="https://themorningcommit.com/">', output)
        self.assertIn('<meta property="og:title"', output)
        self.assertIn('<meta name="description"', output)
        self.assertIn('aria-label="Publication"', output)

    def test_decorate_is_idempotent(self) -> None:
        raw = '<!doctype html><html><head><title>Old</title></head><body data-style-system="themorningcommit"><p><strong>Date</strong><br>September 3, 2026</p></body></html>'
        date = build.parse_date(raw)
        first = build.decorate(raw, date, "https://themorningcommit.com/")
        second = build.decorate(first, date, "https://themorningcommit.com/")
        self.assertEqual(second.count("tmc-seo:start"), 1)
        self.assertEqual(second.count("tmc-nav:start"), 1)
        self.assertEqual(second.count("tmc-nav-css:start"), 1)


if __name__ == "__main__":
    unittest.main()
