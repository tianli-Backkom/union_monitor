"""Validate the delivered design artifacts, not the future dashboard implementation.

These checks catch broken review links, orphaned requirements and inconsistent
machine-readable examples. They do not establish collection/deployment success.
"""
from __future__ import annotations

import json
import re
import unittest
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DESIGN = ROOT / "docs" / "design"
PRODUCT = DESIGN / "2026-10-10-unified-dashboard-product.md"
ARCHITECTURE = DESIGN / "2026-10-10-unified-dashboard-architecture.md"
ANCHOR = re.compile(r'<a\s+id="([^"]+)"\s*></a>')
LINK = re.compile(r"\[[^\]\n]+\]\(([^)\n]+)\)")
FENCE = re.compile(r"^```[^\n]*\n.*?^```\s*$", re.M | re.S)


def prose(text: str) -> str:
    return FENCE.sub("", text)


def local_link_errors(path: Path, text: str, documents: dict[Path, str]) -> list[str]:
    errors = []
    for raw in LINK.findall(prose(text)):
        target = urlsplit(raw.strip("<>"))
        if target.scheme or target.netloc:
            continue
        destination = (path.parent / unquote(target.path)).resolve() if target.path else path.resolve()
        if not destination.is_file():
            errors.append(f"missing file: {raw}")
        elif target.fragment and destination in documents:
            if unquote(target.fragment) not in ANCHOR.findall(prose(documents[destination])):
                errors.append(f"missing anchor: {raw}")
    return errors


def anchored_section(text: str, anchor: str) -> str:
    marker = f'<a id="{anchor}"></a>'
    if marker not in text:
        raise ValueError(f"missing section anchor: {anchor}")
    tail = text.split(marker, 1)[1]
    return re.split(r'<a\s+id="', tail, maxsplit=1)[0]


def json_example(text: str, anchor: str) -> dict:
    # Do not accidentally consume another example if this section lost its fence.
    section = anchored_section(text, anchor)
    match = re.search(r"^```json\s*\n(.*?)^```\s*$", section, re.M | re.S)
    if not match:
        raise ValueError(f"missing JSON example: {anchor}")
    value = json.loads(match.group(1))
    if not isinstance(value, dict):
        raise ValueError(f"example must be an object: {anchor}")
    return value


def utc_time(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("timestamp must have an explicit timezone")
    return parsed


class DeliveredDesignTests(unittest.TestCase):
    def documents(self) -> dict[Path, str]:
        result = {}
        for path in (PRODUCT, ARCHITECTURE):
            self.assertTrue(path.is_file(), f"design deliverable missing: {path.name}")
            result[path.resolve()] = path.read_text(encoding="utf-8")
        return result

    def test_deliverables_have_unique_review_anchors(self):
        for path, text in self.documents().items():
            anchors = ANCHOR.findall(prose(text))
            self.assertTrue(anchors, path.name)
            self.assertEqual(len(anchors), len(set(anchors)), path.name)

    def test_all_local_review_links_resolve(self):
        documents = self.documents()
        for path, text in documents.items():
            self.assertEqual(local_link_errors(path, text, documents), [], path.name)

    def test_every_requirement_and_decision_has_an_acceptance_mapping(self):
        documents = self.documents()
        product = documents[PRODUCT.resolve()]
        architecture = documents[ARCHITECTURE.resolve()]
        wanted_product = {x for x in ANCHOR.findall(prose(product)) if re.fullmatch(r"P-\d{3}", x)}
        wanted_technical = {x for x in ANCHOR.findall(prose(architecture)) if re.fullmatch(r"T-\d{3}", x)}
        wanted_acceptance = {x for x in ANCHOR.findall(prose(architecture)) if re.fullmatch(r"AC-\d{3}", x)}
        self.assertTrue(wanted_product)
        self.assertTrue(wanted_technical)
        self.assertTrue(wanted_acceptance)
        mapped = {"P": set(), "T": set(), "AC": set()}
        for line in prose(anchored_section(architecture, "traceability")).splitlines():
            if not line.startswith("|"):
                continue
            references = [unquote(urlsplit(link).fragment) for link in LINK.findall(line)]
            if not any(re.fullmatch(r"P-\d{3}", x) for x in references):
                continue
            for prefix in mapped:
                matches = {x for x in references if re.fullmatch(prefix + r"-\d{3}", x)}
                self.assertTrue(matches, f"traceability row has no {prefix}: {line}")
                mapped[prefix].update(matches)
        self.assertEqual(mapped["P"], wanted_product)
        self.assertEqual(mapped["T"], wanted_technical)
        self.assertEqual(mapped["AC"], wanted_acceptance)

    def test_machine_readable_examples_are_valid_json(self):
        for path, text in self.documents().items():
            blocks = re.findall(r"^```json\s*\n(.*?)^```\s*$", text, re.M | re.S)
            for index, block in enumerate(blocks):
                with self.subTest(document=path.name, example=index):
                    json.loads(block)

    def test_catalog_examples_do_not_collide_or_reference_missing_profiles(self):
        text = self.documents()[ARCHITECTURE.resolve()]
        catalog = json_example(text, "example-catalog")
        projects = catalog["projects"]
        instances = catalog["source_instances"]
        self.assertEqual(len(instances), len({v["base_url"] for v in instances.values()}))
        for instance in instances.values():
            self.assertEqual(urlsplit(instance["base_url"]).scheme, "https")
            self.assertTrue(urlsplit(instance["base_url"]).hostname)
            self.assertTrue(instance["provider"])
        self.assertEqual({p["project_id"] for p in projects if p["enabled"]}, {"ubs", "triton"})
        self.assertEqual(len(projects), len({p["project_id"] for p in projects}))
        for project in projects:
            self.assertIn(project["collector"], catalog["collectors"])
            self.assertIn(project["metric_profile"], catalog["metric_profiles"])
            self.assertIn(project["view_profile"], catalog["view_profiles"])
            ids = [r["repository_id"] for r in project["repositories"]]
            self.assertEqual(len(ids), len(set(ids)))
            self.assertTrue(all(":" in value and "/" in value for value in ids))
            for repository_id in ids:
                self.assertIn(repository_id.split(":", 1)[0], instances)

    def test_report_and_fresh_release_use_the_same_run_context(self):
        text = self.documents()[ARCHITECTURE.resolve()]
        context = json_example(text, "example-run-context")
        report = json_example(text, "example-collection-report")
        release = json_example(text, "example-release-manifest")
        catalog = json_example(text, "example-catalog")
        self.assertEqual(context["run_id"], report["run_id"])
        self.assertEqual(context["run_id"], release["run_id"])
        self.assertEqual(context["code_sha"], report["code_sha"])
        self.assertEqual(context["code_sha"], release["code_sha"])
        enabled = {p["project_id"] for p in catalog["projects"] if p["enabled"]}
        self.assertEqual(set(release["projects"]), enabled)
        self.assertEqual(set(context["project_ids"]), enabled)
        cutoff = utc_time(context["cutoff_at"])
        self.assertEqual(utc_time(report["window"]["end_at"]), cutoff)
        project = next(p for p in catalog["projects"] if p["project_id"] == report["project_id"])
        self.assertEqual(report["window"]["time_basis"], project["window"]["time_basis"])
        self.assertEqual((cutoff - utc_time(report["window"]["start_at"])).total_seconds(),
                         project["window"]["hours"] * 3600)
        fresh = release["projects"][report["project_id"]]
        self.assertEqual(fresh["data_mode"], "fresh")
        self.assertEqual(report["collection_status"], "success")
        self.assertEqual(report["validation_status"], "passed")
        self.assertEqual(fresh["task_status"], "success")
        self.assertEqual(fresh["task_status"], report["task_status"])
        self.assertEqual(fresh["snapshot_sha256"], report["snapshot_sha256"])
        self.assertEqual(fresh["collected_at"], report["collected_at"])
        self.assertEqual(fresh["window"], report["window"])

    def test_fallback_example_keeps_old_data_time_and_failed_task_result(self):
        text = self.documents()[ARCHITECTURE.resolve()]
        context = json_example(text, "example-run-context")
        release = json_example(text, "example-release-manifest")
        fallback = release["projects"]["triton"]
        self.assertEqual(fallback["data_mode"], "fallback")
        self.assertEqual(fallback["task_status"], "failed")
        self.assertTrue(fallback["error"])
        self.assertLess(utc_time(fallback["window"]["end_at"]), utc_time(context["cutoff_at"]))
        self.assertLess(utc_time(fallback["collected_at"]), utc_time(release["published_at"]))
        for value in release["projects"].values():
            self.assertRegex(value["snapshot_sha256"], r"^[0-9a-f]{64}$")

    def test_fallback_preserves_the_verified_baseline_snapshot_reference(self):
        text = self.documents()[ARCHITECTURE.resolve()]
        baseline = json_example(text, "example-trusted-baseline")
        release = json_example(text, "example-release-manifest")
        self.assertEqual(release["baseline_release_id"], baseline["release_id"])
        old = baseline["projects"]["triton"]
        reused = release["projects"]["triton"]
        for field in ("snapshot_version", "snapshot_path", "snapshot_sha256", "collected_at", "window"):
            with self.subTest(field=field):
                self.assertTrue(old[field])
                self.assertEqual(reused[field], old[field])


class ArtifactCheckBehaviorTests(unittest.TestCase):
    def test_link_check_detects_removed_anchor_but_ignores_code_example_links(self):
        path = Path(__file__).resolve()
        text = '[broken](#gone)\n```text\n[example](#not-a-real-link)\n```\n'
        self.assertEqual(local_link_errors(path, text, {path: text}), ["missing anchor: #gone"])

    def test_json_reader_does_not_silently_consume_the_next_example(self):
        text = '<a id="one"></a>\nNo JSON.\n<a id="two"></a>\n```json\n{}\n```\n'
        with self.assertRaisesRegex(ValueError, "missing JSON example: one"):
            json_example(text, "one")

    def test_naive_time_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "explicit timezone"):
            utc_time("2026-10-10T07:30:00")


if __name__ == "__main__":
    unittest.main()
