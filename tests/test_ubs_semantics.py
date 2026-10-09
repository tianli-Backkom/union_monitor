"""REQ-041 · UBS代表值和跨仓算法保持正确 — 测试。

锁定 scripts/verify_ubs_semantics.py 的独立重算语义：
- 代表批次选择：最长可测量终态 E2E，并列取 trigger 编号较大者（AC02）；
  任务值仅取代表批次，同类缺失或关联不唯一留空，不从其他批次补取（AC02）
- 批次资格：running/incomplete 排除，已完成取消可测量；事件时间与任务算术
- 跨仓参与规则：success/partial 且快照范围==索引范围参与；失败/过期/缺快照
  排除并记录原因，合法零 PR 仓库保留（AC03）
- 复合 PR 主键与批次 URL 唯一、跨仓同号 PR 互不污染（AC04）
- 合成目录树：干净树退出码 0，篡改代表值/事件时间/重复 URL 退出码 1；
  Node 前端算法（web/core.js）交叉核对构成非循环锁定
- 提交证据（ubs-semantics-evidence.json）：冻结输入 203 PR/826 批次、
  x86/ARM/DT 有效样本 191/203/195、四类差异 0、基线 matched
"""
import copy
import io
import json
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'scripts'))

import verify_ubs_semantics as va  # noqa: E402

EVIDENCE_PATH = ROOT / 'audit' / '2026-10-09' / 'evidence' / 'ubs-semantics-evidence.json'


def make_child(number, kind, *, result='SUCCESS', queue_ms=200, duration_ms=800,
               association_valid=True, building=False, repo='alpha'):
    url = f'https://ci.example/{kind}/{repo}/{number}/'
    return {'url': url, 'kind': kind, 'association_valid': association_valid,
            'building': building, 'result': result, 'queue_ms': queue_ms,
            'duration_ms': duration_ms, 'total_ms': queue_ms + duration_ms,
            'start_ms': 1500, 'end_ms': 1500 + duration_ms}


def make_batch(number, *, request_ms=1000, scheduled_ms=1100, complete=True,
               children=(), trigger_result='SUCCESS', trigger_building=False,
               trigger_end=5000, event_id=None, repo='alpha'):
    url = f'https://ci.example/trigger/{repo}/{number}/'
    trigger = {'url': url, 'result': trigger_result, 'building': trigger_building,
               'start_ms': 1200, 'end_ms': trigger_end,
               'duration_ms': trigger_end - 1200, 'queue_ms': 50,
               'total_ms': 50 + (trigger_end - 1200), 'scheduled_ms': scheduled_ms}
    children = list(children)
    jobs = [trigger] + children
    ends = [job['end_ms'] for job in jobs]
    end = (max(ends) if complete and all(value is not None for value in ends)
           else None)
    e2e = end - request_ms if end is not None and end >= request_ms else None
    status = ('running' if any(job['building'] for job in jobs)
              else 'incomplete' if (not complete
                                    or any(job['result'] is None for job in jobs))
              else 'failure' if any(job['result'] != 'SUCCESS' for job in jobs)
              else 'success' if children else 'incomplete')
    cancelled = any(job['result'] in ('ABORTED', 'NOT_BUILT') for job in jobs)
    jenkins = (end - scheduled_ms if end is not None and end >= scheduled_ms
               else None)
    return {'url': url, 'number': number, 'request_ms': request_ms,
            'scheduled_ms': scheduled_ms, 'complete': complete, 'trigger': trigger,
            'children': children, 'end_ms': end, 'e2e_ms': e2e,
            'jenkins_ms': jenkins, 'status': status, 'cancelled': cancelled,
            'eligible': status in ('success', 'failure') and e2e is not None,
            'event_id': event_id}


class IndependentImplementationTests(unittest.TestCase):
    """独立重算纯函数语义（AC02 资格与并列、任务留空、插值）。"""

    def test_own_batch_status_and_eligibility(self):
        success = make_batch(10, children=[make_child(10, 'x86')])
        derived = va.own_batch(success)
        self.assertEqual(derived['status'], 'success')
        self.assertTrue(derived['eligible'])
        self.assertEqual(derived['e2e_ms'], 4000)
        self.assertEqual(derived['jenkins_ms'], 3900)
        self.assertFalse(derived['cancelled'])
        running = make_batch(11, children=[make_child(11, 'x86', building=True)])
        self.assertEqual(va.own_batch(running)['status'], 'running')
        self.assertFalse(va.own_batch(running)['eligible'])
        incomplete = make_batch(12, complete=False)
        self.assertEqual(va.own_batch(incomplete)['status'], 'incomplete')
        self.assertFalse(va.own_batch(incomplete)['eligible'])
        failure = make_batch(13, children=[make_child(13, 'x86', result='FAILURE')])
        self.assertEqual(va.own_batch(failure)['status'], 'failure')
        self.assertTrue(va.own_batch(failure)['eligible'])
        cancelled = make_batch(14, trigger_result='ABORTED',
                               children=[make_child(14, 'x86')])
        self.assertTrue(va.own_batch(cancelled)['cancelled'])
        self.assertTrue(va.own_batch(cancelled)['eligible'])

    def test_representative_longest_then_tie_breaks_by_number(self):
        short = make_batch(12, children=[make_child(12, 'x86')])
        long = make_batch(15, trigger_end=6000, children=[make_child(15, 'arm')])
        metrics, best = va.representative({'batches': [short, long], 'events': []})
        self.assertEqual(metrics['representative_batch_number'], 15)
        self.assertEqual(best['number'], 15)
        tie_a = make_batch(12, children=[make_child(12, 'x86')])
        tie_b = make_batch(99, children=[make_child(99, 'arm')])
        metrics, best = va.representative({'batches': [tie_a, tie_b], 'events': []})
        self.assertEqual(metrics['e2e_ms'], 4000)
        self.assertEqual(metrics['representative_batch_number'], 99)

    def test_representative_task_nulls_and_no_cross_batch_borrowing(self):
        rep = make_batch(99, trigger_end=6000, children=[make_child(99, 'arm')])
        other = make_batch(12, trigger_end=5000,
                           children=[make_child(12, 'x86'), make_child(12, 'dt')])
        metrics, _ = va.representative({'batches': [rep, other], 'events': []})
        self.assertEqual(metrics['representative_batch_number'], 99)
        self.assertIsNone(metrics['x86']['url'])
        self.assertIsNone(metrics['x86']['queue_ms'])
        self.assertIsNone(metrics['dt']['url'])
        self.assertEqual(metrics['arm']['queue_ms'], 200)
        ambiguous = make_batch(98, trigger_end=7000, children=[
            make_child(98, 'arm', queue_ms=300), make_child(97, 'arm', queue_ms=400)])
        metrics, _ = va.representative({'batches': [ambiguous], 'events': []})
        self.assertIsNone(metrics['arm']['url'])
        self.assertIsNone(metrics['arm']['queue_ms'])

    def test_stats_p90_linear_interpolation_and_valid_zero(self):
        summary = va.stats([600, 600, 900])
        self.assertEqual(summary['n'], 3)
        self.assertAlmostEqual(summary['mean'], 700.0)
        self.assertAlmostEqual(summary['p90'], 840.0)
        summary = va.stats([None, -5, 0, 1000])
        self.assertEqual(summary['n'], 2)
        self.assertAlmostEqual(summary['mean'], 500.0)
        self.assertAlmostEqual(summary['p90'], 900.0)

    def test_equal_numeric_tolerance(self):
        self.assertTrue(va.equal(2723354.8000000003, 2723354.8000000004))
        self.assertFalse(va.equal(1.0, 2.0))
        self.assertTrue(va.equal({'a': [1, 2]}, {'a': [1, 2]}))


class ParticipationTests(unittest.TestCase):
    """AC03：参与规则与排除原因。"""

    def test_participation_rules_and_exclusion_reasons(self):
        index = {'start_ms': 1000, 'end_ms': 9000, 'repositories': [
            {'name': 'ok', 'status': 'success'},
            {'name': 'half', 'status': 'partial'},
            {'name': 'down', 'status': 'failed'},
            {'name': 'wait', 'status': 'pending'},
            {'name': 'old', 'status': 'success'},
        ]}
        current = {'meta': {'start_ms': 1000, 'end_ms': 9000}}
        stale = {'meta': {'start_ms': 100, 'end_ms': 900}}
        snapshots = {'ok': current, 'half': current, 'down': current,
                     'wait': None, 'old': stale}
        entries = {e['name']: e for e in va.participation(index, snapshots)}
        self.assertTrue(entries['ok']['participates'])
        self.assertEqual(entries['ok']['reason'], 'participates')
        self.assertTrue(entries['half']['participates'])
        self.assertFalse(entries['down']['participates'])
        self.assertEqual(entries['down']['reason'], 'excluded_status_failed')
        self.assertFalse(entries['wait']['participates'])
        self.assertEqual(entries['wait']['reason'], 'snapshot_missing')
        self.assertFalse(entries['old']['participates'])
        self.assertEqual(entries['old']['reason'], 'stale_range')


class SyntheticTreeTests(unittest.TestCase):
    """合成目录树：干净树通过；篡改代表值/事件时间/重复 URL 退出码 1。"""

    def build_tree(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / 'web/data/repos').mkdir(parents=True)
        tie_a = make_batch(12, children=[make_child(12, 'x86')])
        tie_b = make_batch(99, children=[make_child(99, 'arm')])
        pr7 = {'number': 7, 'batches': [tie_a, tie_b], 'events': []}
        rep50 = make_batch(50, trigger_end=6000, event_id='e1', children=[
            make_child(50, 'x86'),
            make_child(50, 'arm', queue_ms=300),
            make_child(60, 'arm', queue_ms=400),
            make_child(50, 'dt'),
        ])
        running51 = make_batch(51, children=[make_child(51, 'x86', building=True)])
        pr8 = {'number': 8, 'batches': [rep50, running51],
               'events': [{'id': 'e1', 'time_ms': 1000}]}
        pr30 = {'number': 30,
                'batches': [make_batch(30, trigger_end=5500, repo='gamma',
                                       children=[make_child(30, 'x86', repo='gamma')])],
                'events': []}
        for pr in (pr7, pr8, pr30):
            pr['metrics'] = va.representative(pr)[0]
        alpha = {'meta': {'repository': 'org/alpha', 'start_ms': 1000,
                          'end_ms': 9000}, 'prs': [pr7, pr8]}
        beta = {'meta': {'repository': 'org/beta', 'start_ms': 1000,
                         'end_ms': 9000}, 'prs': []}
        gamma = {'meta': {'repository': 'org/gamma', 'start_ms': 1000,
                          'end_ms': 9000}, 'prs': [pr30]}
        index = {'schema_version': 3, 'start_ms': 1000, 'end_ms': 9000,
                 'repositories': [
                     {'name': 'alpha', 'repository': 'org/alpha',
                      'snapshot': 'repos/alpha.json', 'status': 'success'},
                     {'name': 'beta', 'repository': 'org/beta',
                      'snapshot': 'repos/beta.json', 'status': 'success'},
                     {'name': 'gamma', 'repository': 'org/gamma',
                      'snapshot': 'repos/gamma.json', 'status': 'failed'}]}
        (root / 'web/data/repositories.json').write_text(json.dumps(index), 'utf-8')
        (root / 'web/data/repos/alpha.json').write_text(json.dumps(alpha), 'utf-8')
        (root / 'web/data/repos/beta.json').write_text(json.dumps(beta), 'utf-8')
        (root / 'web/data/repos/gamma.json').write_text(json.dumps(gamma), 'utf-8')
        shutil.copy(ROOT / 'web/core.js', root / 'web/core.js')
        return root

    def rewrite_alpha(self, root, mutate):
        path = root / 'web/data/repos/alpha.json'
        snapshot = json.loads(path.read_text('utf-8'))
        mutate(snapshot)
        path.write_text(json.dumps(snapshot), 'utf-8')

    def run_tool(self, root):
        output = root / 'report.json'
        with redirect_stdout(io.StringIO()):
            code = va.main(['--root', str(root), '--output', str(output)])
        return code, json.loads(output.read_text('utf-8'))

    def test_clean_tree_exit_zero(self):
        root = self.build_tree()
        code, report = self.run_tool(root)
        self.assertEqual(code, 0)
        self.assertEqual(report['overall']['status'], 'verified')
        self.assertEqual(report['counts'], {'prs': 3, 'batches': 5,
                                            'participating_metrics_checked': 2})
        self.assertEqual(report['input']['participating_repos'], 2)
        self.assertEqual(report['input']['excluded_repos'], ['gamma'])
        self.assertEqual(report['input']['zero_pr_participating_repos'], ['beta'])
        reasons = {e['name']: e['reason'] for e in report['input']['repositories']}
        self.assertEqual(reasons['gamma'], 'excluded_status_failed')
        census = report['representative_recheck']['tie_census']
        self.assertEqual(census['prs_with_tied_max_e2e'], 1)
        self.assertEqual(census['tie_break_violations'], [])
        for key in ('metrics_differences', 'batch_field_differences',
                    'event_time_differences', 'job_arithmetic_differences'):
            self.assertEqual(report['representative_recheck'][key], 0, key)
        self.assertTrue(report['identity']['composite_pr_keys_unique'])
        self.assertTrue(report['identity']['batch_urls_unique'])
        self.assertEqual(report['identity']['pr_numbers_in_multiple_repos'], [])
        self.assertEqual(report['cross_repo']['valid_samples'],
                         {'x86': 1, 'arm': 1, 'dt': 1})
        self.assertEqual(report['frontend_cross_check']['status'], 'ran')
        self.assertTrue(report['frontend_cross_check']['metrics_matched'])
        self.assertTrue(report['frontend_cross_check']['aggregate_matched'])
        self.assertEqual(report['audit_baseline_comparison']['status'],
                         'not_applicable_input_drifted')

    def test_tampered_representative_metrics_exit_one(self):
        root = self.build_tree()

        def mutate(snapshot):
            snapshot['prs'][0]['metrics']['e2e_ms'] = 99999

        self.rewrite_alpha(root, mutate)
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertEqual(report['overall']['status'], 'failed')
        self.assertEqual(report['representative_recheck']['metrics_differences'], 1)

    def test_event_time_mismatch_exit_one(self):
        root = self.build_tree()

        def mutate(snapshot):
            snapshot['prs'][1]['events'][0]['time_ms'] = 2000

        self.rewrite_alpha(root, mutate)
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertEqual(report['representative_recheck']['event_time_differences'], 1)

    def test_duplicate_batch_url_exit_one(self):
        root = self.build_tree()

        def mutate(snapshot):
            duplicate = copy.deepcopy(snapshot['prs'][0]['batches'][0])
            snapshot['prs'][0]['batches'].append(duplicate)

        self.rewrite_alpha(root, mutate)
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertFalse(report['identity']['batch_urls_unique'])
        self.assertEqual(report['identity']['batch_urls'], 6)


class CommittedEvidenceTests(unittest.TestCase):
    """提交证据（ubs-semantics-evidence.json）：冻结输入保持结论。"""

    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(EVIDENCE_PATH.read_text('utf-8'))

    def test_frozen_counts_and_valid_samples(self):
        self.assertEqual(self.report['counts'],
                         {'prs': 203, 'batches': 826,
                          'participating_metrics_checked': 203})
        self.assertEqual(self.report['cross_repo']['valid_samples'],
                         {'x86': 191, 'arm': 203, 'dt': 195})
        self.assertTrue(self.report['input']['matches_audit_frozen_input'])
        self.assertEqual(self.report['input']['bundle_fingerprint'],
                         va.AUDIT_BASELINE_FINGERPRINT)

    def test_zero_differences_and_identity(self):
        recheck = self.report['representative_recheck']
        for key in ('metrics_differences', 'batch_field_differences',
                    'event_time_differences', 'job_arithmetic_differences'):
            self.assertEqual(recheck[key], 0, key)
        self.assertEqual(recheck['tie_census']['prs_with_tied_max_e2e'], 0)
        self.assertEqual(recheck['tie_census']['tie_break_violations'], [])
        identity = self.report['identity']
        self.assertEqual(identity['composite_pr_keys'], 203)
        self.assertTrue(identity['composite_pr_keys_unique'])
        self.assertEqual(identity['batch_urls'], 826)
        self.assertTrue(identity['batch_urls_unique'])
        self.assertEqual(identity['pr_numbers_in_multiple_repos'], [])

    def test_frontend_and_baseline_matched(self):
        frontend = self.report['frontend_cross_check']
        self.assertEqual(frontend['status'], 'ran')
        self.assertEqual(frontend['prs'], 203)
        self.assertTrue(frontend['metrics_matched'])
        self.assertTrue(frontend['aggregate_matched'])
        baseline = self.report['audit_baseline_comparison']
        self.assertEqual(baseline['status'], 'matched')
        self.assertEqual(baseline['prs'], {'computed': 203, 'baseline': 203})
        self.assertEqual(baseline['batches'], {'computed': 826, 'baseline': 826})
        self.assertEqual(baseline['valid_samples'],
                         {'x86': {'computed': 191, 'baseline': 191},
                          'arm': {'computed': 203, 'baseline': 203},
                          'dt': {'computed': 195, 'baseline': 195}})
        self.assertEqual(baseline['per_repository'], 'matched')
        self.assertEqual(baseline['aggregate'], 'matched')

    def test_participation_all_success_repos(self):
        info = self.report['input']
        self.assertEqual(info['participating_repos'], 9)
        self.assertEqual(info['excluded_repos'], [])
        self.assertEqual(info['zero_pr_participating_repos'], [])
        for entry in info['repositories']:
            self.assertEqual(entry['status'], 'success', entry['name'])
            self.assertEqual(entry['reason'], 'participates', entry['name'])

    def test_aggregate_locks_baseline_values(self):
        aggregate = self.report['cross_repo']['aggregate']
        self.assertEqual(aggregate['e2e']['n'], 203)
        self.assertAlmostEqual(aggregate['e2e']['p90'], 2723354.8, places=3)
        for kind, expected in (('x86', 191), ('arm', 203), ('dt', 195)):
            self.assertEqual(aggregate[kind]['queue']['n'], expected, kind)
            self.assertEqual(aggregate[kind]['duration']['n'], expected, kind)
            self.assertEqual(aggregate[kind]['total']['n'], expected, kind)


if __name__ == '__main__':
    unittest.main()
