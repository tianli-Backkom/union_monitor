"""Developer bootstrap contracts at the network/file boundary."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts import devdata
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


class BootstrapTests(unittest.TestCase):
    SITE = "https://tianli-backkom.github.io/union_monitor"
    FIXTURES = Path(__file__).resolve().parent / "fixtures" / "minimal"

    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.web_data = self.root / "web" / "data"
        self.root_data = self.root / "data"
        self.catalog = {"schema_version": 1, "projects": []}
        (self.root / "catalog.json").write_text(json.dumps(self.catalog), encoding="utf-8")
        patches = contextlib.ExitStack()
        self.addCleanup(patches.close)
        for name, value in (("REPO_ROOT", self.root), ("WEB_DATA_DIR", self.web_data),
                            ("ROOT_DATA_DIR", self.root_data)):
            patches.enter_context(patch.object(devdata, name, value))

    def resources(self, ubs_base=None, triton_url=None, triton_body=None):
        ubs_base = ubs_base or self.SITE
        triton_url = triton_url or self.SITE + "/data/triton.json"
        return {
            ubs_base + "/data/" + relative: (self.FIXTURES / relative).read_bytes()
            for relative in ("repositories.json", "repos/ubs-engine.json", "snapshot.json")
        } | {triton_url: triton_body if triton_body is not None else
             (self.FIXTURES / "triton.json").read_bytes()}

    def assert_outputs(self):
        for relative in ("repositories.json", "repos/ubs-engine.json", "triton.json"):
            self.assertEqual(json.loads((self.web_data / relative).read_bytes()),
                             json.loads((self.FIXTURES / relative).read_bytes()))
        self.assertEqual(json.loads((self.root_data / "snapshot.json").read_bytes()),
                         json.loads((self.FIXTURES / "snapshot.json").read_bytes()))
        self.assertEqual(json.loads((self.web_data / "catalog.json").read_bytes()), self.catalog)

    def test_default_cli_bootstraps_both_projects_from_same_published_site(self):
        resources = self.resources()
        requested = []

        def fetch(url):
            requested.append(url)
            self.assertTrue(url in resources, f"unexpected default source: {url}")
            return resources[url]

        with patch.object(devdata, "fetch", side_effect=fetch), patch("sys.argv", ["devdata.py"]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(devdata.main(), 0)
        self.assertEqual(set(requested), set(resources))
        self.assert_outputs()

    def test_explicit_json_url_writes_the_complete_triton_payload(self):
        url = "https://example.test/custom/triton.json?revision=1"
        with patch.object(devdata, "fetch", side_effect=self.resources(triton_url=url).__getitem__):
            devdata.run_online(self.SITE + "/", url, [])
        self.assert_outputs()

    def test_explicit_legacy_html_url_remains_supported(self):
        base = "https://tianli-backkom.github.io/ubs_core_monitor"
        url = "https://tianli-backkom.github.io/Triton-Ascend_monitor/index.html"
        html = b'<!doctype html><script type="application/json" id="data">' + \
            (self.FIXTURES / "triton.json").read_bytes() + b"</script>"
        with patch.object(devdata, "fetch", side_effect=self.resources(base, url, html).__getitem__):
            devdata.run_online(base, url, [])
        self.assert_outputs()

    def test_direct_json_reports_invalid_json_instead_of_missing_html_script(self):
        url = self.SITE + "/data/triton.json"
        for body in (b'{"batches":', b"\xff", b"<html>upstream unavailable</html>"):
            with self.subTest(body=body), \
                    patch.object(devdata, "fetch", side_effect=self.resources(triton_body=body).__getitem__):
                with self.assertRaisesRegex(DevDataError, "invalid JSON"):
                    devdata.run_online(self.SITE, url, [])
        self.assertFalse((self.web_data / "triton.json").exists())

    def test_direct_json_validates_existing_required_payload_fields(self):
        url = self.SITE + "/data/triton.json"
        with patch.object(devdata, "fetch", side_effect=self.resources(triton_body=b'{"batches":[]}').__getitem__):
            with self.assertRaisesRegex(DevDataError, "missing required field.*repo.*window_start.*summary"):
                devdata.run_online(self.SITE, url, [])
        self.assertFalse((self.web_data / "triton.json").exists())

    def test_offline_cli_uses_fixtures_without_network_access(self):
        with patch.object(devdata, "fetch", side_effect=AssertionError("offline must not access the network")), \
                patch("sys.argv", ["devdata.py", "--offline"]), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(devdata.main(), 0)
        self.assert_outputs()


if __name__ == "__main__":
    unittest.main()
