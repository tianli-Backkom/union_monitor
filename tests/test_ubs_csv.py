"""REQ-044 · UBS四类CSV内容与格式保持正确 — 测试。

锁定 scripts/verify_ubs_csv.py 的独立重算语义：
- 文本序列化：BOM/CRLF/公式前缀转义（=+-@ 制表 回车）/引号倍增/空值 ""/
  布尔 true/false/整值浮点不带 .0（U38/A11 口径）
- 日期：空值 '—'、sv-SE 上海时区完整时间
- PR 导出：完整筛选集不受 15 行分页限制（U21）、24 列布局与毫秒单位（U22）、
  状态筛选行数与代表值字段（U21/U23）
- 批次导出：全部批次 × 全部子任务、无子任务占位一行（U26）、代表标志行数、
  issues join 与名称映射
- 质量导出：PR/批次问题、运行中批次与采集错误组合（U29）
- 仓库汇总：纳入/过期/待采集状态文案、覆盖率、P90 降序默认序（U31）
- 合成目录树：干净树退出码 0；篡改 core.js 公式转义或 app.js 表头退出码 1
- 提交证据（ubs-csv-evidence.json）：冻结输入 21 行集 + nasty 逐字节一致、
  基线 U21/U23/U26/U29/U31/U38/A11 matched
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

import verify_ubs_csv as vuc  # noqa: E402

EVIDENCE_PATH = ROOT / 'audit' / '2026-10-09' / 'evidence' / 'ubs-csv-evidence.json'


def make_child(number, kind, *, result='SUCCESS', queue_ms=200, duration_ms=800,
               building=False, repo='alpha'):
    url = f'https://ci.example/{kind}/{repo}/{number}/'
    return {'url': url, 'kind': kind, 'association_valid': True,
            'building': building, 'result': result, 'queue_ms': queue_ms,
            'duration_ms': duration_ms, 'total_ms': queue_ms + duration_ms,
            'start_ms': 1500, 'end_ms': 1500 + duration_ms}


def make_batch(number, *, trigger_end=5000, children=(), repo='alpha',
               event_type='create', issues=None):
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
            'event_id': None, 'sha': None, 'event_type': event_type,
            'issues': issues}


def make_pr(number, created_ms, batches, *, state='merged', title=None,
            author='dev', merged_ms=None, submission_count=1, issues=None):
    return {'number': number, 'created_ms': created_ms,
            'batches': list(batches), 'state': state,
            'title': title or f'PR #{number}', 'author': author,
            'merged_ms': merged_ms, 'submission_count': submission_count,
            'issues': issues, 'events': []}


class CsvEncodingTests(unittest.TestCase):
    """文本序列化语义（U38/A11 口径）。"""

    def test_nasty_roundtrip_and_formula_escape(self):
        parsed = vuc.own_parse(vuc.own_csv(vuc.NASTY_MATRIX))
        expected = []
        for row in vuc.NASTY_MATRIX:
            out = []
            for v in row:
                if v is None:
                    out.append('')
                elif v is True:
                    out.append('true')
                elif v is False:
                    out.append('false')
                elif isinstance(v, str):
                    out.append("'" + v
                               if v[:1] in ('=', '+', '-', '@', '\t', '\r')
                               else v)
                else:
                    out.append(str(v))
            expected.append(out)
        self.assertEqual(parsed, expected)

    def test_null_bool_and_integral_float_cells(self):
        text = vuc.own_csv([[None, True, False, 232188.0, 1.0,
                             2710318.4, 0]])
        self.assertEqual(text, '\ufeff"","true","false","232188","1",'
                               '"2710318.4","0"')

    def test_bom_crlf_quote_doubling(self):
        self.assertEqual(vuc.own_csv([['a"b'], ['c']]),
                         '\ufeff"a""b"\r\n"c"')


class DateTests(unittest.TestCase):
    """sv-SE 上海时区完整时间与空值占位。"""

    def test_empty_values_em_dash(self):
        self.assertEqual(vuc.own_date(None), '—')
        self.assertEqual(vuc.own_date(0), '—')

    def test_shanghai_format(self):
        self.assertEqual(vuc.own_date(1789479077000), '2026-09-15 21:31:17')
        self.assertEqual(vuc.own_date(1759971042000), '2025-10-09 08:50:42')
        self.assertEqual(vuc.own_date(500), '1970-01-01 08:00:00')


class PrCsvTests(unittest.TestCase):
    """PR 导出行构造（U21/U22/U23 口径）。"""

    @staticmethod
    def snap(prs):
        return {'meta': {'repository': 'org/alpha'}, 'prs': prs}

    @staticmethod
    def many_prs():
        return [make_pr(300 + i, 1000 + i * 100,
                        [make_batch(40 + i, children=[
                            make_child(40 + i, 'x86')])])
                for i in range(18)]

    def test_full_filter_set_not_paged(self):
        rows = vuc.own_pr_csv_rows(self.snap(self.many_prs()))
        self.assertEqual(len(rows), 18)  # 超过 15 行分页仍导出完整筛选集
        self.assertTrue(all(r[0] == 'org/alpha' for r in rows))

    def test_row_layout_and_units(self):
        rows = vuc.own_pr_csv_rows(self.snap([make_pr(
            301, 500, [make_batch(31, trigger_end=6000, children=[
                make_child(31, 'x86')])], merged_ms=2000)]))
        self.assertEqual(len(vuc.PR_HEADS), 24)
        self.assertEqual(vuc.PR_HEADS[14], 'E2E ms')
        self.assertEqual(vuc.PR_HEADS[15:18],
                         ['x86排队ms', 'x86执行ms', 'x86总计ms'])
        row = rows[0]
        self.assertEqual(row[:8],
                         ['org/alpha', 301, 'PR #301', '已合入', 'dev',
                          '1970-01-01 08:00:00', '1970-01-01 08:00:02', 1])
        self.assertEqual(row[8:15],
                         [1, 0, 0, 0, 31,
                          'https://ci.example/trigger/alpha/31/', 5000])
        self.assertEqual(row[15:18], [200, 800, 1000])

    def test_state_filter_rows(self):
        prs = [
            make_pr(301, 500, [make_batch(31, trigger_end=6000, children=[
                make_child(31, 'x86')])]),
            make_pr(302, 3000, [make_batch(32, children=[
                make_child(32, 'x86')])]),
            make_pr(303, 1000, [make_batch(33, trigger_end=4000, children=[
                make_child(33, 'x86')])]),
            make_pr(304, 2000, [make_batch(34, children=[
                make_child(34, 'x86')])], state='open'),
        ]
        rows = vuc.own_pr_csv_rows(self.snap(prs), state='merged')
        self.assertEqual([r[1] for r in rows], [301, 302, 303])


class BatchCsvTests(unittest.TestCase):
    """批次导出行构造（U26 口径）。"""

    @classmethod
    def setUpClass(cls):
        cls.snap = {'meta': {'repository': 'org/alpha'}}
        cls.pr = make_pr(101, 500, [
            make_batch(11, trigger_end=6000, children=[
                make_child(11, 'x86'), make_child(11, 'dt')]),
            make_batch(12, children=[]),
            make_batch(13, children=[make_child(13, 'x86')],
                       issues=['问题A', '问题B'], event_type='retest'),
            make_batch(14, children=[make_child(14, 'x86')],
                       event_type='weird'),
        ])
        cls.rows = vuc.own_batch_csv_rows(cls.snap, cls.pr)

    def test_expansion_and_placeholder(self):
        self.assertEqual(len(self.rows), 5)  # 2 + 占位 1 + 1 + 1
        placeholder = next(r for r in self.rows
                           if r[2] == 'https://ci.example/trigger/alpha/12/')
        self.assertIsNone(placeholder[11])   # 无子任务批次占位一行
        self.assertIsNone(placeholder[12])
        self.assertEqual([r[2] for r in self.rows].count(
            'https://ci.example/trigger/alpha/11/'), 2)

    def test_representative_flag_rows(self):
        flagged = [r for r in self.rows if r[10] is True]
        self.assertEqual(len(flagged), 2)   # 代表批次 #11（e2e 5000）全部行
        self.assertTrue(all(r[2] == 'https://ci.example/trigger/alpha/11/'
                            for r in flagged))
        self.assertFalse(any(r[10] for r in self.rows
                             if r[2] != 'https://ci.example/trigger/alpha/11/'))

    def test_issues_join_and_name_maps(self):
        b13 = next(r for r in self.rows
                   if r[2] == 'https://ci.example/trigger/alpha/13/')
        self.assertEqual(b13[16], '问题A; 问题B')
        self.assertEqual(b13[4], '重跑请求')
        self.assertEqual(b13[3], '成功')
        b14 = next(r for r in self.rows
                   if r[2] == 'https://ci.example/trigger/alpha/14/')
        self.assertEqual(b14[4], 'weird')    # 未知事件类型回退原值
        b12 = next(r for r in self.rows
                   if r[2] == 'https://ci.example/trigger/alpha/12/')
        self.assertEqual(b12[3], '数据不完整')
        self.assertIs(b12[10], False)


class QualityRowsTests(unittest.TestCase):
    """质量导出组合（U29 口径）。"""

    def test_composition_order(self):
        prs = [
            make_pr(101, 500, [make_batch(11, children=[
                make_child(11, 'x86')])], issues=['PR 级问题']),
            make_pr(102, 600, [
                make_batch(12, children=[make_child(12, 'x86')],
                           issues=['批次级问题']),
                make_batch(13, children=[
                    make_child(13, 'x86', building=True)]),
            ]),
        ]
        meta = {'errors': [{'source': 'jenkins', 'reason': '采集超时'}]}
        rows = vuc.own_quality_rows(prs, meta)
        self.assertEqual(rows, [
            [101, 'PR', 'PR 级问题'],
            [102, '#12', '批次级问题'],
            [102, '#13', '仍在执行：排除主要耗时统计'],
            ['采集', 'jenkins', '采集超时'],
        ])


class RepoCsvTests(unittest.TestCase):
    """仓库汇总行（U31 口径）。"""

    @classmethod
    def setUpClass(cls):
        cls.index = {'start_ms': 1000, 'end_ms': 9000, 'repositories': [
            {'name': 'alpha', 'repository': 'org/alpha',
             'snapshot': 'repos/alpha.json', 'status': 'success'},
            {'name': 'beta', 'repository': 'org/beta',
             'snapshot': 'repos/beta.json', 'status': 'success'},
            {'name': 'gamma', 'repository': 'org/gamma',
             'snapshot': None, 'status': 'pending'},
        ]}
        alpha = {'meta': {'repository': 'org/alpha', 'start_ms': 1000,
                          'end_ms': 9000,
                          'collected_at': '2026-10-09T06:00:00+08:00'}, 'prs': [
            make_pr(101, 500, [make_batch(11, trigger_end=6000, children=[
                make_child(11, 'x86')])]),
            make_pr(102, 1000, [make_batch(12, children=[
                make_child(12, 'x86')])]),
        ]}
        beta = {'meta': {'repository': 'org/beta', 'start_ms': 100,
                         'end_ms': 900}, 'prs': []}
        cls.snapshots = {'alpha': alpha, 'beta': beta}
        cls.rows, cls.names = vuc.own_repo_csv_rows(cls.index, cls.snapshots)

    def test_included_and_excluded_rows(self):
        by_name = dict(zip(self.names, self.rows))
        alpha = by_name['alpha']
        self.assertEqual(alpha[0], 'org/alpha')
        self.assertEqual(alpha[1], '采集完成')
        self.assertTrue(alpha[2])
        self.assertEqual(alpha[3], '2026-10-09T06:00:00+08:00')
        self.assertEqual(alpha[4:8], [2, 0, 2, 0])
        self.assertEqual(alpha[8], 2)
        self.assertEqual(alpha[9], 1.0)      # 覆盖率 2/2
        self.assertEqual(alpha[10], 4500.0)  # (5000 + 4000) / 2
        self.assertEqual(alpha[11], 4900.0)  # P90 线性插值
        beta = by_name['beta']
        self.assertEqual(beta[1], '过期快照 · 不计跨仓汇总')
        self.assertFalse(beta[2])
        self.assertIsNone(beta[4])
        self.assertEqual(beta[5:8], [None, None, None])
        self.assertIsNone(beta[10])
        gamma = by_name['gamma']
        self.assertEqual(gamma[1], '未获取数据 · 待采集')
        self.assertIsNone(gamma[3])

    def test_default_p90_order(self):
        self.assertEqual(self.names, ['alpha', 'beta', 'gamma'])


class SyntheticTreeTests(unittest.TestCase):
    """合成目录树：干净树通过；篡改公式转义或 PR 表头退出码 1。"""

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
        ]}
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
            code = vuc.main(['--root', str(root), '--output', str(output)])
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
        self.assertTrue(report['csv_encoding']['nasty_matrix_bytes_equal'])
        self.assertTrue(all(report['csv_encoding']
                            ['real_row_sets_bytes_equal'].values()))
        self.assertEqual(report['date_format']['mismatches'], {})
        self.assertTrue(report['repo_csv']['values_equal_to_repository_rows'])
        self.assertEqual(report['repo_csv']['rows'], 2)
        self.assertEqual(report['baseline']['status'], 'not_applicable')

    def test_tampered_formula_escape_exit_one(self):
        root = self.build_tree()
        self.tamper(root, 'core.js', '/^[=+\\-@\\t\\r]/.test(s)',
                    '/^[=+]/.test(s)')
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertFalse(report['csv_encoding']['nasty_matrix_bytes_equal'])
        self.assertIn('core.js:csv_formula_escape',
                      report['source_contracts']['missing'])

    def test_tampered_pr_heads_exit_one(self):
        root = self.build_tree()
        self.tamper(root, 'app.js', "'代表trigger编号'", "'代表批次编号'")
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertIn('app.js:pr_heads',
                      report['source_contracts']['missing'])


class CommittedEvidenceTests(unittest.TestCase):
    """提交证据（ubs-csv-evidence.json）：冻结输入保持结论。"""

    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(EVIDENCE_PATH.read_text('utf-8'))

    def test_frozen_overall_and_encoding(self):
        self.assertTrue(self.report['input']['matches_audit_frozen_input'])
        self.assertEqual(self.report['overall'], {'status': 'verified',
                                                  'problems': []})
        enc = self.report['csv_encoding']
        self.assertTrue(enc['nasty_matrix_bytes_equal'])
        self.assertEqual(len(enc['real_row_sets_bytes_equal']), 21)
        self.assertTrue(all(enc['real_row_sets_bytes_equal'].values()))
        self.assertTrue(enc['bom_and_crlf'])
        self.assertTrue(enc['roundtrip_formula_prefix_kept'])
        compared = self.report['node_cross_check']['row_sets_compared']
        self.assertEqual(len(compared), 22)
        self.assertIn('nasty', compared)
        self.assertIn('quality_ham', compared)
        self.assertEqual(self.report['date_format']['samples_checked'], 13)
        self.assertEqual(self.report['date_format']['mismatches'], {})

    def test_frozen_pr_and_repo_csv(self):
        pr = self.report['pr_csv']
        self.assertEqual(pr['per_repo_default_rows'],
                         {'ubs-engine': 68, 'ubs-comm': 28, 'ubs-virt': 29,
                          'ubs-io': 6, 'ubs-mem': 12, 'OmniStateStore': 20,
                          'ham': 1, 'ubturbo': 27, 'ubs-atomic': 12})
        self.assertTrue(all(pr['per_repo_repository_column_ok'].values()))
        self.assertEqual(pr['engine_merged_rows'], 50)
        self.assertEqual(pr['engine_merged_first_row'],
                         ['openeuler/ubs-engine', 1599, 4288049])
        self.assertTrue(pr['engine_sequences_equal'])
        repo = self.report['repo_csv']
        self.assertEqual(repo['rows'], 9)
        self.assertEqual(repo['default_order_names'],
                         ['OmniStateStore', 'ubturbo', 'ubs-engine', 'ubs-comm',
                          'ubs-mem', 'ubs-virt', 'ubs-io', 'ubs-atomic', 'ham'])
        self.assertTrue(repo['values_equal_to_repository_rows'])
        self.assertEqual(repo['diffs'], {})

    def test_frozen_batch_and_quality_csv(self):
        batch = self.report['batch_csv']
        self.assertEqual(batch['per_repo_rows'],
                         {'ubs-engine': 1275, 'ubs-comm': 551, 'ubs-virt': 1078,
                          'ubs-io': 60, 'ubs-mem': 190, 'OmniStateStore': 253,
                          'ham': 35, 'ubturbo': 450, 'ubs-atomic': 112})
        self.assertEqual(batch['per_repo_representative_rows'],
                         {'ubs-engine': 336, 'ubs-comm': 140, 'ubs-virt': 143,
                          'ubs-io': 30, 'ubs-mem': 60, 'OmniStateStore': 79,
                          'ham': 5, 'ubturbo': 126, 'ubs-atomic': 48})
        self.assertEqual(batch['representative_rows_expected'],
                         batch['per_repo_representative_rows'])
        self.assertEqual(set(batch['eligible_field_mismatches'].values()), {0})
        self.assertEqual(self.report['quality_csv']['per_repo_default_counts'],
                         {'ubs-engine': 17, 'ubs-comm': 5, 'ubs-virt': 5,
                          'ubs-io': 0, 'ubs-mem': 1, 'OmniStateStore': 10,
                          'ham': 0, 'ubturbo': 6, 'ubs-atomic': 1})

    def test_frozen_baseline_checks(self):
        baseline = self.report['baseline']
        self.assertEqual(baseline['status'], 'matched')
        checks = baseline['checks']
        for name, check in checks.items():
            self.assertTrue(check['passed'], name)
        u26 = checks['U26_detail_batch_task_rows']
        self.assertEqual(u26['pr'], 1600)
        self.assertEqual(u26['batches'], 5)
        self.assertEqual(u26['rows'], 23)
        self.assertEqual(u26['representative_rows'], 3)
        u23 = checks['U23_first_row_representative_fields']
        self.assertEqual([u23['repository'], u23['pr'], u23['e2e_ms']],
                         ['openeuler/ubs-engine', 1599, 4288049])
        self.assertEqual(checks['U21_pr_export_full_merged_set']['rows'], 50)
        self.assertEqual(checks['U29_quality_export_records']['rows'], 17)
        self.assertEqual(checks['U31_repository_csv_repos']['rows'], 9)
        self.assertEqual(checks['U38_text_roundtrip']['value'],
                         "'=中文,\"带换行\n标题")
        self.assertEqual(checks['A11_pages_blob_filename']['filename'],
                         'ubs-engine-pr-summary.csv')
        contracts = self.report['source_contracts']
        self.assertEqual(contracts['checked'], 33)
        self.assertEqual(contracts['missing'], [])


if __name__ == '__main__':
    unittest.main()
