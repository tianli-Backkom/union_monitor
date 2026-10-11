"""REQ-045 · UBS正常详情与下钻能力保持 — 测试。

锁定 scripts/verify_ubs_detail.py 的独立重算语义：
- 事件分组：批次按 event_id||空串 分组、事件按 id 去重（后写覆盖值、
  保留首插位置）、失配批次入「关联未知/失配」组并注明原因、全部批次
  恰好覆盖一次（U24 口径）
- 失败等待：status=failure 且 E2E 有限非负，E2E 降序并列编号升序；
  取消终态纳入（AC04）；无候选返回 None
- 后续成功不抹去历史失败：成功请求晚于失败批次，null 按 0 比较
- 分钟/精确值：zh-CN 千分位、(0,600)ms 显示 '<0.01'、ms/s 单位切换
- 跨仓序列：失败等待/最长 E2E 按 E2E 降序、并列创建时间降序
- 合成目录树：干净树退出码 0；篡改 core.js failedWait 过滤、app.js
  代表展开表达式或 minute 阈值退出码 1（U25/U27/U28/U30/U32/U33/A07）
- 提交证据（ubs-detail-evidence.json）：冻结输入保持结论与基线回放
"""
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

import verify_ubs_detail as vud  # noqa: E402

EVIDENCE_PATH = (ROOT / 'audit' / '2026-10-09' / 'evidence'
                 / 'ubs-detail-evidence.json')


def make_child(number, kind='x86', *, result='FAILURE', repo='alpha'):
    url = f'https://ci.example/{kind}/{repo}/{number}/'
    return {'url': url, 'kind': kind, 'association_valid': True,
            'building': False, 'result': result, 'queue_ms': 200,
            'duration_ms': 800, 'total_ms': 1000, 'start_ms': 1500,
            'end_ms': 2300, 'scheduled_ms': 1400}


def make_batch(number, *, e2e_ms=4000, repo='alpha', event_id=None,
               result='FAILURE', request_ms=1000, issues=None):
    """REQ-045 合成批次：trigger+单子任务，e2e=请求到全批结束。"""
    trigger_end = request_ms + e2e_ms
    url = f'https://ci.example/trigger/{repo}/{number}/'
    trigger = {'url': url, 'result': 'SUCCESS', 'building': False,
               'start_ms': 1200, 'end_ms': trigger_end,
               'duration_ms': trigger_end - 1200, 'queue_ms': 50,
               'total_ms': 50 + (trigger_end - 1200), 'scheduled_ms': 1100}
    child = make_child(number, result=result, repo=repo)
    children = [child]
    end = max(trigger_end, child['end_ms'])
    status = 'failure' if result != 'SUCCESS' else 'success'
    return {'url': url, 'number': number, 'request_ms': request_ms,
            'scheduled_ms': 1100, 'complete': True, 'trigger': trigger,
            'children': children, 'end_ms': end,
            'e2e_ms': end - request_ms, 'jenkins_ms': end - 1100,
            'status': status,
            'cancelled': result in ('ABORTED', 'NOT_BUILT'),
            'eligible': status in ('success', 'failure'),
            'event_id': event_id, 'sha': None, 'event_type': 'create',
            'issues': issues}


def make_pr(number, created_ms, batches, *, events=None, state='merged',
            issues=None):
    return {'number': number, 'created_ms': created_ms,
            'batches': list(batches), 'state': state,
            'title': f'PR #{number}', 'author': 'dev', 'merged_ms': None,
            'submission_count': 1, 'issues': issues,
            'events': list(events or [])}


class DetailGroupsTests(unittest.TestCase):
    """事件分组语义（U24/未知关联按 REQ-016 口径）。"""

    def test_batches_grouped_by_event_id_in_event_order(self):
        pr = {'events': [{'id': 'e2', 'kind': 'push'},
                         {'id': 'e1', 'kind': 'create'}],
              'batches': [{'url': 'u1', 'event_id': 'e1'},
                          {'url': 'u2', 'event_id': 'e2'},
                          {'url': 'u3', 'event_id': 'e2'}]}
        groups = vud.own_detail_groups(pr)
        self.assertEqual([g['event']['id'] for g in groups], ['e2', 'e1'])
        self.assertEqual([b['url'] for b in groups[0]['batches']],
                         ['u2', 'u3'])
        self.assertEqual([b['url'] for b in groups[1]['batches']], ['u1'])
        self.assertTrue(all(g['reason'] is None for g in groups))

    def test_unmatched_group_reason_and_no_forged_event(self):
        pr = {'events': [{'id': 'e1', 'kind': 'create'}],
              'batches': [{'url': 'u1', 'event_id': 'e1'},
                          {'url': 'u2', 'event_id': ''},
                          {'url': 'u3', 'event_id': None},
                          {'url': 'u4', 'event_id': 'zzz'}]}
        groups = vud.own_detail_groups(pr)
        self.assertEqual(len(groups), 2)
        unmatched = groups[1]
        self.assertEqual(unmatched['event'], {'kind': 'unmatched'})
        self.assertEqual([b['url'] for b in unmatched['batches']],
                         ['u2', 'u3', 'u4'])
        self.assertEqual(unmatched['reason'],
                         '2 批 event_id 为空，1 批 event_id 不在事件列表')

    def test_event_dedup_last_value_wins_first_position(self):
        pr = {'events': [{'id': 'e1', 'kind': 'create', 'sha': 'aaa'},
                         {'id': 'e2', 'kind': 'push'},
                         {'id': 'e1', 'kind': 'retest', 'sha': 'bbb'}],
              'batches': [{'url': 'u1', 'event_id': 'e1'}]}
        groups = vud.own_detail_groups(pr)
        self.assertEqual([g['event']['id'] for g in groups], ['e1', 'e2'])
        self.assertEqual(groups[0]['event']['kind'], 'retest')
        self.assertEqual(groups[0]['event']['sha'], 'bbb')

    def test_all_batches_covered_exactly_once(self):
        pr = {'events': [{'id': 'e1', 'kind': 'create'}],
              'batches': [{'url': 'u1', 'event_id': 'e1'},
                          {'url': 'u2', 'event_id': None},
                          {'url': 'u3', 'event_id': 'zzz'},
                          {'url': 'u4', 'event_id': 'e1'}]}
        covered = [b['url'] for g in vud.own_detail_groups(pr)
                   for b in g['batches']]
        self.assertEqual(sorted(covered),
                         sorted(b['url'] for b in pr['batches']))
        self.assertEqual(len(covered), len(pr['batches']))


class FailedWaitTests(unittest.TestCase):
    """失败等待选择（AC02/AC04 口径）。"""

    def test_filter_and_order(self):
        pr = {'batches': [
            {'url': 'a', 'number': 3, 'status': 'failure', 'e2e_ms': 500},
            {'url': 'b', 'number': 2, 'status': 'failure', 'e2e_ms': 900},
            {'url': 'c', 'number': 1, 'status': 'failure', 'e2e_ms': 900},
            {'url': 'd', 'number': 4, 'status': 'success', 'e2e_ms': 9999},
            {'url': 'e', 'number': 5, 'status': 'failure', 'e2e_ms': None},
            {'url': 'f', 'number': 6, 'status': 'failure', 'e2e_ms': -1},
            {'url': 'g', 'number': 7, 'status': 'running', 'e2e_ms': 800},
            {'url': 'h', 'number': 8, 'status': 'failure', 'e2e_ms': 'x'},
            {'url': 'i', 'number': 9, 'status': 'failure',
             'e2e_ms': float('inf')},
        ]}
        fw = vud.own_failed_wait(pr)
        self.assertEqual(fw['url'], 'c')  # E2E 并列取 trigger 编号较小者

    def test_cancelled_terminal_included(self):
        pr = {'batches': [{'url': 'a', 'number': 1, 'status': 'failure',
                           'e2e_ms': 100, 'cancelled': True}]}
        self.assertEqual(vud.own_failed_wait(pr)['url'], 'a')

    def test_none_when_no_candidates(self):
        self.assertIsNone(vud.own_failed_wait({'batches': []}))
        self.assertIsNone(vud.own_failed_wait(
            {'batches': [{'url': 'a', 'number': 1, 'status': 'success',
                          'e2e_ms': 100}]}))
        self.assertIsNone(vud.own_failed_wait(
            {'batches': [{'url': 'a', 'number': 1, 'status': 'failure',
                          'e2e_ms': None}]}))


class LaterSuccessTests(unittest.TestCase):
    """后续成功不抹去历史失败（AC02 口径）。"""

    def test_later_success_flag(self):
        failed = {'request_ms': 1000}
        later = {'batches': [
            {'status': 'success', 'request_ms': 2000},
            {'status': 'success', 'request_ms': 1000},
            {'status': 'failure', 'request_ms': 3000},
        ]}
        self.assertTrue(vud.own_later_success(later, failed))
        earlier = {'batches': [{'status': 'success', 'request_ms': 999}]}
        self.assertFalse(vud.own_later_success(earlier, failed))

    def test_null_request_ms_coerces_zero(self):
        failed = {'request_ms': None}
        pr = {'batches': [{'status': 'success', 'request_ms': 500}]}
        self.assertTrue(vud.own_later_success(pr, failed))  # JS null→0
        failed2 = {'request_ms': 100}
        pr2 = {'batches': [{'status': 'success', 'request_ms': None}]}
        self.assertFalse(vud.own_later_success(pr2, failed2))


class MinuteExactTests(unittest.TestCase):
    """分钟显示与精确值公式（AC04 口径）。"""

    def test_boundaries(self):
        self.assertEqual(vud.own_minute(None), '—')
        self.assertEqual(vud.own_exact(None), '—')
        self.assertEqual(vud.own_minute(0), '0.00')
        self.assertEqual(vud.own_exact(0), '0 ms')
        self.assertEqual(vud.own_minute(599), '<0.01')
        self.assertEqual(vud.own_exact(599), '599 ms')
        self.assertEqual(vud.own_minute(600), '0.01')
        self.assertEqual(vud.own_exact(999), '999 ms')
        self.assertEqual(vud.own_minute(1000), '0.02')
        self.assertEqual(vud.own_exact(1000), '1.000 s')

    def test_thousands_and_real_values(self):
        self.assertEqual(vud.own_num(1234.5), '1,234.50')
        self.assertEqual(vud.own_num(None), '—')
        self.assertEqual(vud.own_num(5, 0), '5')
        self.assertEqual(vud.own_minute(11064101), '184.40')
        self.assertEqual(vud.own_exact(11064101), '11,064.101 s')
        self.assertEqual(vud.own_minute(50640069), '844.00')
        self.assertEqual(vud.own_exact(50640069), '50,640.069 s')
        self.assertEqual(vud.own_minute(232188), '3.87')
        self.assertEqual(vud.own_exact(61470), '61.470 s')


class CrossRowsTests(unittest.TestCase):
    """跨仓失败等待/最长 E2E 序列排序。"""

    def test_failed_wait_rows_order(self):
        index = {'start_ms': 1000, 'end_ms': 9000, 'repositories': [
            {'name': 'alpha', 'status': 'success'},
            {'name': 'beta', 'status': 'success'}]}

        def pr(number, created, batch):
            return {'number': number, 'created_ms': created,
                    'batches': [batch]}

        snapshots = {
            'alpha': {'meta': {'start_ms': 1000, 'end_ms': 9000}, 'prs': [
                pr(101, 500, {'url': 'a12', 'number': 12,
                              'status': 'failure', 'e2e_ms': 6000,
                              'request_ms': 1000}),
                pr(102, 900, {'url': 'a21', 'number': 21,
                              'status': 'failure', 'e2e_ms': 6000,
                              'request_ms': 1000})]},
            'beta': {'meta': {'start_ms': 1000, 'end_ms': 9000}, 'prs': [
                pr(201, 100, {'url': 'b31', 'number': 31,
                              'status': 'failure', 'e2e_ms': 7000,
                              'request_ms': 1000})]}}
        rows = vud.own_failed_wait_rows(
            vud.own_cross_pairs(index, snapshots))
        self.assertEqual([(r['repo'], r['pr'], r['trigger']) for r in rows],
                         [('beta', 201, 31), ('alpha', 102, 21),
                          ('alpha', 101, 12)])
        self.assertEqual(vud.own_failed_wait_rows([]), [])

    def test_exception_rows_order(self):
        index = {'start_ms': 1000, 'end_ms': 9000, 'repositories': [
            {'name': 'alpha', 'status': 'success'},
            {'name': 'beta', 'status': 'success'}]}
        alpha = {'meta': {'start_ms': 1000, 'end_ms': 9000}, 'prs': [
            make_pr(101, 500, [make_batch(11, e2e_ms=6000,
                                          result='SUCCESS')]),
            make_pr(102, 900, [make_batch(21, e2e_ms=6000,
                                          result='SUCCESS')])]}
        beta = {'meta': {'start_ms': 1000, 'end_ms': 9000}, 'prs': [
            make_pr(201, 100, [make_batch(31, e2e_ms=8000,
                                          result='SUCCESS',
                                          repo='beta')])]}
        rows = vud.own_exception_rows(vud.own_cross_pairs(
            index, {'alpha': alpha, 'beta': beta}))
        self.assertEqual([(r['repo'], r['pr']) for r in rows],
                         [('beta', 201), ('alpha', 102), ('alpha', 101)])
        self.assertEqual([r['e2e_ms'] for r in rows], [8000, 6000, 6000])
        self.assertEqual(vud.own_exception_rows([]), [])


class SyntheticTreeTests(unittest.TestCase):
    """合成目录树：干净树通过；篡改失败等待/代表展开/分钟阈值退出码 1。"""

    def build_tree(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / 'web/data/repos').mkdir(parents=True)
        alpha = {'meta': {'repository': 'org/alpha', 'start_ms': 1000,
                          'end_ms': 9000, 'errors': []}, 'prs': [
            make_pr(101, 500, [
                make_batch(11, e2e_ms=4000, result='SUCCESS',
                           request_ms=2000, event_id='ev1'),
                make_batch(12, e2e_ms=6000, result='ABORTED',
                           event_id='ev2'),
                make_batch(13, e2e_ms=5000, event_id='ev9'),
                make_batch(14, e2e_ms=4500, event_id=None),
            ], events=[{'id': 'ev1', 'kind': 'create', 'time_ms': 400,
                        'sha': 'a1'},
                       {'id': 'ev2', 'kind': 'push', 'time_ms': 600,
                        'sha': 'a2'}]),
            make_pr(102, 900, [make_batch(21, e2e_ms=2000)],
                    issues=['数据缺口']),
        ]}
        beta = {'meta': {'repository': 'org/beta', 'start_ms': 1000,
                         'end_ms': 9000, 'errors': []},
                'prs': [make_pr(201, 100, [make_batch(
                    31, e2e_ms=8000, result='SUCCESS', repo='beta',
                    event_id='ev1')],
                    events=[{'id': 'ev1', 'kind': 'create', 'time_ms': 50,
                             'sha': 'b1'}])]}
        index = {'schema_version': 3, 'start_ms': 1000, 'end_ms': 9000,
                 'repositories': [
                     {'name': 'alpha', 'repository': 'org/alpha',
                      'snapshot': 'repos/alpha.json', 'status': 'success'},
                     {'name': 'beta', 'repository': 'org/beta',
                      'snapshot': 'repos/beta.json', 'status': 'success'}]}
        (root / 'web/data/repositories.json').write_text(
            json.dumps(index), 'utf-8')
        (root / 'web/data/repos/alpha.json').write_text(
            json.dumps(alpha), 'utf-8')
        (root / 'web/data/repos/beta.json').write_text(
            json.dumps(beta), 'utf-8')
        shutil.copy(ROOT / 'web/core.js', root / 'web/core.js')
        shutil.copy(ROOT / 'web/app.js', root / 'web/app.js')
        return root

    def run_tool(self, root):
        output = root / 'report.json'
        with redirect_stdout(io.StringIO()):
            code = vud.main(['--root', str(root), '--output', str(output)])
        return code, json.loads(output.read_text('utf-8'))

    def tamper(self, root, name, old, new):
        path = root / 'web' / name
        text = path.read_text('utf-8')
        self.assertIn(old, text)
        path.write_text(text.replace(old, new), 'utf-8')

    def test_clean_tree_exit_zero(self):
        root = self.build_tree()
        code, report = self.run_tool(root)
        self.assertEqual(code, 0)
        self.assertEqual(report['overall'], {'status': 'verified',
                                             'problems': []})
        self.assertEqual(report['node_cross_check']['status'], 'ok')
        self.assertEqual(report['baseline']['status'], 'not_applicable')
        groups = report['detail_groups']
        self.assertEqual(groups['per_repo']['alpha'],
                         {'prs': 2, 'groups': 4,
                          'prs_with_unmatched_group': 2,
                          'unmatched_batches': 3,
                          'empty_event_id_batches': 2,
                          'coverage_all_batches_ok': True})
        self.assertTrue(groups['node_equal'])
        self.assertTrue(all(v['coverage_all_batches_ok']
                            for v in groups['per_repo'].values()))
        fw = report['failed_wait']
        self.assertEqual(fw['per_repo']['alpha'],
                         {'prs_with_failed_wait': 2, 'cancelled_batches': 1,
                          'later_success_prs': 1})
        self.assertEqual(fw['top8'], [['alpha', 101, 12],
                                      ['alpha', 102, 21]])
        self.assertTrue(fw['node_equal'])
        self.assertTrue(fw['sequence_node_equal'])
        self.assertEqual(report['exceptions']['top8'],
                         [['beta', 201], ['alpha', 101], ['alpha', 102]])
        self.assertTrue(report['exceptions']['sequence_node_equal'])
        self.assertEqual(report['cross_max_e2e']['value']['repo'], 'beta')
        self.assertEqual(report['cross_max_e2e']['value']['pr'], 201)
        self.assertEqual(report['drill_targets']['quality_per_repo']
                         ['alpha'], {'targets': [102], 'targets_exist': True})
        self.assertEqual(report['minute_exact']['mismatches'], {})

    def test_tampered_failed_wait_filter_exit_one(self):
        root = self.build_tree()
        self.tamper(root, 'core.js', "filter(b=>b.status==='failure'&&",
                    "filter(b=>b.status==='success'&&")
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertIn('core.js:failedWait_filter',
                      report['source_contracts']['missing'])
        self.assertFalse(report['failed_wait']['node_equal'])
        self.assertFalse(report['failed_wait']['sequence_node_equal'])

    def test_tampered_rep_expand_exit_one(self):
        root = self.build_tree()
        self.tamper(root, 'app.js',
                    'bs.map(b=>batchHTML(b,b.url===s.representative_batch_url))',
                    'bs.map(b=>batchHTML(b,b.url!==s.representative_batch_url))')
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertIn('app.js:rep_expand_flag',
                      report['source_contracts']['missing'])

    def test_tampered_route_context_cleanup_exit_one(self):
        root = self.build_tree()
        self.tamper(root, 'app.js',
                    'detailPR=null;detailRepo=null;detailSnapshot=null;}',
                    'detailPR=null;detailSnapshot=null;}')
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertIn('app.js:route_context_cleanup', report['source_contracts']['missing'])

    def test_tampered_minute_threshold_exit_one(self):
        root = self.build_tree()
        self.tamper(root, 'app.js', "ms<600?'<0.01'", "ms<700?'<0.01'")
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertIn('app.js:minute_fn',
                      report['source_contracts']['missing'])
        self.assertTrue(report['minute_exact']['mismatches'])


class CommittedEvidenceTests(unittest.TestCase):
    """提交证据（ubs-detail-evidence.json）：冻结输入保持结论。"""

    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(EVIDENCE_PATH.read_text('utf-8'))

    def test_frozen_overall_and_cross_checks(self):
        self.assertTrue(self.report['input']['matches_audit_frozen_input'])
        self.assertEqual(self.report['input']['manifest_state'], 'verified')
        self.assertEqual(self.report['overall'], {'status': 'verified',
                                                  'problems': []})
        self.assertEqual(self.report['node_cross_check']['status'], 'ok')
        self.assertEqual(len(self.report['node_cross_check']['compared']), 7)
        contracts = self.report['source_contracts']
        self.assertEqual(contracts['checked'], 40)
        self.assertEqual(contracts['missing'], [])
        me = self.report['minute_exact']
        self.assertEqual(me['samples_checked'], 24)
        self.assertEqual(me['mismatches'], {})
        self.assertTrue(all(v['coverage_all_batches_ok'] for v in
                            self.report['detail_groups']['per_repo']
                            .values()))
        self.assertTrue(self.report['detail_groups']['node_equal'])
        self.assertTrue(all(v['targets_exist'] for v in
                            self.report['drill_targets']
                            ['quality_per_repo'].values()))

    def test_frozen_per_repo_counts(self):
        groups = self.report['detail_groups']['per_repo']
        self.assertEqual(groups['ubs-engine'],
                         {'prs': 68, 'groups': 258,
                          'prs_with_unmatched_group': 3,
                          'unmatched_batches': 4,
                          'empty_event_id_batches': 4,
                          'coverage_all_batches_ok': True})
        self.assertEqual(groups['ubturbo'],
                         {'prs': 27, 'groups': 96,
                          'prs_with_unmatched_group': 2,
                          'unmatched_batches': 2,
                          'empty_event_id_batches': 2,
                          'coverage_all_batches_ok': True})
        self.assertEqual(sum(v['unmatched_batches']
                             for v in groups.values()), 6)
        fw = self.report['failed_wait']
        self.assertEqual(fw['per_repo'],
                         {'ubs-engine': {'prs_with_failed_wait': 39,
                                         'cancelled_batches': 2,
                                         'later_success_prs': 31},
                          'ubs-comm': {'prs_with_failed_wait': 20,
                                       'cancelled_batches': 1,
                                       'later_success_prs': 12},
                          'ubs-virt': {'prs_with_failed_wait': 23,
                                       'cancelled_batches': 1,
                                       'later_success_prs': 19},
                          'ubs-io': {'prs_with_failed_wait': 4,
                                     'cancelled_batches': 0,
                                     'later_success_prs': 2},
                          'ubs-mem': {'prs_with_failed_wait': 9,
                                      'cancelled_batches': 0,
                                      'later_success_prs': 7},
                          'OmniStateStore': {'prs_with_failed_wait': 12,
                                             'cancelled_batches': 1,
                                             'later_success_prs': 8},
                          'ham': {'prs_with_failed_wait': 1,
                                  'cancelled_batches': 0,
                                  'later_success_prs': 0},
                          'ubturbo': {'prs_with_failed_wait': 15,
                                      'cancelled_batches': 3,
                                      'later_success_prs': 13},
                          'ubs-atomic': {'prs_with_failed_wait': 4,
                                         'cancelled_batches': 0,
                                         'later_success_prs': 3}})
        self.assertEqual(fw['cross_total'], 127)
        self.assertEqual(fw['cancelled_total'], 8)
        self.assertEqual(fw['later_success_total'], 95)
        self.assertTrue(fw['node_equal'])
        self.assertTrue(fw['sequence_node_equal'])
        self.assertEqual(self.report['exceptions']['total_valid'], 203)
        self.assertTrue(self.report['exceptions']['sequence_node_equal'])
        rep = self.report['representative_expand']['per_repo']
        self.assertEqual([rep[k]['prs_with_representative'] for k in rep],
                         [68, 28, 29, 6, 12, 20, 1, 27, 12])
        self.assertEqual(self.report['drill_targets']['quality_per_repo']
                         ['ubs-engine']['targets'],
                         [1573, 1583, 1591, 1596, 1599, 1612, 1618, 1633,
                          1645])

    def test_frozen_top8_and_baseline(self):
        self.assertEqual(self.report['failed_wait']['top8'],
                         [['ubs-engine', 1600, 7469],
                          ['ubs-engine', 1601, 7470],
                          ['OmniStateStore', 137, 277],
                          ['OmniStateStore', 139, 281],
                          ['OmniStateStore', 138, 282],
                          ['ubs-comm', 1095, 4291],
                          ['OmniStateStore', 134, 272],
                          ['ubs-engine', 1602, 7475]])
        self.assertEqual(self.report['exceptions']['top8'],
                         [['ubturbo', 442], ['ubs-engine', 1600],
                          ['ubs-engine', 1601], ['OmniStateStore', 137],
                          ['OmniStateStore', 139], ['OmniStateStore', 136],
                          ['OmniStateStore', 138], ['OmniStateStore', 135]])
        cross = self.report['cross_max_e2e']
        self.assertEqual([cross['value']['repo'], cross['value']['pr'],
                          cross['value']['e2e_ms']],
                         ['ubturbo', 442, 50640069])
        self.assertTrue(cross['node_equal'])
        ex = self.report['minute_exact']['examples']
        self.assertEqual(ex['599'], {'minute': '<0.01', 'exact': '599 ms'})
        self.assertEqual(ex['600'], {'minute': '0.01', 'exact': '600 ms'})
        self.assertEqual(ex['1000'], {'minute': '0.02',
                                      'exact': '1.000 s'})
        self.assertEqual(ex['11064101'], {'minute': '184.40',
                                          'exact': '11,064.101 s'})
        self.assertEqual(ex['50640069'], {'minute': '844.00',
                                          'exact': '50,640.069 s'})
        baseline = self.report['baseline']
        self.assertEqual(baseline['status'], 'matched')
        checks = baseline['checks']
        for name, check in checks.items():
            self.assertTrue(check['passed'], name)
        u24 = checks['U24_detail_keeps_all_batches']
        self.assertEqual([u24['pr'], u24['batches'], u24['groups']],
                         [1600, 5, 5])
        self.assertEqual(checks['U25_representative_expanded']
                         ['rep_trigger'], 7469)
        self.assertEqual(checks['U30_quality_drill']
                         ['engine_quality_targets'],
                         [1573, 1583, 1591, 1596, 1599, 1612, 1618, 1633,
                          1645])
        self.assertEqual(checks['U32_cross_max_drill']['top'][0],
                         ['ubturbo', 442])
        self.assertEqual(checks['U33_failed_wait_drill']['top'][0],
                         ['ubs-engine', 1600, 7469])


if __name__ == '__main__':
    unittest.main()
