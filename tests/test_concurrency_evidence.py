"""REQ-039 · 并发调度策略与运行证据一致 — 测试。

锁定 scripts/verify_concurrency.py 的补证语义：
- 真实工作流并发声明与文档化策略一致（group=pages、cancel-in-progress=false、
  无显式 queue，即平台默认 single）
- 提交证据（concurrency-evidence.json）结构与语义：平台文档引文与参考链接、
  业务影响三场景、AC01 受控序列协议与 AC03 运行历史如实 unverified、
  AC04 queue:max 缓期决策、测试名与 README 对齐
- 工具在合成目录树上可执行且能发现漂移（cancel-in-progress 改 true、恢复
  失实测试名、删除 README 声明、缺失工作流均退出码 1）
"""
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import verify_concurrency as vc  # noqa: E402

EVIDENCE_PATH = ROOT / 'audit' / '2026-10-09' / 'evidence' / 'concurrency-evidence.json'


class WorkflowConfigTests(unittest.TestCase):
    """真实工作流并发声明与文档化策略一致。"""

    def test_real_workflows_declare_documented_strategy(self):
        for name in vc.WORKFLOWS:
            path = ROOT / vc.WORKFLOW_DIR / name
            info = vc.extract_concurrency(path.read_text('utf-8'))
            self.assertIsNotNone(info, name)
            self.assertEqual(info.get('group'), 'pages', name)
            self.assertEqual(info.get('cancel-in-progress'), 'false', name)
            self.assertNotIn('queue', info, name)
        facts, problems = vc.config_facts(ROOT)
        self.assertEqual(problems, [])
        for entry in facts.values():
            self.assertEqual(entry['group'], 'pages')
            self.assertEqual(entry['cancel_in_progress'], 'false')
            self.assertEqual(entry['queue'], 'single (platform default)')

    def test_extract_concurrency_parses_group_cancel_and_queue(self):
        text = ('name: probe\n'
                'concurrency:\n'
                '  group: demo\n'
                '  cancel-in-progress: true\n'
                '  queue: max\n'
                'jobs:\n'
                '  build:\n')
        info = vc.extract_concurrency(text)
        self.assertEqual(info['group'], 'demo')
        self.assertEqual(info['cancel-in-progress'], 'true')
        self.assertEqual(info['queue'], 'max')

    def test_extract_concurrency_absent_returns_none(self):
        self.assertIsNone(vc.extract_concurrency('name: probe\njobs: {}\n'))

    def test_explicit_queue_is_flagged_as_strategy_drift(self):
        drifted = ('concurrency:\n'
                   '  group: pages\n'
                   '  cancel-in-progress: false\n'
                   '  queue: max\n')
        healthy = ('concurrency:\n'
                   '  group: pages\n'
                   '  cancel-in-progress: false\n')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / vc.WORKFLOW_DIR).mkdir(parents=True)
            (root / vc.WORKFLOW_DIR / 'pages.yml').write_text(drifted, 'utf-8')
            (root / vc.WORKFLOW_DIR / 'triton-refresh.yml').write_text(healthy, 'utf-8')
            _, problems = vc.config_facts(root)
            self.assertTrue(any('queue' in problem for problem in problems))


class CommittedEvidenceTests(unittest.TestCase):
    """提交证据（concurrency-evidence.json）结构与语义。"""

    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(EVIDENCE_PATH.read_text('utf-8'))

    def test_documented_semantics_with_reference(self):
        semantics = self.report['documented_platform_semantics']
        self.assertEqual(semantics['reference'], vc.REFERENCE)
        self.assertGreaterEqual(len(semantics['quotes']), 4)
        self.assertIn('pending', semantics['pending_default_single'])
        self.assertIn('cancel-in-progress: true', semantics['queue_max'])
        self.assertIn('FIFO', semantics['fifo'])

    def test_business_impact_scenarios(self):
        impact = self.report['business_impact']
        self.assertEqual([s['id'] for s in impact['scenarios']], ['S-a', 'S-b', 'S-c'])
        s_b = impact['scenarios'][1]
        self.assertIn('每日全量', s_b['sequence'])
        self.assertIn('丢失', s_b['business'])
        self.assertIn('07:30', s_b['business'])
        s_c = impact['scenarios'][2]
        self.assertIn('手动', s_c['business'])
        self.assertIn('不推断已线上发生', impact['conclusion'])

    def test_ac01_unverified_with_protocol(self):
        ac01 = self.report['ac01_controlled_sequence']
        self.assertEqual(ac01['status'], 'unverified')
        self.assertTrue(ac01['reasons'])
        self.assertGreaterEqual(len(ac01['protocol']['steps']), 5)
        self.assertTrue(ac01['protocol']['isolation'])
        expected = ac01['protocol']['expected']
        self.assertIn('A 不被取消', expected)
        self.assertIn('B 被 C 取代', expected)

    def test_ac03_unverified_with_procedure(self):
        ac03 = self.report['ac03_run_history']
        self.assertEqual(ac03['status'], 'unverified')
        self.assertTrue(ac03['reasons'])
        self.assertGreaterEqual(len(ac03['procedure']), 3)
        self.assertIn('不推断已线上发生', ac03['recorded'])

    def test_ac04_deferred(self):
        ac04 = self.report['ac04_queue_max']
        self.assertEqual(ac04['decision'], 'deferred')
        self.assertIn('不是新增必改功能', ac04['rationale'])
        self.assertIn('queue: max', ac04['future_policy'])
        self.assertIn('P04', ac04['p04_resolution'])

    def test_alignment_locks_test_name_and_readme(self):
        checks = self.report['test_and_doc_alignment']
        self.assertTrue(all(checks.values()), checks)
        test_text = (ROOT / vc.TEST_FILE).read_text('utf-8')
        self.assertNotIn(vc.OLD_TEST_NAME, test_text)
        self.assertIn(vc.NEW_TEST_NAME, test_text)
        self.assertIn(vc.README_MARKER, (ROOT / vc.README_FILE).read_text('utf-8'))

    def test_overall_aligned_and_unverified_tolerated(self):
        overall = self.report['overall']
        self.assertEqual(overall['status'], 'aligned')
        self.assertEqual(overall['problems'], [])
        self.assertIn('不影响退出码', overall['note'])


class SyntheticTreeTests(unittest.TestCase):
    """工具在合成目录树上的行为：对齐树退出码 0、漂移树退出码 1。"""

    def build_tree(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / vc.WORKFLOW_DIR).mkdir(parents=True)
        for name in vc.WORKFLOWS:
            shutil.copy(ROOT / vc.WORKFLOW_DIR / name, root / vc.WORKFLOW_DIR / name)
        (root / vc.TEST_FILE).parent.mkdir(parents=True)
        shutil.copy(ROOT / vc.TEST_FILE, root / vc.TEST_FILE)
        shutil.copy(ROOT / vc.README_FILE, root / vc.README_FILE)
        return root

    def test_clean_tree_exit_zero(self):
        root = self.build_tree()
        output = root / 'report.json'
        code = vc.main(['--root', str(root), '--output', str(output)])
        self.assertEqual(code, 0)
        report = json.loads(output.read_text('utf-8'))
        self.assertEqual(report['overall']['status'], 'aligned')
        self.assertEqual(report['overall']['problems'], [])

    def test_cancel_in_progress_true_exit_one(self):
        root = self.build_tree()
        path = root / vc.WORKFLOW_DIR / 'pages.yml'
        path.write_text(
            path.read_text('utf-8').replace('cancel-in-progress: false',
                                            'cancel-in-progress: true'), 'utf-8')
        output = root / 'report.json'
        code = vc.main(['--root', str(root), '--output', str(output)])
        self.assertEqual(code, 1)
        report = json.loads(output.read_text('utf-8'))
        self.assertEqual(report['overall']['status'], 'drift')
        self.assertTrue(any('cancel-in-progress' in problem
                            for problem in report['overall']['problems']))

    def test_old_test_name_restored_exit_one(self):
        root = self.build_tree()
        path = root / vc.TEST_FILE
        path.write_text(
            path.read_text('utf-8').replace(vc.NEW_TEST_NAME, vc.OLD_TEST_NAME), 'utf-8')
        output = root / 'report.json'
        code = vc.main(['--root', str(root), '--output', str(output)])
        self.assertEqual(code, 1)
        report = json.loads(output.read_text('utf-8'))
        self.assertTrue(any(vc.OLD_TEST_NAME in problem
                            for problem in report['overall']['problems']))

    def test_missing_readme_marker_exit_one(self):
        root = self.build_tree()
        path = root / vc.README_FILE
        path.write_text(
            path.read_text('utf-8').replace(vc.README_MARKER, ''), 'utf-8')
        output = root / 'report.json'
        code = vc.main(['--root', str(root), '--output', str(output)])
        self.assertEqual(code, 1)
        report = json.loads(output.read_text('utf-8'))
        self.assertFalse(report['test_and_doc_alignment']['readme_states_pending_replacement'])

    def test_missing_workflow_exit_one(self):
        root = self.build_tree()
        (root / vc.WORKFLOW_DIR / 'triton-refresh.yml').unlink()
        output = root / 'report.json'
        code = vc.main(['--root', str(root), '--output', str(output)])
        self.assertEqual(code, 1)
        report = json.loads(output.read_text('utf-8'))
        self.assertEqual(report['config_facts']['triton-refresh.yml']['status'], 'missing')


if __name__ == '__main__':
    unittest.main()
