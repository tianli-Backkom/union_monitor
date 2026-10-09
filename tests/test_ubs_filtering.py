"""REQ-042 · UBS筛选保持PR集合及代表批次 — 测试。

锁定 scripts/verify_ubs_filtering.py 的独立谓词语义：
- 触发请求按事件身份（id）去重，后写覆盖；计数 create/push/retest/other、
  无关联事件与未知来源批次（AC02）
- 组合筛选：状态、编号/标题/作者/SHA 搜索（大小写不敏感、首尾空格剥离）、
  完整性（complete = 有批次且全部可测量且无问题；incomplete = 无批次 /
  有问题 / 存在不可测量批次）、push/retest 触发（AC01/AC02）
- 无结果查询返回空集、默认参数返回完整集合（重置语义）（AC04）
- 合成目录树：干净树退出码 0（含去重碰撞、孤儿批次、零批次 PR）；篡改
  web/core.js 的查询 trim 或触发去重语义退出码 1（非循环锁定）
- 提交证据（ubs-filtering-evidence.json）：冻结输入 9 仓 522 组合零失配、
  跨仓一致、孤儿可追踪、U12/U19 基线回放 matched
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

import verify_ubs_filtering as vf  # noqa: E402
import verify_ubs_semantics as vsm  # noqa: E402

EVIDENCE_PATH = ROOT / 'audit' / '2026-10-09' / 'evidence' / 'ubs-filtering-evidence.json'


def make_child(number, kind, *, result='SUCCESS', queue_ms=200, duration_ms=800,
               association_valid=True, building=False, repo='alpha'):
    url = f'https://ci.example/{kind}/{repo}/{number}/'
    return {'url': url, 'kind': kind, 'association_valid': association_valid,
            'building': building, 'result': result, 'queue_ms': queue_ms,
            'duration_ms': duration_ms, 'total_ms': queue_ms + duration_ms,
            'start_ms': 1500, 'end_ms': 1500 + duration_ms}


def make_batch(number, *, request_ms=1000, scheduled_ms=1100, complete=True,
               children=(), trigger_result='SUCCESS', trigger_building=False,
               trigger_end=5000, event_id=None, sha=None, repo='alpha'):
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
    return {'url': url, 'number': number, 'request_ms': request_ms,
            'scheduled_ms': scheduled_ms, 'complete': complete, 'trigger': trigger,
            'children': children, 'end_ms': end, 'e2e_ms': e2e,
            'jenkins_ms': (end - scheduled_ms if end is not None
                           and end >= scheduled_ms else None),
            'status': status,
            'cancelled': any(job['result'] in ('ABORTED', 'NOT_BUILT')
                             for job in jobs),
            'eligible': status in ('success', 'failure') and e2e is not None,
            'event_id': event_id, 'sha': sha}


def make_pr(number, *, state='open', title='', author='', batches=(), events=(),
            issues=(), created_ms=2000):
    pr = {'number': number, 'state': state, 'title': title, 'author': author,
          'created_ms': created_ms, 'batches': list(batches),
          'events': list(events), 'issues': list(issues)}
    pr['metrics'] = vsm.representative(pr)[0]
    return pr


class IndependentPredicateTests(unittest.TestCase):
    """独立谓词纯函数语义（AC01/AC02）。"""

    @staticmethod
    def pr(number, state='open', title='', author='', batches=(), events=(),
           issues=()):
        return {'number': number, 'state': state, 'title': title, 'author': author,
                'batches': list(batches), 'events': list(events),
                'issues': list(issues)}

    def test_trigger_counts_event_identity_dedup(self):
        pr = {'events': [{'id': 'e1', 'kind': 'push'}, {'id': 'e1', 'kind': 'retest'},
                         {'id': 'e2', 'kind': 'push'}],
              'batches': [{'event_id': 'e1'}, {'event_id': 'GHOST'},
                          {'event_id': None}]}
        counts = vf.own_trigger_counts(pr)
        self.assertEqual(counts['push'], 1)      # e1 后写覆盖为 retest，仅 e2 计 push
        self.assertEqual(counts['retest'], 1)
        self.assertEqual(counts['create'], 0)
        self.assertEqual(counts['unlinked'], 1)  # e2 无批次引用
        self.assertEqual(counts['unknownBatches'], 2)  # GHOST 与空 event_id

    def test_trigger_counts_kinds(self):
        pr = {'events': [{'id': 'a', 'kind': 'create'}, {'id': 'b', 'kind': 'push'},
                         {'id': 'c', 'kind': 'retest'}, {'id': 'd', 'kind': 'comment'}],
              'batches': [{'event_id': 'a'}, {'event_id': 'b'}, {'event_id': 'c'},
                          {'event_id': 'd'}]}
        counts = vf.own_trigger_counts(pr)
        self.assertEqual((counts['create'], counts['push'], counts['retest'],
                          counts['other']), (1, 1, 1, 1))
        self.assertEqual((counts['unlinked'], counts['unknownBatches']), (0, 0))

    def test_filter_state_and_query_dimensions(self):
        prs = [
            self.pr(1, title='修复内存泄漏', author='XuKe--',
                    batches=[{'sha': 'aabbccdd', 'eligible': True}]),
            self.pr(2, state='merged', title='update docs', author='dev-two',
                    batches=[{'sha': '11223344', 'eligible': True},
                             {'sha': None, 'eligible': False}]),
            self.pr(3, state='closed', author='XuKe--'),
        ]
        self.assertEqual([p['number'] for p in vf.own_filter(prs, state='open')], [1])
        self.assertEqual([p['number'] for p in vf.own_filter(prs, state='merged')], [2])
        self.assertEqual([p['number'] for p in vf.own_filter(prs, query='XuKe--')], [1, 3])
        self.assertEqual([p['number'] for p in vf.own_filter(prs, query='2')], [2])
        self.assertEqual([p['number'] for p in vf.own_filter(prs, query='DOCS')], [2])
        self.assertEqual([p['number'] for p in vf.own_filter(prs, query='aabbccd')], [1])
        self.assertEqual([p['number'] for p in vf.own_filter(prs, query='11223344')], [2])

    def test_filter_query_case_and_trim_normalization(self):
        prs = [
            self.pr(1, author='XuKe--', batches=[{'sha': 'a1', 'eligible': True}]),
            self.pr(2, state='merged', author='dev-two'),
        ]
        expected = [p['number'] for p in vf.own_filter(prs, query='xuke--')]
        self.assertEqual(expected, [1])
        self.assertEqual([p['number'] for p in vf.own_filter(prs, query='XUKE--')], expected)
        self.assertEqual([p['number'] for p in vf.own_filter(prs, query='  XuKe--  ')],
                         expected)

    def test_filter_quality_rules(self):
        prs = [
            self.pr(1, batches=[{'sha': 'x', 'eligible': True}]),
            self.pr(2, batches=[{'sha': 'y', 'eligible': True},
                                {'sha': 'z', 'eligible': False}]),
            self.pr(3),
            self.pr(4, batches=[{'sha': 'w', 'eligible': True}], issues=['数据缺口']),
        ]
        self.assertEqual([p['number'] for p in vf.own_filter(prs, quality='complete')],
                         [1])
        self.assertEqual([p['number'] for p in vf.own_filter(prs, quality='incomplete')],
                         [2, 3, 4])

    def test_filter_trigger_dedup_and_combined(self):
        prs = [
            self.pr(1, events=[{'id': 'a', 'kind': 'create'}]),
            self.pr(2, state='merged',
                    events=[{'id': 'b', 'kind': 'push'}, {'id': 'c', 'kind': 'retest'}]),
            self.pr(3, events=[{'id': 'd', 'kind': 'push'},
                               {'id': 'd', 'kind': 'retest'}]),
        ]
        self.assertEqual([p['number'] for p in vf.own_filter(prs, trigger='retest')],
                         [2, 3])
        self.assertEqual([p['number'] for p in vf.own_filter(prs, trigger='push')], [2])
        self.assertEqual([p['number'] for p in vf.own_filter(prs, trigger='create')], [1])
        self.assertEqual([p['number'] for p in vf.own_filter(prs, state='merged',
                                                             trigger='retest')], [2])

    def test_filter_no_result_and_default(self):
        prs = [self.pr(1), self.pr(2, state='merged')]
        self.assertEqual(vf.own_filter(prs, query='__NO_RESULTS__'), [])
        self.assertEqual([p['number'] for p in vf.own_filter(prs)], [1, 2])


class SyntheticTreeTests(unittest.TestCase):
    """合成目录树：干净树通过；篡改查询 trim / 触发去重退出码 1。"""

    def build_tree(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / 'web/data/repos').mkdir(parents=True)
        prs = [
            make_pr(101, title='修复内存泄漏', author='XuKe--',
                    batches=[make_batch(12, event_id='e1', sha='aabbccdd',
                                        children=[make_child(12, 'x86')])],
                    events=[{'id': 'e1', 'kind': 'create'}]),
            make_pr(102, state='merged', title='sync upstream', author='dev-two',
                    batches=[make_batch(12, event_id='e2', sha='sha02012',
                                        children=[make_child(12, 'x86')]),
                             make_batch(99, trigger_end=6000, event_id='e3',
                                        sha='sha02099',
                                        children=[make_child(99, 'arm')])],
                    events=[{'id': 'e2', 'kind': 'push'},
                            {'id': 'e3', 'kind': 'retest'}]),
            make_pr(103, state='closed', author='dev-three',
                    batches=[make_batch(13, event_id='e4', sha='sha03013',
                                        children=[make_child(13, 'x86',
                                                             building=True)])],
                    events=[{'id': 'e4', 'kind': 'create'}]),
            make_pr(104, author='dev-four',
                    batches=[make_batch(14, event_id='e5', sha='sha04014',
                                        children=[make_child(14, 'x86')])],
                    events=[{'id': 'e5', 'kind': 'create'}], issues=['数据缺口']),
            make_pr(105, state='merged', author='dev-five'),
            make_pr(106, author='dev-six',
                    batches=[make_batch(16, event_id='e6', sha='ff001122',
                                        children=[make_child(16, 'x86')])],
                    events=[{'id': 'e6', 'kind': 'push'},
                            {'id': 'e6', 'kind': 'retest'}]),
            make_pr(107, author='dev-seven',
                    batches=[make_batch(17, event_id='GHOST', sha='sha07017',
                                        children=[make_child(17, 'dt')])],
                    events=[{'id': 'e7', 'kind': 'retest'}]),
        ]
        beta = [make_pr(201, author='beta-dev')]
        alpha = {'meta': {'repository': 'org/alpha', 'start_ms': 1000,
                          'end_ms': 9000}, 'prs': prs}
        beta_snap = {'meta': {'repository': 'org/beta', 'start_ms': 1000,
                              'end_ms': 9000}, 'prs': beta}
        index = {'schema_version': 3, 'start_ms': 1000, 'end_ms': 9000,
                 'repositories': [
                     {'name': 'alpha', 'repository': 'org/alpha',
                      'snapshot': 'repos/alpha.json', 'status': 'success'},
                     {'name': 'beta', 'repository': 'org/beta',
                      'snapshot': 'repos/beta.json', 'status': 'success'}]}
        (root / 'web/data/repositories.json').write_text(json.dumps(index), 'utf-8')
        (root / 'web/data/repos/alpha.json').write_text(json.dumps(alpha), 'utf-8')
        (root / 'web/data/repos/beta.json').write_text(json.dumps(beta_snap), 'utf-8')
        shutil.copy(ROOT / 'web/core.js', root / 'web/core.js')
        return root

    def run_tool(self, root):
        output = root / 'report.json'
        with redirect_stdout(io.StringIO()):
            code = vf.main(['--root', str(root), '--output', str(output)])
        return code, json.loads(output.read_text('utf-8'))

    def tamper_core_js(self, root, old, new):
        core = root / 'web/core.js'
        text = core.read_text('utf-8')
        self.assertIn(old, text)
        core.write_text(text.replace(old, new), 'utf-8')

    def test_clean_tree_exit_zero(self):
        root = self.build_tree()
        code, report = self.run_tool(root)
        self.assertEqual(code, 0)
        self.assertEqual(report['overall']['status'], 'verified')
        self.assertEqual(report['input']['repos_checked'], 2)
        self.assertEqual(report['combos']['total_compared'], 114)
        self.assertEqual(report['combos']['per_repo'], {'alpha': 58, 'beta': 56})
        self.assertEqual(report['identity']['combo_mismatch_count'], 0)
        self.assertEqual(report['trigger_dedup']['mismatch_count'], 0)
        self.assertEqual(report['representative_invariance']['fact_mismatch_count'], 0)
        self.assertEqual(report['representative_invariance']['stored_mismatch_count'], 0)
        self.assertTrue(all(v['agree'] for v
                            in report['identity']['query_normalization'].values()))
        self.assertEqual(report['trigger_dedup']['audit_predicate']['divergence_count'], 1)
        self.assertEqual(report['overall']['status'], 'verified')
        self.assertEqual(report['orphan_tracking'],
                         {'unknown_batches_prs': 1, 'unknown_batches_total': 1,
                          'unlinked_event_prs': 1, 'unlinked_events_total': 1,
                          'all_in_default_set': True})
        self.assertTrue(all(v['match'] for v in report['cross_repo'].values()))
        self.assertEqual(report['cross_repo']['open']['python'], 5)
        self.assertEqual(report['cross_repo']['merged']['python'], 2)
        self.assertEqual(report['cross_repo']['closed']['python'], 1)
        self.assertTrue(report['no_result_and_reset']['no_result_empty'])
        self.assertTrue(report['no_result_and_reset']['default_full'])
        self.assertEqual(report['representative_invariance']['null_e2e_prs'], 3)
        self.assertEqual(report['audit_baseline_comparison']['status'],
                         'not_applicable_input_drifted')

    def test_tampered_query_trim_exit_one(self):
        root = self.build_tree()
        self.tamper_core_js(root, 'query.toLowerCase().trim()', 'query.toLowerCase()')
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertGreater(report['identity']['combo_mismatch_count'], 0)
        self.assertFalse(report['identity']['query_normalization']['alpha']['agree'])

    def test_tampered_trigger_dedup_exit_one(self):
        root = self.build_tree()
        self.tamper_core_js(root, 'triggerCounts(p)[trigger]>0',
                            'p.events.some(e=>e.kind===trigger)')
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertGreater(report['identity']['combo_mismatch_count'], 0)
        self.assertEqual(report['trigger_dedup']['mismatch_count'], 0)


class CommittedEvidenceTests(unittest.TestCase):
    """提交证据（ubs-filtering-evidence.json）：冻结输入保持结论。"""

    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(EVIDENCE_PATH.read_text('utf-8'))

    def test_frozen_combo_matrix_zero_mismatch(self):
        self.assertEqual(self.report['input']['repos_checked'], 9)
        self.assertEqual(self.report['combos']['total_compared'], 522)
        self.assertEqual(set(self.report['combos']['per_repo'].values()), {58})
        self.assertEqual(self.report['identity']['combo_mismatch_count'], 0)
        self.assertEqual(self.report['trigger_dedup']['mismatch_count'], 0)
        self.assertEqual(self.report['representative_invariance']['fact_mismatch_count'], 0)
        self.assertEqual(self.report['representative_invariance']['stored_mismatch_count'], 0)
        self.assertTrue(all(v['agree'] for v
                            in self.report['identity']['query_normalization'].values()))

    def test_frozen_baseline_u12_u19(self):
        baseline = self.report['audit_baseline_comparison']
        self.assertEqual(baseline['status'], 'matched')
        by_combo = {json.dumps(e['combo'], ensure_ascii=False, sort_keys=True): e
                    for e in baseline['u12_replay']}
        expected = {'{"state": "open"}': 11,
                    '{"state": "merged", "trigger": "retest"}': 20,
                    '{"quality": "incomplete"}': 9,
                    '{"quality": "complete", "trigger": "push"}': 38,
                    '{"q": "1655"}': 1, '{"q": "xuke--"}': 1,
                    '{"q": "4cf1f74e"}': 1, '{"q": "__NO_RESULTS__"}': 0}
        self.assertEqual(set(by_combo), set(expected))
        for key, value in expected.items():
            self.assertEqual(by_combo[key]['computed'], value, key)
            self.assertEqual(by_combo[key]['baseline'], value, key)
            self.assertTrue(by_combo[key]['match'], key)
        u19 = baseline['u19']
        self.assertEqual(u19['first_pr'], 1600)
        self.assertEqual(u19['representative_url']['computed'],
                         'https://ci.openeuler.openatom.cn/job/multiarch/job/openeuler'
                         '/job/trigger/job/ubs-engine/7469/')
        self.assertTrue(u19['representative_url']['match'])
        for key, value in (('x86_queue_ms', 4125), ('x86_duration_ms', 127),
                           ('x86_total_ms', 4252)):
            self.assertEqual(u19[key]['computed'], value, key)
            self.assertEqual(u19[key]['baseline'], value, key)
            self.assertTrue(u19[key]['match'], key)
        self.assertTrue(u19['queue_plus_duration_equals_total'])

    def test_frozen_cross_repo_and_orphan(self):
        cross = self.report['cross_repo']
        for state, pooled in (('', 203), ('open', 38), ('merged', 139), ('closed', 26)):
            self.assertEqual(cross[state]['python'], pooled, state)
            self.assertEqual(cross[state]['node'], pooled, state)
            self.assertTrue(cross[state]['match'], state)
        self.assertEqual(self.report['orphan_tracking'],
                         {'unknown_batches_prs': 5, 'unknown_batches_total': 6,
                          'unlinked_event_prs': 10, 'unlinked_events_total': 12,
                          'all_in_default_set': True})

    def test_frozen_no_result_default_and_nulls(self):
        reset = self.report['no_result_and_reset']
        self.assertTrue(reset['no_result_empty'])
        self.assertTrue(reset['default_full'])
        invariance = self.report['representative_invariance']
        self.assertEqual(invariance['prs'], 203)
        self.assertEqual(invariance['prs_with_rep'], 203)
        self.assertEqual(invariance['null_e2e_prs'], 0)
        self.assertTrue(invariance['nulls_preserved'])

    def test_frozen_predicate_and_overall(self):
        self.assertEqual(self.report['trigger_dedup']['prs_compared'], 203)
        self.assertEqual(self.report['trigger_dedup']['audit_predicate']['compared'], 609)
        self.assertEqual(self.report['trigger_dedup']['audit_predicate']['divergence_count'], 0)
        self.assertTrue(self.report['input']['matches_audit_frozen_input'])
        self.assertEqual(self.report['input']['manifest_state'], 'verified')
        self.assertEqual(self.report['overall'], {'status': 'verified', 'problems': []})


if __name__ == '__main__':
    unittest.main()
