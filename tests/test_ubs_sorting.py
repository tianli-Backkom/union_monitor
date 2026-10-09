"""REQ-043 · UBS排序与分页边界保持正确 — 测试。

锁定 scripts/verify_ubs_sorting.py 的独立重算语义：
- 分页模型：15 条/页，0/1/15/16/30/31 边界页码与上一/下一页禁用状态（A08 口径）、
  0 条时 1/1 且无记录；页码越界约束到合法页；全部页切片恰好划分序列（AC02/AC03）
- PR 排序：代表 E2E 降序（并列按创建时间从新到旧、空值最后）、批次数降序
  （并列同上）、创建时间降序（并列保持原序）（AC01）
- 仓库排序：P90 降序（空→-1）、PR 数降序、名称不区分大小写升序（AC01）
- 合成目录树：干净树退出码 0；篡改 web/core.js E2E 并列规则或 web/app.js
  PAGE_SIZE 退出码 1（非循环锁定）
- 提交证据（ubs-sorting-evidence.json）：冻结输入 9 仓 27 序列零失配、
  仓库三种排序与 P90 独立值一致、源码契约齐全、U14–U18/A08/A14 基线 matched
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

import verify_ubs_sorting as vso  # noqa: E402

EVIDENCE_PATH = ROOT / 'audit' / '2026-10-09' / 'evidence' / 'ubs-sorting-evidence.json'


def make_child(number, kind, *, result='SUCCESS', queue_ms=200, duration_ms=800,
               building=False, repo='alpha'):
    url = f'https://ci.example/{kind}/{repo}/{number}/'
    return {'url': url, 'kind': kind, 'association_valid': True,
            'building': building, 'result': result, 'queue_ms': queue_ms,
            'duration_ms': duration_ms, 'total_ms': queue_ms + duration_ms,
            'start_ms': 1500, 'end_ms': 1500 + duration_ms}


def make_batch(number, *, trigger_end=5000, children=(), repo='alpha'):
    url = f'https://ci.example/trigger/{repo}/{number}/'
    trigger = {'url': url, 'result': 'SUCCESS', 'building': False,
               'start_ms': 1200, 'end_ms': trigger_end,
               'duration_ms': trigger_end - 1200, 'queue_ms': 50,
               'total_ms': 50 + (trigger_end - 1200), 'scheduled_ms': 1100}
    children = list(children)
    jobs = [trigger] + children
    ends = [job['end_ms'] for job in jobs]
    end = max(ends)
    e2e = end - 1000
    status = ('running' if any(job['building'] for job in jobs)
              else 'failure' if any(job['result'] != 'SUCCESS' for job in jobs)
              else 'success' if children else 'incomplete')
    return {'url': url, 'number': number, 'request_ms': 1000,
            'scheduled_ms': 1100, 'complete': True, 'trigger': trigger,
            'children': children, 'end_ms': end, 'e2e_ms': e2e,
            'jenkins_ms': end - 1100, 'status': status, 'cancelled': False,
            'eligible': status in ('success', 'failure') and e2e is not None,
            'event_id': None, 'sha': None}


def make_pr(number, created_ms, batches):
    return {'number': number, 'created_ms': created_ms, 'batches': list(batches)}


class PagingModelTests(unittest.TestCase):
    """独立分页模型（AC02/AC03，A08 边界口径）。"""

    def test_paging_boundaries(self):
        expected = {0: (1, '1 / 1', True, True, 0), 1: (1, '1 / 1', True, True, 1),
                    15: (1, '1 / 1', True, True, 15),
                    16: (2, '1 / 2', True, False, 15),
                    30: (2, '1 / 2', True, False, 15),
                    31: (3, '1 / 3', True, False, 15)}
        for total, (pages, page_info, prev_disabled, next_disabled,
                    rows) in expected.items():
            info = vso.own_paging(total)
            self.assertEqual(info['pages'], pages, total)
            self.assertEqual(info['page_info'], page_info, total)
            self.assertEqual(info['prev_disabled'], prev_disabled, total)
            self.assertEqual(info['next_disabled'], next_disabled, total)
            self.assertEqual(info['rows_on_page'], rows, total)

    def test_paging_clamp_and_last_page(self):
        self.assertEqual(vso.own_paging(68, page=99)['page'], 5)
        self.assertEqual(vso.own_paging(0, page=7)['page'], 1)
        info = vso.own_paging(68, page=5)
        self.assertEqual(info['page_info'], '5 / 5')
        self.assertFalse(info['prev_disabled'])
        self.assertTrue(info['next_disabled'])
        self.assertEqual(info['rows_on_page'], 8)

    def test_paging_rows_per_page(self):
        self.assertEqual(vso.own_paging(37, page=1)['rows_on_page'], 15)
        self.assertEqual(vso.own_paging(37, page=2)['rows_on_page'], 15)
        self.assertEqual(vso.own_paging(37, page=3)['rows_on_page'], 7)

    def test_paging_partitions_cover_all_sizes(self):
        for total in list(range(46)) + [68, 75, 76]:
            self.assertTrue(vso.paging_partitions(total), total)


class SortPredicateTests(unittest.TestCase):
    """独立排序谓词（AC01）。"""

    @staticmethod
    def prs():
        return [
            make_pr(101, 500, [make_batch(11, trigger_end=6000, children=[
                make_child(11, 'x86')])]),                # e2e 5000
            make_pr(102, 3000, [make_batch(12, children=[
                make_child(12, 'x86')])]),                # e2e 4000
            make_pr(103, 1000, [make_batch(13, children=[
                make_child(13, 'x86')])]),                # e2e 4000
            make_pr(104, 9000, [make_batch(14, children=[
                make_child(14, 'x86', building=True)])]),  # 运行中 → 空
            make_pr(105, 2000, [make_batch(15, children=[
                make_child(15, 'x86')]),
                make_batch(16, children=[make_child(16, 'x86')])]),  # e2e 4000
        ]

    def test_sort_e2e_tie_breaks_by_created_and_null_last(self):
        order = [p['number'] for p in vso.own_sort_prs(self.prs(), 'e2e')]
        self.assertEqual(order, [101, 102, 105, 103, 104])

    def test_sort_batches_tie_breaks_by_created(self):
        order = [p['number'] for p in vso.own_sort_prs(self.prs(), 'batches')]
        self.assertEqual(order, [105, 104, 102, 103, 101])

    def test_sort_created_desc_and_stable_ties(self):
        prs = [make_pr(201, 2500, [make_batch(21)]),
               make_pr(202, 2500, [make_batch(22)]),
               make_pr(203, 4000, [make_batch(23)])]
        order = [p['number'] for p in vso.own_sort_prs(prs, 'created')]
        self.assertEqual(order, [203, 201, 202])

    def test_repo_orders(self):
        rows = [{'name': 'ubs-virt', 'p90': 900.0, 'prs': 3},
                {'name': 'ham', 'p90': None, 'prs': 0},
                {'name': 'ubs-engine', 'p90': 2500.0, 'prs': 5},
                {'name': 'OmniStateStore', 'p90': 1200.0, 'prs': 1}]
        orders = vso.own_repo_orders(rows)
        self.assertEqual(orders['p90'], ['ubs-engine', 'OmniStateStore',
                                         'ubs-virt', 'ham'])
        self.assertEqual(orders['prs'], ['ubs-engine', 'ubs-virt',
                                         'OmniStateStore', 'ham'])
        self.assertEqual(orders['name'], ['ham', 'OmniStateStore',
                                          'ubs-engine', 'ubs-virt'])


class SyntheticTreeTests(unittest.TestCase):
    """合成目录树：干净树通过；篡改排序并列规则或 PAGE_SIZE 退出码 1。"""

    def build_tree(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / 'web/data/repos').mkdir(parents=True)
        alpha = {'meta': {'repository': 'org/alpha', 'start_ms': 1000,
                          'end_ms': 9000}, 'prs': [
            make_pr(101, 500, [make_batch(11, trigger_end=6000, children=[
                make_child(11, 'x86')])]),
            make_pr(102, 3000, [make_batch(12, children=[
                make_child(12, 'x86')])]),
            make_pr(103, 1000, [make_batch(13, children=[
                make_child(13, 'x86')])]),
            make_pr(104, 9000, [make_batch(14, children=[
                make_child(14, 'x86', building=True)])]),
            make_pr(105, 2000, [make_batch(15, children=[
                make_child(15, 'x86')]),
                make_batch(16, children=[make_child(16, 'x86')])])]}
        beta = {'meta': {'repository': 'org/beta', 'start_ms': 1000,
                         'end_ms': 9000},
                'prs': [make_pr(201, 100, [make_batch(21, repo='beta', children=[
                    make_child(21, 'x86', repo='beta')])])]}
        index = {'schema_version': 3, 'start_ms': 1000, 'end_ms': 9000,
                 'repositories': [
                     {'name': 'alpha', 'repository': 'org/alpha',
                      'snapshot': 'repos/alpha.json', 'status': 'success'},
                     {'name': 'beta', 'repository': 'org/beta',
                      'snapshot': 'repos/beta.json', 'status': 'success'}]}
        (root / 'web/data/repositories.json').write_text(json.dumps(index), 'utf-8')
        (root / 'web/data/repos/alpha.json').write_text(json.dumps(alpha), 'utf-8')
        (root / 'web/data/repos/beta.json').write_text(json.dumps(beta), 'utf-8')
        shutil.copy(ROOT / 'web/core.js', root / 'web/core.js')
        shutil.copy(ROOT / 'web/app.js', root / 'web/app.js')
        return root

    def run_tool(self, root):
        output = root / 'report.json'
        with redirect_stdout(io.StringIO()):
            code = vso.main(['--root', str(root), '--output', str(output)])
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
        self.assertEqual(report['overall']['status'], 'verified')
        self.assertEqual(report['pr_sorting']['sequences_compared'], 6)
        self.assertEqual(report['pr_sorting']['mismatch_count'], 0)
        self.assertEqual(report['pr_sorting']['per_repo']['alpha']['e2e'],
                         [101, 102, 105, 103, 104])
        self.assertEqual(report['pr_sorting']['per_repo']['alpha']['batches'],
                         [105, 104, 102, 103, 101])
        self.assertEqual(report['pr_sorting']['per_repo']['alpha']['created'],
                         [104, 102, 105, 103, 101])
        self.assertTrue(report['repo_sorting']['p90_order']['match'])
        self.assertEqual(report['repo_sorting']['prs_order']['python'],
                         ['alpha', 'beta'])
        self.assertTrue(report['source_contracts']['all_found'])
        self.assertTrue(report['pagination_model']['coverage_verified'])
        self.assertTrue(report['pagination_model']['clamp_verified'])
        self.assertEqual(report['audit_baseline_comparison']['status'],
                         'not_applicable_input_drifted')

    def test_tampered_sort_tiebreak_exit_one(self):
        root = self.build_tree()
        self.tamper(root, 'core.js',
                    '(value(a).e2e_ms??-1)||(b.created_ms||0)-(a.created_ms||0)',
                    '(value(a).e2e_ms??-1)')
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertGreater(report['pr_sorting']['mismatch_count'], 0)

    def test_tampered_page_size_exit_one(self):
        root = self.build_tree()
        self.tamper(root, 'app.js', 'const PAGE_SIZE=15', 'const PAGE_SIZE=10')
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertFalse(report['source_contracts']['all_found'])
        missing = [c['name'] for c in report['source_contracts']['contracts']
                   if not c['found']]
        self.assertIn('page_size_15', missing)


class CommittedEvidenceTests(unittest.TestCase):
    """提交证据（ubs-sorting-evidence.json）：冻结输入保持结论。"""

    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(EVIDENCE_PATH.read_text('utf-8'))

    def test_frozen_pr_sorting_sequences(self):
        self.assertEqual(self.report['pr_sorting']['sequences_compared'], 27)
        self.assertEqual(self.report['pr_sorting']['mismatch_count'], 0)
        per_repo = self.report['pr_sorting']['per_repo']
        counts = {name: len(seq['e2e']) for name, seq in per_repo.items()}
        self.assertEqual(counts, {'ubs-engine': 68, 'ubs-comm': 28,
                                  'ubs-virt': 29, 'ubs-io': 6, 'ubs-mem': 12,
                                  'OmniStateStore': 20, 'ham': 1,
                                  'ubturbo': 27, 'ubs-atomic': 12})
        engine = per_repo['ubs-engine']['e2e']
        self.assertEqual(engine[:15], [1600, 1601, 1599, 1602, 1564, 1559,
                                       1603, 1570, 1573, 1596, 1620, 1617,
                                       1604, 1579, 1612])
        self.assertEqual(engine[60:], [1580, 1639, 1655, 1618, 1633, 1619,
                                       1651, 1632])

    def test_frozen_repo_sorting_orders(self):
        repo_sorting = self.report['repo_sorting']
        self.assertEqual(repo_sorting['p90_order']['python'],
                         ['OmniStateStore', 'ubturbo', 'ubs-engine', 'ubs-comm',
                          'ubs-mem', 'ubs-virt', 'ubs-io', 'ubs-atomic', 'ham'])
        self.assertEqual(repo_sorting['prs_order']['python'],
                         ['ubs-engine', 'ubs-virt', 'ubs-comm', 'ubturbo',
                          'OmniStateStore', 'ubs-mem', 'ubs-atomic', 'ubs-io',
                          'ham'])
        self.assertEqual(repo_sorting['name_order']['python'],
                         ['ham', 'OmniStateStore', 'ubs-atomic', 'ubs-comm',
                          'ubs-engine', 'ubs-io', 'ubs-mem', 'ubs-virt',
                          'ubturbo'])
        for key in ('p90', 'prs', 'name'):
            self.assertTrue(repo_sorting[f'{key}_order']['match'], key)
        self.assertTrue(all(v['match'] for v
                            in repo_sorting['p90_values'].values()))
        self.assertEqual(round(repo_sorting['p90_values']['OmniStateStore']['python']),
                         8511499)
        self.assertEqual(round(repo_sorting['p90_values']['ham']['python']), 232188)

    def test_frozen_pagination_and_contracts(self):
        model = self.report['pagination_model']
        self.assertEqual(model['page_size'], 15)
        expected_pages = {'0': '1 / 1', '1': '1 / 1', '15': '1 / 1',
                          '16': '1 / 2', '30': '1 / 2', '31': '1 / 3'}
        self.assertEqual({k: v['page_info'] for k, v
                          in model['boundaries'].items()}, expected_pages)
        self.assertTrue(model['coverage_verified'])
        self.assertTrue(model['clamp_verified'])
        contracts = self.report['source_contracts']
        self.assertTrue(contracts['all_found'])
        names = {c['name'] for c in contracts['contracts']}
        self.assertIn('page_size_15', names)
        self.assertIn('page_clamp', names)
        self.assertIn('repo_sort_p90', names)
        self.assertEqual(len(contracts['contracts']), 17)

    def test_frozen_baseline_replay(self):
        baseline = self.report['audit_baseline_comparison']
        self.assertEqual(baseline['status'], 'matched')
        for order in ('created', 'batches', 'e2e'):
            self.assertTrue(baseline['u18'][order]['match'], order)
        self.assertTrue(baseline['u15']['match'])
        u16 = baseline['u16']
        self.assertTrue(u16['match'])
        self.assertEqual(u16['pages'], {'computed': 5, 'baseline': 5})
        self.assertEqual(u16['page_info'],
                         {'computed': '5 / 5', 'baseline': '5 / 5'})
        self.assertTrue(u16['next_disabled']['computed'])
        self.assertEqual(u16['last_page_rows']['computed'],
                         [1580, 1639, 1655, 1618, 1633, 1619, 1651, 1632])
        self.assertTrue(baseline['u14']['match'])
        self.assertEqual(baseline['u17']['computed'], '1 / 1')
        self.assertEqual(set(baseline['a08']), {'0', '1', '15', '16', '30', '31'})
        self.assertTrue(all(v['match'] for v in baseline['a08'].values()))
        self.assertTrue(baseline['a14']['match'])

    def test_frozen_overall_status(self):
        self.assertTrue(self.report['input']['matches_audit_frozen_input'])
        self.assertEqual(self.report['input']['manifest_state'], 'verified')
        self.assertEqual(self.report['input']['repos_checked'], 9)
        self.assertEqual(self.report['overall'], {'status': 'verified',
                                                  'problems': []})


if __name__ == '__main__':
    unittest.main()
