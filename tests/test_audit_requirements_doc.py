"""Validate the requirements contract, never infer business acceptance from it."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / 'docs/requirements/2026-10-12-unified-dashboard-audit-requirements.md'


def requirements(text):
    return [(m.group(1), m.group(2)) for m in re.finditer(
        r'^### (UDR-\d{3})[^\n]*\n(.*?)(?=^### UDR-|^## |\Z)', text, re.M | re.S)]


class AuditRequirementsDocumentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = DOC.read_text(encoding='utf-8')
        cls.items = requirements(cls.text)

    def test_ids_are_complete_unique_and_do_not_reuse_historical_req_ids(self):
        ids = [key for key, _ in self.items]
        self.assertEqual(ids, [f'UDR-{n:03d}' for n in range(1, 39)])
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn('REQ-001～REQ-051', self.text)

    def test_each_requirement_has_description_source_priority_and_status(self):
        for key, block in self.items:
            with self.subTest(requirement=key):
                for label in ('**需求描述：**', '**来源：**', '**优先级：**', '**当前状态：**', '**自动化测试用例：**', '**验收条件：**'):
                    self.assertIn(label, block)
                self.assertRegex(block, r'\*\*优先级：\*\* P[12]')
                self.assertRegex(block, r'\*\*当前状态：\*\* (回归保持|部分具备|待实现|待补证)')

    def test_cases_have_input_action_expected_result_and_cover_all_acceptance_conditions(self):
        all_cases = []
        for key, block in self.items:
            with self.subTest(requirement=key):
                acs = re.findall(r'^- (' + key + r'-AC\d{2})：(.+)$', block, re.M)
                cases = re.findall(r'^\| (' + key + r'-TC\d{2}) \| (.+) \| (.+) \| (.+) \| (.+) \|$', block, re.M)
                self.assertGreaterEqual(len(acs), 2)
                self.assertGreaterEqual(len(cases), 2)
                self.assertEqual(len(acs), len({a[0] for a in acs}))
                case_links = set()
                for case, scenario, expected, linked, coverage in cases:
                    self.assertIn('输入：', scenario)
                    self.assertIn('操作：', scenario)
                    self.assertGreater(len(expected), 12)
                    self.assertRegex(coverage, r'^(现有|待补充|待新增)')
                    case_links.update(re.findall(key + r'-AC\d{2}', linked))
                    all_cases.append(case)
                self.assertEqual(case_links, {a[0] for a in acs})
        self.assertEqual(len(all_cases), len(set(all_cases)))

    def test_every_original_finding_has_at_least_one_requirement(self):
        blocks = '\n'.join(block for _, block in self.items)
        for number in range(1, 13):
            self.assertRegex(blocks, r'\*\*来源：\*\*[^\n]*\bR' + f'{number:02d}' + r'\b')

    def test_relative_links_and_existing_tests_are_real_files(self):
        for target in re.findall(r'\]\(([^)]+)\)', self.text):
            if '://' not in target:
                self.assertTrue((DOC.parent / target.split('#')[0]).is_file(), target)

    def test_planned_test_and_release_limits_are_explicit(self):
        for boundary in ('文档校验通过不等于业务验收通过', '371', '93', '887', '885',
                         '07:30', '720', '72', 'queue: max', 'Dashboard quality gate',
                         '真实恢复部署', '不可把未验证标为通过', '待新增'):
            self.assertIn(boundary, self.text)

    def test_contract_checks_reject_missing_duplicate_and_broken_evidence_fields(self):
        mutations = [
            ('duplicate id', 'test_ids_are_complete_unique_and_do_not_reuse_historical_req_ids',
             self.text.replace('### UDR-002：', '### UDR-001：', 1)),
            ('missing description', 'test_each_requirement_has_description_source_priority_and_status',
             self.text.replace('**需求描述：**', '**描述被删除：**', 1)),
            ('missing action', 'test_cases_have_input_action_expected_result_and_cover_all_acceptance_conditions',
             self.text.replace('操作：', '动作被删除：', 1)),
            ('broken AC mapping', 'test_cases_have_input_action_expected_result_and_cover_all_acceptance_conditions',
             self.text.replace('| UDR-001-AC01 |', '| UDR-001-AC99 |', 1)),
            ('missing finding', 'test_every_original_finding_has_at_least_one_requirement',
             self.text.replace('R12', 'Rxx')),
            ('missing file', 'test_relative_links_and_existing_tests_are_real_files',
             self.text.replace('../../audit/2026-10-11/report.md', '../../audit/missing-report.md', 1)),
        ]
        for name, method, text in mutations:
            with self.subTest(mutation=name):
                checker = type(self)(method)
                checker.text, checker.items = text, requirements(text)
                with self.assertRaises(AssertionError):
                    getattr(checker, method)()


if __name__ == '__main__':
    unittest.main()
