from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from refractrouter.source_pack import attach_source_pack, load_source_pack
from tests.helpers import make_task


class SourcePackTests(unittest.TestCase):
    def test_loads_titles_content_and_stable_hashes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "report_001"
            source_dir.mkdir()
            (source_dir / "source_001.md").write_text(
                "# First source\n\nA traceable claim.\n",
                encoding="utf-8",
            )

            documents = load_source_pack(source_dir)

            self.assertEqual(documents[0].source_id, "source_001")
            self.assertEqual(documents[0].title, "First source")
            self.assertEqual(documents[0].content, "A traceable claim.")
            self.assertEqual(len(documents[0].content_hash), 64)

    def test_attach_source_pack_uses_task_pack_id(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp) / "report_001"
            source_dir.mkdir()
            (source_dir / "source_001.md").write_text(
                "# First source\n\nA traceable claim.\n",
                encoding="utf-8",
            )

            task = attach_source_pack(make_task(), tmp)

            self.assertEqual(tuple(source.source_id for source in task.source_documents), ("source_001",))

    def test_rejects_invalid_source_filename(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            source_dir = Path(tmp)
            (source_dir / "notes.md").write_text("# Notes\n\nClaim.\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Invalid source filename"):
                load_source_pack(source_dir)


if __name__ == "__main__":
    unittest.main()
