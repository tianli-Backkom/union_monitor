"""Tests for catalog publication into the served web tree."""

import tempfile
import unittest
from pathlib import Path

from scripts.devdata import DevDataError, publish_catalog


class PublishCatalogTests(unittest.TestCase):
    def test_copies_catalog_into_web_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "catalog.json"
            source.write_text('{"schema_version":1,"projects":[]}', encoding="utf-8")
            target = Path(tmp) / "web" / "data" / "catalog.json"
            written = []
            result = publish_catalog(source=source, target=target, written=written)
            self.assertEqual(target.read_text(encoding="utf-8"), '{"schema_version":1,"projects":[]}')
            self.assertEqual(result, target)
            self.assertEqual(len(written), 1)

    def test_missing_source_raises(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(DevDataError):
                publish_catalog(source=Path(tmp) / "nope.json", target=Path(tmp) / "out.json")


if __name__ == "__main__":
    unittest.main()