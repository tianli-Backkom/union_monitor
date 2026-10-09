"""REQ-040 · CI目标运行时兼容性验证 — 测试。

锁定 scripts/verify_runtime.py 的补证语义：
- 解析器：unittest/node（Node 22 '#' 与 Node 24 'ℹ' 两种前缀）摘要计数、
  工作流版本声明提取、node 主版本号
- AC03 诚实分类：报告未达 verified、工件缺失（FileNotFoundError）或报告
  不可读时绝不返回 passed，即使退出码为 0
- 提交证据（runtime-evidence.json）结构与语义：精确版本、命令、退出码、
  失败数与日志路径；测试与门禁在目标运行时全部通过；原始审计如实
  not_passed；CI 声明↔README↔交付结果三方一致；基线仅作原环境记录
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import verify_runtime as vr  # noqa: E402

EVIDENCE_PATH = ROOT / 'audit' / '2026-10-09' / 'evidence' / 'runtime-evidence.json'


class ParserTests(unittest.TestCase):
    """输出解析与版本声明提取。"""

    def test_parse_workflow_declarations(self):
        declared = vr.parse_workflow_declarations(ROOT)
        self.assertEqual(declared['python'], ['3.12'])
        self.assertEqual(declared['node'], ['22'])

    def test_parse_unittest_summary_ok_with_skip(self):
        summary = vr.parse_unittest_summary('Ran 240 tests in 94.5s\n\nOK (skipped=1)\n')
        self.assertEqual(summary['tests'], 240)
        self.assertEqual(summary['skipped'], 1)
        self.assertEqual(summary['failures'], 0)
        self.assertEqual(summary['result'], 'OK')

    def test_parse_unittest_summary_failed_counts(self):
        output = 'Ran 10 tests\n\nFAILED (failures=2, errors=1, skipped=3)\n'
        summary = vr.parse_unittest_summary(output)
        self.assertEqual(summary['result'], 'FAILED')
        self.assertEqual(summary['failures'], 2)
        self.assertEqual(summary['errors'], 1)
        self.assertEqual(summary['skipped'], 3)

    def test_parse_node_summary_both_prefix_styles(self):
        for prefix in ('ℹ', '#'):
            output = (f'{prefix} tests 122\n{prefix} suites 0\n{prefix} pass 122\n'
                      f'{prefix} fail 0\n{prefix} cancelled 0\n{prefix} skipped 0\n')
            summary = vr.parse_node_summary(output)
            self.assertEqual(summary['tests'], 122, prefix)
            self.assertEqual(summary['pass'], 122, prefix)
            self.assertEqual(summary['fail'], 0, prefix)
            self.assertEqual(summary['result'], 'OK', prefix)

    def test_parse_node_summary_failed(self):
        summary = vr.parse_node_summary('ℹ tests 5\nℹ pass 3\nℹ fail 2\n')
        self.assertEqual(summary['result'], 'FAILED')
        self.assertEqual(summary['fail'], 2)

    def test_node_major(self):
        self.assertEqual(vr.node_major('v22.23.3'), '22')
        self.assertEqual(vr.node_major('22.1.0'), '22')
        self.assertEqual(vr.node_major('v10.24.1'), '10')
        self.assertIsNone(vr.node_major(None))
        self.assertIsNone(vr.node_major('garbage'))


class AuditHonestyTests(unittest.TestCase):
    """AC03：工件缺失或报告未验证时绝不报审计通过。"""

    def test_classify_audit_never_fakes_passed(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / 'validation-multi.json'
            report.write_text(json.dumps({'overall_status': 'verified'}), 'utf-8')
            self.assertEqual(vr.classify_audit(0, 'log', report)[0], 'passed')
            report.write_text(json.dumps({'overall_status': 'unverified'}), 'utf-8')
            self.assertEqual(vr.classify_audit(0, 'log', report)[0],
                             'not_passed_unverified')
            report.write_text('not json', 'utf-8')
            self.assertEqual(vr.classify_audit(0, 'log', report)[0],
                             'inconclusive_bad_report')
        self.assertEqual(
            vr.classify_audit(0, 'log', Path('/nonexistent/report.json'))[0],
            'inconclusive_exit0_no_report')
        self.assertEqual(
            vr.classify_audit(1, 'FileNotFoundError: data/repositories.json', None)[0],
            'failed_missing_artifacts')
        self.assertEqual(vr.classify_audit(1, 'AssertionError: boom', None)[0],
                         'failed_exit_1')


class CommittedEvidenceTests(unittest.TestCase):
    """提交证据（runtime-evidence.json）结构与语义。"""

    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(EVIDENCE_PATH.read_text('utf-8'))

    def run_by_label(self, label):
        return next(run for run in self.report['runs'] if run['label'] == label)

    def test_runtimes_match_ci_declarations(self):
        runtimes = self.report['runtimes']
        self.assertEqual(runtimes['python']['major_minor'], '3.12')
        self.assertTrue(runtimes['python']['version'].startswith('3.12.'))
        self.assertEqual(runtimes['node']['major'], '22')
        self.assertTrue(runtimes['node']['version'].startswith('v22.'))
        declared = self.report['ci_declarations']
        self.assertEqual(declared['python'], ['3.12'])
        self.assertEqual(declared['node'], ['22'])
        self.assertEqual(declared['sources'], ['pages.yml', 'triton-refresh.yml'])

    def test_baseline_note_kept_as_original_env_only(self):
        note = self.report['baseline_note']
        self.assertEqual(note, vr.BASELINE_NOTE)
        self.assertIn('79/79', note)
        self.assertIn('34/34', note)
        self.assertIn('不替代', note)

    def test_python_tests_pass_on_target_runtime(self):
        run = self.run_by_label('python_tests')
        self.assertEqual(run['exit_code'], 0)
        self.assertEqual(run['summary']['result'], 'OK')
        self.assertEqual(run['summary']['failures'], 0)
        self.assertEqual(run['summary']['errors'], 0)
        self.assertGreaterEqual(run['summary']['tests'], 240)
        self.assertTrue(run['command'])
        self.assertTrue(run['log'].endswith('.txt'))

    def test_node_tests_pass_on_target_runtime(self):
        run = self.run_by_label('node_tests')
        self.assertEqual(run['exit_code'], 0)
        self.assertEqual(run['summary']['result'], 'OK')
        self.assertEqual(run['summary']['fail'], 0)
        self.assertEqual(run['summary']['pass'], run['summary']['tests'])
        self.assertGreaterEqual(run['summary']['tests'], 122)
        self.assertIn('node --test', run['command'])

    def test_data_gates_pass_on_target_runtime(self):
        for label in ('validate_bundle', 'verify_artifacts', 'verify_concurrency'):
            run = self.run_by_label(label)
            self.assertEqual(run['exit_code'], 0, label)

    def test_raw_audit_honestly_not_passed(self):
        summary = self.report['raw_audit_summary']
        self.assertEqual(summary['status'], 'not_passed')
        self.assertNotIn('passed', summary['classifications'].values())
        self.assertEqual(summary['classifications']['raw_audit_multi'],
                         'failed_missing_artifacts')
        self.assertEqual(summary['classifications']['raw_audit_ubs'],
                         'failed_missing_artifacts')
        self.assertIn('wrapper', summary['note'])
        for label in ('raw_audit_multi', 'raw_audit_ubs'):
            run = self.run_by_label(label)
            self.assertEqual(run['exit_code'], 1, label)
            self.assertEqual(run['audit_classification'], 'failed_missing_artifacts',
                             label)

    def test_version_consistency_with_readme(self):
        consistency = self.report['version_consistency']
        for key in ('python_runtime_matches_ci', 'node_runtime_matches_ci',
                    'readme_states_python', 'readme_states_node'):
            self.assertTrue(consistency[key], key)
        self.assertEqual(consistency['problems'], [])
        readme = (ROOT / vr.README_FILE).read_text('utf-8')
        self.assertIn(vr.README_PY_MARKER, readme)
        self.assertIn(vr.README_NODE_MARKER, readme)

    def test_overall_verified(self):
        self.assertEqual(self.report['overall']['status'], 'verified')
        self.assertEqual(self.report['overall']['problems'], [])


if __name__ == '__main__':
    unittest.main()
