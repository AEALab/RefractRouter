from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from refractrouter.report_renderer import render_standalone_html, save_html_report


class ReportRendererTests(unittest.TestCase):
    def test_render_and_save(self) -> None:
        html = render_standalone_html("Test Report", "<h1>Hello</h1>")
        self.assertIn("<!doctype html>", html)
        self.assertIn("<h1>Hello</h1>", html)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "report.html"
            saved = save_html_report(path, html)
            self.assertTrue(saved.exists())
            self.assertIn("<!doctype html>", saved.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
