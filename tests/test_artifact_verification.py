"""REQ-038 · 原始工件补齐及历史影响核验 — 测试。

锁定 scripts/verify_artifacts.py 的报告语义：
- 不可变输入（冻结 fixture + 审计期导出 CSV）独立重算：双 CSV 逐批一致、
  PR/SHA 传播零失配、attempt 身份/配对/序列自洽、7 个真实重跑批次的新旧
  规则值与高估上限、S01 合成输入与真实数据隔离
- 提交报告（artifact-verification.json）结构与语义：REQ-023 计数等式、
  D10 缺失工件未验证标注、REQ-025 分项推导、AC04 部署核验记录
- 工具在合成目录树上可执行且能发现漂移（干净树退出码 0、漂移树退出码 1）
"""
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import verify_artifacts as va  # noqa: E402

FREEZE_PATH = ROOT / 'tests' / 'fixtures' / 'triton-audit-freeze.json'
AUDIT = ROOT / 'audit' / '2026-10-09' / 'evidence'
REPORT_PATH = AUDIT / 'artifact-verification.json'


def load_freeze():
    return json.loads(FREEZE_PATH.read_text('utf-8'))


class TritonImmutableChecks(unittest.TestCase):
    """不可变输入（冻结 fixture + 审计期导出）上的独立重算。"""

    @classmethod
    def setUpClass(cls):
        cls.freeze = load_freeze()

    def test_freeze_vs_audit_exports(self):
        result = va.triton_csv_checks(ROOT, self.freeze)
        self.assertEqual(result['compared'], 132)
        self.assertEqual(result['consistent'], 132)
        self.assertEqual(result['differences'], [])
        self.assertEqual(len(result['covered_batches']), 66)
        self.assertEqual(result['differing_batches'], [])

    def test_pr_identity_propagation(self):
        result = va.triton_pr_propagation(self.freeze)
        self.assertEqual(result['batches'], 66)
        self.assertEqual(result['workflows'], 434)
        self.assertEqual(result['mismatches'], [])

    def test_attempt_history_checks(self):
        result = va.triton_attempt_checks(self.freeze)
        self.assertEqual(result['rerun_batches'], 7)
        self.assertTrue(result['initial_unique'])
        self.assertEqual(result['duplicate_run_attempt'], 0)
        self.assertEqual(result['bad_sequences'], [])
        self.assertFalse(result['same_run_multi_attempt_preserved'])
        self.assertEqual(result['rerun_identity_ids'], 7)
        self.assertEqual(result['rerun_paired_with_initial'], 7)

    def test_rerun_impact_real_data(self):
        result = va.rerun_impact(ROOT, self.freeze)
        entries = result['rerun_batches']
        self.assertEqual(len(entries), 7)
        for entry in entries:
            self.assertTrue(entry['start_at_equals_created'])
            self.assertTrue(entry['recorded_matches_old_rule'])
            self.assertIsNotNone(entry['old_rule_overestimate_bound_seconds'])
            lower, upper = entry['new_rule_e2e_range_seconds']
            self.assertAlmostEqual(upper, entry['old_rule_e2e_seconds'], places=6)
            self.assertLessEqual(lower, upper)
        bounds = sorted(e['old_rule_overestimate_bound_seconds'] for e in entries)
        self.assertEqual(bounds, [4.0, 5.0, 8.0, 10.0, 13.0, 36.0, 60.0])
        summary = result['summary']
        self.assertEqual(summary['rerun_batches'], 7)
        self.assertEqual(summary['recorded_matches_old'], 7)
        self.assertEqual(summary['provably_affected_batches'], 0)
        self.assertEqual(summary['max_overestimate_bound_seconds'], 60.0)
        self.assertEqual(summary['median_overestimate_bound_seconds'], 10.0)

    def test_s01_synthetic_separated_from_real(self):
        result = va.rerun_impact(ROOT, self.freeze)
        s01 = result['s01']
        self.assertIsNotNone(s01)
        self.assertTrue(s01['is_synthetic'])
        self.assertEqual(s01['old_rule_seconds'], 7500.0)
        self.assertEqual(s01['new_rule_seconds'], 300.0)
        self.assertEqual(s01['current_code_recomputed_seconds'], 300.0)
        self.assertIsNone(s01['recompute_error'])
        synthetic_ids = {s01['input'].get('id')}
        for entry in result['rerun_batches']:
            self.assertNotIn(entry['run_id'], synthetic_ids)


class CommittedReportTest(unittest.TestCase):
    """提交的补证报告（artifact-verification.json）结构与语义。"""

    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(REPORT_PATH.read_text('utf-8'))

    def test_sections_and_overall_derivation(self):
        report = self.report
        self.assertEqual(set(report['sections']), {'ac01', 'ac02', 'ac03', 'ac04'})
        for status in report['sections'].values():
            self.assertIn(status, ('pass', 'partial', 'unverified', 'differ', 'not_applicable'))
        self.assertEqual(report['overall_status'], 'unverified')
        self.assertTrue(report['overall_reason'])
        self.assertTrue(any(s in ('unverified', 'partial') for s in report['sections'].values()))
        self.assertEqual(report['sections']['ac04'], 'unverified')

    def test_ac02_arithmetic_per_category(self):
        categories = self.report['ac02_comparisons']
        for name in ('raw_timestamps', 'queue_components', 'pr_identity', 'attempt_history'):
            category = categories[name]
            total = (category['verified_consistent'] + category['derived_consistent']
                     + category['differ'] + category['missing_evidence'])
            self.assertEqual(total, category['applicable'], name)
            self.assertGreater(category['applicable'], 0, name)

    def test_ac01_inventory_marks_d10_missing(self):
        inventory = self.report['ac01_inventory']
        paths = {entry['path'] for entry in inventory['artifacts']}
        for declared in va.D10_PATHS:
            self.assertIn(declared, paths)
        for entry in inventory['artifacts']:
            if entry['exists']:
                if 'sha256' in entry:
                    self.assertRegex(entry['sha256'], r'^[0-9a-f]{64}$')
            else:
                self.assertEqual(entry['status'], 'unverified')
                self.assertTrue(entry.get('reason'))

    def test_ac01_freeze_entry_matches_immutable_fixture(self):
        inventory = self.report['ac01_inventory']
        entry = next(e for e in inventory['artifacts'] if e['path'].endswith('triton-audit-freeze.json'))
        self.assertEqual(entry['sha256'], va.sha256_file(FREEZE_PATH))
        self.assertEqual(entry['window']['window_start'], '2026-10-06T00:13:06Z')
        self.assertEqual(entry['window']['window_end'], '2026-10-09T00:13:06Z')
        self.assertEqual(entry['window']['collected_at'], '2026-10-09T00:17:38.669255Z')

    def test_ac04_deployment_sections(self):
        deployment = self.report['ac04_deployment']
        self.assertIn(deployment['local_bundle']['status'],
                      ('verified', 'mismatch', 'absent', 'invalid', 'error'))
        if deployment['local_bundle']['status'] == 'verified':
            self.assertRegex(deployment['local_bundle']['fingerprint'], r'^sha256:[0-9a-f]{64}$')
        merged = deployment['merged_dashboard_deployment']
        self.assertEqual(merged['status'], 'unverified')
        self.assertTrue(merged['reasons'])
        self.assertIn('拒绝', merged['old_site_scraping_substitute'])
        probe = deployment['site_probe']
        self.assertTrue(probe['results'])
        self.assertIn('不可冒充', probe['conclusion'])

    def test_site_probe_file_structure(self):
        probe = json.loads((AUDIT / 'site-probe.json').read_text('utf-8'))
        self.assertTrue(probe['probed_at'])
        urls = {entry['url'] for entry in probe['urls']}
        self.assertTrue(any('ubs_core_monitor' in url for url in urls))
        self.assertTrue(any('Triton-Ascend_monitor' in url for url in urls))
        for entry in probe['urls']:
            self.assertIn('relation', entry)
            self.assertIn(entry['relation'], ('matches_local_audit_snapshot',
                                              'differs_from_local_audit_snapshot',
                                              'no_local_counterpart', 'absent_on_site', 'unreachable'))


class SyntheticTreeTest(unittest.TestCase):
    """工具在合成目录树上的行为：干净树通过、漂移树退出码 1、界计算正确。"""

    def build_tree(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / 'web/data/repos').mkdir(parents=True)
        (root / 'tests/fixtures').mkdir(parents=True)
        (root / 'audit/2026-10-09/evidence').mkdir(parents=True)
        index = {'schema_version': 3, 'start_ms': 1000, 'end_ms': 2000,
                 'repositories': [{'name': 'alpha', 'repository': 'org/alpha',
                                   'snapshot': 'repos/alpha.json', 'status': 'success'}]}
        (root / 'web/data/repositories.json').write_text(json.dumps(index), 'utf-8')
        batch = {
            'url': 'https://ci.example/trigger/1/', 'number': 1, 'sha': 'abc',
            'event_id': 'e1', 'event_type': 'retest', 'request_ms': 1000,
            'e2e_ms': 500, 'jenkins_ms': 400, 'complete': True, 'status': 'success',
            'trigger': {'url': 'https://ci.example/trigger/1/', 'queue_ms': 10,
                        'scheduled_ms': 1100, 'start_ms': 1110, 'end_ms': 1500, 'result': 'SUCCESS'},
            'children': [{'url': 'https://ci.example/child/7/', 'queue_ms': 20,
                          'duration_ms': 30, 'total_ms': 50, 'result': 'SUCCESS'}],
        }
        snapshot = {'meta': {'repository': 'org/alpha', 'start_ms': 1000, 'end_ms': 2000},
                    'prs': [{'number': 7, 'batches': [batch], 'events': [{'id': 'e1'}]}]}
        (root / 'web/data/repos/alpha.json').write_text(json.dumps(snapshot), 'utf-8')
        freeze = {
            'repo': 'o/r', 'window_start': '2026-10-08T00:00:00Z',
            'window_end': '2026-10-08T02:00:00Z', 'collected_at': '2026-10-08T02:05:00Z',
            'summary': {},
            'batches': [
                {'id': '11-aaaa-initial', 'pr': 11, 'sha': 'aaaa', 'kind': 'initial',
                 'base_branch': 'main', 'start_at': '2026-10-08T00:00:00Z',
                 'end_at': '2026-10-08T00:10:00Z', 'status': 'success',
                 'duration_seconds': 600.0, 'npu_queue_seconds': None, 'approximate': True,
                 'pr_url': 'https://github.com/o/r/pull/11',
                 'action_url': 'https://github.com/o/r/actions/runs/111',
                 'e2e_index': 1, 'e2e_total': 2,
                 'workflows': [{'id': 111, 'attempt': 1, 'pr': 11, 'head_sha': 'aaaa',
                                'created_at': '2026-10-08T00:00:00Z',
                                'updated_at': '2026-10-08T00:10:00Z', 'jobs': []}]},
                {'id': '11-aaaa-rerun-222-2', 'pr': 11, 'sha': 'aaaa', 'kind': 'rerun',
                 'base_branch': 'main', 'start_at': '2026-10-08T01:00:00Z',
                 'end_at': '2026-10-08T01:05:00Z', 'status': 'success',
                 'duration_seconds': 300.0, 'npu_queue_seconds': None, 'approximate': True,
                 'pr_url': 'https://github.com/o/r/pull/11',
                 'action_url': 'https://github.com/o/r/actions/runs/222',
                 'e2e_index': 2, 'e2e_total': 2,
                 'workflows': [{'id': 222, 'attempt': 2, 'pr': 11, 'head_sha': 'aaaa',
                                'created_at': '2026-10-08T01:00:00Z',
                                'updated_at': '2026-10-08T01:05:00Z',
                                'jobs': [{'created_at': '2026-10-08T01:00:40Z',
                                          'started_at': '2026-10-08T01:01:00Z'}]}]},
            ],
        }
        (root / 'tests/fixtures/triton-audit-freeze.json').write_text(json.dumps(freeze), 'utf-8')
        (root / 'web/data/triton.json').write_text(json.dumps(freeze), 'utf-8')
        header = ['pr', 'title', 'sha', 'base_branch', 'kind', 'start_at', 'end_at', 'status',
                  'duration_seconds', 'npu_queue_seconds', 'approximate', 'critical_workflow',
                  'missing', 'pr_url', 'action_url']
        for name in ('triton-export.csv', 'triton-pages-export.csv'):
            with (root / 'audit/2026-10-09/evidence' / name).open('w', encoding='utf-8-sig', newline='') as handle:
                writer = csv.DictWriter(handle, fieldnames=header)
                writer.writeheader()
                for b in freeze['batches']:
                    writer.writerow({'pr': b['pr'], 'title': 't', 'sha': b['sha'],
                                     'base_branch': b['base_branch'], 'kind': b['kind'],
                                     'start_at': b['start_at'], 'end_at': b['end_at'],
                                     'status': b['status'], 'duration_seconds': b['duration_seconds'],
                                     'npu_queue_seconds': '', 'approximate': b['approximate'],
                                     'critical_workflow': '', 'missing': '',
                                     'pr_url': b['pr_url'], 'action_url': b['action_url']})
        ubs_header = ['仓库', 'PR', 'trigger', 'E2E结果', '触发类型', 'SHA', '请求时间', 'E2E ms',
                      'Jenkins ms', '有效E2E批次', '用于PR效率汇总', '子任务', '子任务结果',
                      '排队ms', '执行ms', '总计ms', '数据问题']
        with (root / 'audit/2026-10-09/evidence/ubs-batch-export.csv').open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=ubs_header)
            writer.writeheader()
            writer.writerow({'仓库': 'org/alpha', 'PR': '7', 'trigger': 'https://ci.example/trigger/1/',
                             'E2E结果': '成功', '触发类型': '重跑请求', 'SHA': 'abc',
                             '请求时间': '1970-01-01 08:00:01', 'E2E ms': '500', 'Jenkins ms': '400',
                             '有效E2E批次': 'true', '用于PR效率汇总': 'false',
                             '子任务': 'https://ci.example/child/7/', '子任务结果': 'SUCCESS',
                             '排队ms': '20', '执行ms': '30', '总计ms': '50', '数据问题': ''})
        return root, freeze

    def test_clean_tree_exit_zero(self):
        root, _ = self.build_tree()
        output = root / 'report.json'
        code = va.main(['--root', str(root), '--output', str(output)])
        self.assertEqual(code, 0)
        report = json.loads(output.read_text('utf-8'))
        self.assertEqual(report['overall_status'], 'unverified')
        categories = report['ac02_comparisons']
        raw = categories['raw_timestamps']
        self.assertEqual(raw['applicable'], 3)
        self.assertEqual(raw['derived_consistent'], 3)
        self.assertEqual(raw['differ'], 0)
        queue = categories['queue_components']
        self.assertEqual(queue['applicable'], 2)
        self.assertEqual(queue['derived_consistent'], 1)
        identity = categories['pr_identity']
        self.assertEqual(identity['applicable'], 3)
        self.assertEqual(identity['derived_consistent'], 3)
        history = categories['attempt_history']
        self.assertEqual(history['applicable'], 2)
        self.assertEqual(history['derived_consistent'], 2)
        self.assertEqual(report['ac03_rerun_impact']['summary']['rerun_batches'], 1)
        self.assertEqual(report['ac01_inventory']['d10_declared_missing'], va.D10_PATHS)

    def test_drift_tree_exit_one(self):
        root, _ = self.build_tree()
        path = root / 'audit/2026-10-09/evidence/triton-export.csv'
        path.write_text(path.read_text('utf-8-sig').replace('600.0', '999.0'), 'utf-8-sig')
        output = root / 'report.json'
        code = va.main(['--root', str(root), '--output', str(output)])
        self.assertEqual(code, 1)
        report = json.loads(output.read_text('utf-8'))
        self.assertEqual(report['overall_status'], 'failed')
        self.assertGreater(report['ac02_comparisons']['raw_timestamps']['differ'], 0)

    def test_rerun_bound_math(self):
        root, freeze = self.build_tree()
        result = va.rerun_impact(root, freeze)
        entry = result['rerun_batches'][0]
        self.assertEqual(entry['old_rule_e2e_seconds'], 300.0)
        self.assertEqual(entry['old_rule_overestimate_bound_seconds'], 40.0)
        self.assertEqual(entry['new_rule_e2e_range_seconds'], [260.0, 300.0])
        self.assertFalse(entry['provably_identical_to_new_rule'])
        freeze['batches'][1]['workflows'][0]['jobs'] = []
        result = va.rerun_impact(root, freeze)
        entry = result['rerun_batches'][0]
        self.assertIsNone(entry['old_rule_overestimate_bound_seconds'])
        self.assertEqual(entry['new_rule_e2e_range_seconds'], [None, 300.0])
        freeze['batches'][1]['duration_seconds'] = 299.0
        result = va.rerun_impact(root, freeze)
        self.assertFalse(result['rerun_batches'][0]['recorded_matches_old_rule'])

    def test_derive_overall(self):
        sections = {'ac01': 'pass', 'ac02': 'partial', 'ac03': 'partial', 'ac04': 'unverified'}
        self.assertEqual(va.derive_overall(sections, False), 'unverified')
        self.assertEqual(va.derive_overall({'ac01': 'pass', 'ac02': 'differ'}, False), 'failed')
        self.assertEqual(va.derive_overall(sections, True), 'failed')
        self.assertEqual(va.derive_overall({'ac01': 'pass', 'ac02': 'verified'}, False), 'verified')
        self.assertEqual(va.derive_overall({'ac01': 'pass', 'ac02': 'not_applicable'}, False), 'verified')


if __name__ == '__main__':
    unittest.main()
