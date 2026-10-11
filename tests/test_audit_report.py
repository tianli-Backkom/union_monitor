"""Keep the audit's evidence and implementation boundaries inspectable."""
import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'audit/2026-10-11'


class AuditReportTests(unittest.TestCase):
    def test_relative_evidence_links_resolve(self):
        text = (AUDIT / 'report.md').read_text(encoding='utf-8')
        for target in re.findall(r'\]\(([^)]+)\)', text):
            if '://' not in target:
                self.assertTrue((AUDIT / target.split('#')[0]).is_file(), target)

    def test_evidence_json_is_readable_and_validation_has_no_failed_checks(self):
        for path in (AUDIT / 'evidence').glob('*.json'):
            json.loads(path.read_text(encoding='utf-8'))
        report = json.loads((AUDIT / 'evidence/validation.json').read_text(encoding='utf-8'))
        self.assertEqual(report['python']['failures'], 0)
        self.assertEqual(report['python']['errors'], 0)
        for name in ('node', 'chromium'):
            self.assertEqual(report[name]['ran'], report[name]['passed'])

    def test_report_distinguishes_fixes_from_incomplete_migration_and_source_audit(self):
        text = (AUDIT / 'report.md').read_text(encoding='utf-8')
        for boundary in ('不证明所有分页', '未完成', '只读', '并非全部'):
            if boundary == '并非全部':
                self.assertIn('不是全部真实 PR', text)
            else:
                self.assertIn(boundary, text)
        self.assertIn('276', text)
        self.assertIn('93', text)
        self.assertIn('Dashboard quality gate', text)
