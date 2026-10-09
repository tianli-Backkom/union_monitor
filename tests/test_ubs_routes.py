"""REQ-047 · UBS全部视图与旧链接可达性保持 — 测试。

锁定 scripts/verify_ubs_routes.py 的独立镜像语义：
- parseHash：三域解析、repo/quality 子视图、空段过滤、额外段忽略、
  安全解码（坏百分号/截断序列回退原文）（U 口径）
- resolve：LEGACY 旧链接规范化（#repositories→#ubs、#overview/#prs→
  ubs-engine 单仓、#quality→ubs-engine 质量、#method）、#repo/NAME 与
  method 别名、未知路由默认回总览（U10 口径）
- toHash：默认回退、quality 后缀、encodeURIComponent 编码语义
- 视图枚举：每仓单仓+质量两页 + 跨仓总览/Triton/口径（2N+3）
- keepPRPage：仅仓库视图跨仓切换时重置分页
- 合成目录树：干净树退出码 0；篡改 router.js LEGACY 表/quality 分支或
  app.js 未知仓库提示退出码 1（U01/U11 口径）
- 提交证据（ubs-routes-evidence.json）：冻结输入保持结论与基线回放
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

import verify_ubs_routes as vur  # noqa: E402

EVIDENCE_PATH = (ROOT / 'audit' / '2026-10-09' / 'evidence'
                 / 'ubs-routes-evidence.json')


class ParseHashTests(unittest.TestCase):
    """parseHash 镜像语义。"""

    def test_domains_and_views(self):
        self.assertEqual(vur.own_parse_hash('#ubs'), {'domain': 'ubs'})
        self.assertEqual(vur.own_parse_hash('#ubs/repo/x'),
                         {'domain': 'ubs', 'repo': 'x'})
        self.assertEqual(vur.own_parse_hash('#ubs/repo/x/quality'),
                         {'domain': 'ubs', 'repo': 'x', 'sub': 'quality'})
        self.assertEqual(vur.own_parse_hash('#triton'),
                         {'domain': 'triton'})
        self.assertEqual(vur.own_parse_hash('#method'),
                         {'domain': 'method'})
        self.assertIsNone(vur.own_parse_hash('#xyz'))
        self.assertIsNone(vur.own_parse_hash(''))
        self.assertIsNone(vur.own_parse_hash('#'))
        self.assertIsNone(vur.own_parse_hash(None))

    def test_edge_parts(self):
        self.assertEqual(vur.own_parse_hash('#ubs/repo'),
                         {'domain': 'ubs'})       # 无仓名回跨仓
        self.assertEqual(vur.own_parse_hash('#ubs/repo/x/extra'),
                         {'domain': 'ubs', 'repo': 'x'})  # 额外段忽略
        self.assertEqual(vur.own_parse_hash('#ubs/repo/x/QUALITY'),
                         {'domain': 'ubs', 'repo': 'x'})  # 大小写敏感
        self.assertEqual(vur.own_parse_hash('#ubs//repo//x'),
                         {'domain': 'ubs', 'repo': 'x'})  # 空段过滤
        self.assertEqual(vur.own_parse_hash('#ubs/repo/'),
                         {'domain': 'ubs'})
        self.assertEqual(vur.own_parse_hash('#ubs/x'),
                         {'domain': 'ubs'})

    def test_decode_safety(self):
        self.assertEqual(vur.own_parse_hash('#ubs/repo/%E4%B8%AD%E6%96%87'),
                         {'domain': 'ubs', 'repo': '中文'})
        self.assertEqual(vur.own_parse_hash('#ubs/repo/%zz'),
                         {'domain': 'ubs', 'repo': '%zz'})  # 坏百分号回退
        self.assertEqual(vur.own_parse_hash('#ubs/repo/%E4%B8'),
                         {'domain': 'ubs', 'repo': '%E4%B8'})  # 截断回退
        self.assertIsNone(vur.own_parse_hash('##ubs'))  # 仅去一个 #


class ResolveTests(unittest.TestCase):
    """resolve 镜像：LEGACY 表与别名（U10/AC02 口径）。"""

    def test_legacy_aliases(self):
        self.assertEqual(vur.own_resolve('#repositories'), '#ubs')
        self.assertEqual(vur.own_resolve('#overview'),
                         '#ubs/repo/ubs-engine')
        self.assertEqual(vur.own_resolve('#prs'), '#ubs/repo/ubs-engine')
        self.assertEqual(vur.own_resolve('#quality'),
                         '#ubs/repo/ubs-engine/quality')
        self.assertEqual(vur.own_resolve('#method'), '#method')
        for head, target in vur.LEGACY.items():
            self.assertEqual(vur.own_resolve('#' + head), target)

    def test_repo_alias_and_unknown(self):
        self.assertEqual(vur.own_resolve('#repo/ubs-engine'),
                         '#ubs/repo/ubs-engine')
        self.assertEqual(vur.own_resolve('#repo/x/quality'),
                         '#ubs/repo/x/quality')
        self.assertEqual(vur.own_resolve('#repo/x/method'), '#method')
        self.assertEqual(vur.own_resolve('#repo/x/extra'),
                         '#ubs/repo/x')
        self.assertEqual(vur.own_resolve('#repo'), '#ubs')
        self.assertEqual(vur.own_resolve('#repo/%E4%B8%AD%E6%96%87'),
                         '#ubs/repo/%E4%B8%AD%E6%96%87')
        for unknown in ('', None, '#xyz', '#UBS', '#ubs/repo', '#ubs/unknown',
                        '#%E4%B8%AD%E6%96%87', '##ubs', '#/'):
            self.assertEqual(vur.own_resolve(unknown), '#ubs',
                             msg=repr(unknown))
        # 未知仓库保留哈希：路由可达，视图层显示未找到仓库
        self.assertEqual(vur.own_resolve('#ubs/repo/unknown-repo'),
                         '#ubs/repo/unknown-repo')


class ToHashTests(unittest.TestCase):
    """toHash 镜像：默认回退与编码。"""

    def test_routes_and_defaults(self):
        self.assertEqual(vur.own_to_hash(None), '#ubs')
        self.assertEqual(vur.own_to_hash({}), '#ubs')
        self.assertEqual(vur.own_to_hash({'domain': 'ubs'}), '#ubs')
        self.assertEqual(vur.own_to_hash({'domain': 'ubs', 'sub': 'quality'}),
                         '#ubs')
        self.assertEqual(vur.own_to_hash({'domain': 'ubs', 'repo': 'x'}),
                         '#ubs/repo/x')
        self.assertEqual(vur.own_to_hash(
            {'domain': 'ubs', 'repo': 'x', 'sub': 'quality'}),
            '#ubs/repo/x/quality')
        self.assertEqual(vur.own_to_hash(
            {'domain': 'ubs', 'repo': 'x', 'sub': 'xyz'}), '#ubs/repo/x')
        self.assertEqual(vur.own_to_hash({'domain': 'triton'}), '#triton')
        self.assertEqual(vur.own_to_hash({'domain': 'method'}), '#method')
        self.assertEqual(vur.own_to_hash({'domain': 'other'}), '#ubs')

    def test_encoding(self):
        self.assertEqual(vur.own_to_hash({'domain': 'ubs', 'repo': '中文'}),
                         '#ubs/repo/%E4%B8%AD%E6%96%87')
        self.assertEqual(vur.own_to_hash({'domain': 'ubs', 'repo': 'a b'}),
                         '#ubs/repo/a%20b')
        self.assertEqual(vur.own_to_hash({'domain': 'ubs', 'repo': 'a*b'}),
                         '#ubs/repo/a*b')  # JS encodeURIComponent 不转义 *
        self.assertEqual(
            vur.own_to_hash({'domain': 'ubs', 'repo': 'OmniStateStore'}),
            '#ubs/repo/OmniStateStore')


class ViewNameTests(unittest.TestCase):
    """视图名与导航高亮目标派生。"""

    def test_view_name_and_nav(self):
        self.assertEqual(vur.own_view_name({'domain': 'ubs', 'repo': 'x'}),
                         'ubs-repo')
        self.assertEqual(vur.own_view_name(
            {'domain': 'ubs', 'repo': 'x', 'sub': 'quality'}),
            'ubs-quality')
        self.assertEqual(vur.own_view_name({'domain': 'ubs'}), 'ubs')
        self.assertEqual(vur.own_view_name({'domain': 'triton'}), 'triton')
        self.assertEqual(vur.own_view_name({'domain': 'method'}), 'method')
        self.assertEqual(vur.own_nav_target({'domain': 'ubs'}),
                         'ubs-overview')
        self.assertEqual(vur.own_nav_target(
            {'domain': 'ubs', 'repo': 'x'}), 'ubs-repo')
        self.assertEqual(vur.own_nav_target({'domain': 'triton'}), 'triton')


class KeepPRPageTests(unittest.TestCase):
    """keepPRPage 镜像：仓库视图跨仓切换才重置分页。"""

    def test_keep_pr_page(self):
        self.assertTrue(vur.own_keep_pr_page('a', 'ubs-repo', 'a'))
        self.assertFalse(vur.own_keep_pr_page('a', 'ubs-repo', 'b'))
        self.assertTrue(vur.own_keep_pr_page('a', 'ubs-quality', 'a'))
        self.assertFalse(vur.own_keep_pr_page('a', 'ubs-quality', 'b'))
        self.assertTrue(vur.own_keep_pr_page('a', 'ubs', 'b'))
        self.assertTrue(vur.own_keep_pr_page('a', 'triton', 'b'))
        self.assertFalse(vur.own_keep_pr_page(None, 'ubs-repo', 'x'))


class ViewsEnumerationTests(unittest.TestCase):
    """视图枚举：2N+3 与归属核验。"""

    def test_views_from_synthetic_index(self):
        index = {'repositories': [
            {'name': 'alpha', 'repository': 'org/alpha'},
            {'name': 'beta', 'repository': 'org/beta'}]}
        snapshots = {
            'alpha': {'meta': {'repository': 'org/alpha'},
                      'prs': [{'number': 1}, {'number': 2}]},
            'beta': {'meta': {'repository': 'org/Wrong'}, 'prs': []}}
        views = vur.own_views(index, snapshots)
        self.assertEqual(len(views), 7)  # 2 仓 × 2 页 + 3 全局
        alpha_repo = next(v for v in views
                          if v['repo'] == 'alpha' and v['kind'] == 'repo')
        self.assertEqual(alpha_repo['hash'], '#ubs/repo/alpha')
        self.assertEqual(alpha_repo['view_name'], 'ubs-repo')
        self.assertEqual(alpha_repo['nav_target'], 'ubs-repo')
        self.assertTrue(alpha_repo['roundtrip_ok'])
        self.assertTrue(alpha_repo['canonical_ok'])
        self.assertTrue(alpha_repo['snapshot_attribution_ok'])
        self.assertEqual(alpha_repo['prs'], 2)
        alpha_quality = next(v for v in views
                             if v['repo'] == 'alpha'
                             and v['kind'] == 'quality')
        self.assertEqual(alpha_quality['hash'],
                         '#ubs/repo/alpha/quality')
        beta_repo = next(v for v in views
                         if v['repo'] == 'beta' and v['kind'] == 'repo')
        self.assertFalse(beta_repo['snapshot_attribution_ok'])  # 归属不符
        globals_ = [v for v in views if v['repo'] is None]
        self.assertEqual([v['hash'] for v in globals_],
                         ['#ubs', '#triton', '#method'])
        self.assertEqual([v['nav_target'] for v in globals_],
                         ['ubs-overview', 'triton', 'method'])


class SyntheticTreeTests(unittest.TestCase):
    """合成目录树：干净树通过；篡改路由/提示退出码 1。"""

    def build_tree(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / 'web/data/repos').mkdir(parents=True)
        alpha = {'meta': {'repository': 'org/alpha', 'start_ms': 1000,
                          'end_ms': 9000},
                 'prs': [{'number': 101, 'created_ms': 500,
                          'state': 'merged', 'batches': [], 'events': []}]}
        beta = {'meta': {'repository': 'org/beta', 'start_ms': 1000,
                         'end_ms': 9000}, 'prs': []}
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
        shutil.copy(ROOT / 'web/router.js', root / 'web/router.js')
        shutil.copy(ROOT / 'web/app.js', root / 'web/app.js')
        return root

    def run_tool(self, root):
        output = root / 'report.json'
        with redirect_stdout(io.StringIO()):
            code = vur.main(['--root', str(root), '--output', str(output)])
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
        self.assertEqual(report['views']['total'], 7)
        self.assertEqual(report['views']['expected_total'], 7)
        self.assertEqual(report['baseline']['status'], 'not_applicable')
        self.assertEqual(report['node_cross_check']['status'], 'ok')
        matrix = report['router_matrix']
        for key in ('resolve_mismatches', 'parse_mismatches',
                    'to_hash_mismatches', 'keep_pr_page_mismatches'):
            self.assertEqual(matrix[key], {}, key)
        self.assertEqual(report['views']['per_repo']['alpha']['repo']
                         ['prs'], 1)
        self.assertTrue(all(
            v[k] for v in report['views']['per_repo'].values()
            for v in v.values()
            for k in ('roundtrip_ok', 'canonical_ok',
                      'snapshot_attribution_ok')))

    def test_tampered_legacy_map_exit_one(self):
        root = self.build_tree()
        self.tamper(root, 'router.js', "repositories:'#ubs'",
                    "repositories:'#triton'")
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertIn('router.js:legacy_map',
                      report['source_contracts']['missing'])
        self.assertTrue(report['router_matrix']['resolve_mismatches'])

    def test_tampered_quality_branch_exit_one(self):
        root = self.build_tree()
        self.tamper(root, 'router.js', "parts[3]==='quality'",
                    "parts[3]==='q'")
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertIn('router.js:parse_repo_quality',
                      report['source_contracts']['missing'])
        self.assertTrue(report['router_matrix']['parse_mismatches'])

    def test_tampered_unknown_repo_notice_exit_one(self):
        root = self.build_tree()
        self.tamper(root, 'app.js', ":'未找到仓库'):''",
                    ":'未知仓库'):''")
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertIn('app.js:unknown_repo_notice',
                      report['source_contracts']['missing'])


class CommittedEvidenceTests(unittest.TestCase):
    """提交证据（ubs-routes-evidence.json）：冻结输入保持结论。"""

    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(EVIDENCE_PATH.read_text('utf-8'))

    def test_frozen_overall(self):
        self.assertTrue(self.report['input']['matches_audit_frozen_input'])
        self.assertEqual(self.report['overall'], {'status': 'verified',
                                                  'problems': []})
        self.assertEqual(self.report['node_cross_check']['status'], 'ok')
        self.assertEqual(self.report['node_cross_check']['compared'],
                         ['resolve', 'parseHash', 'toHash', 'keepPRPage'])
        self.assertEqual(self.report['views']['total'], 21)
        self.assertEqual(self.report['views']['expected_total'], 21)
        self.assertEqual(self.report['views']['repos'], 9)
        matrix = self.report['router_matrix']
        self.assertEqual((matrix['hash_cases'], matrix['to_hash_cases'],
                          matrix['keep_pr_page_cases']), (55, 13, 8))
        for key in ('resolve_mismatches', 'parse_mismatches',
                    'to_hash_mismatches', 'keep_pr_page_mismatches'):
            self.assertEqual(matrix[key], {}, key)
        contracts = self.report['source_contracts']
        self.assertEqual(contracts['checked'], 34)
        self.assertEqual(contracts['missing'], [])

    def test_frozen_views_and_aliases(self):
        views = self.report['views']
        self.assertEqual(
            [v['hash'] for v in views['global']],
            ['#ubs', '#triton', '#method'])
        self.assertEqual([v['nav_target'] for v in views['global']],
                         ['ubs-overview', 'triton', 'method'])
        prs = {repo: kinds['repo']['prs']
               for repo, kinds in views['per_repo'].items()}
        self.assertEqual(prs, {'ubs-engine': 68, 'ubs-comm': 28,
                               'ubs-virt': 29, 'ubs-io': 6, 'ubs-mem': 12,
                               'OmniStateStore': 20, 'ham': 1,
                               'ubturbo': 27, 'ubs-atomic': 12})
        engine = views['per_repo']['ubs-engine']
        self.assertEqual(engine['repo'],
                         {'hash': '#ubs/repo/ubs-engine',
                          'view_name': 'ubs-repo',
                          'nav_target': 'ubs-repo', 'roundtrip_ok': True,
                          'canonical_ok': True,
                          'snapshot_attribution_ok': True, 'prs': 68})
        self.assertEqual(engine['quality']['hash'],
                         '#ubs/repo/ubs-engine/quality')
        self.assertEqual(engine['quality']['view_name'], 'ubs-quality')
        self.assertEqual(self.report['legacy_aliases'],
                         {'#repositories': '#ubs',
                          '#overview': '#ubs/repo/ubs-engine',
                          '#prs': '#ubs/repo/ubs-engine',
                          '#quality': '#ubs/repo/ubs-engine/quality',
                          '#method': '#method',
                          '#repo/ubs-engine': '#ubs/repo/ubs-engine',
                          '#repo/ubs-comm/quality':
                              '#ubs/repo/ubs-comm/quality',
                          '#repo/ubs-engine/method': '#method'})
        self.assertEqual(self.report['unknown_routes'],
                         {'(empty)': '#ubs', '#xyz': '#ubs', '#UBS': '#ubs',
                          '#ubs/repo': '#ubs', '#ubs/unknown': '#ubs',
                          '#ubs/repo/unknown-repo':
                              '#ubs/repo/unknown-repo'})

    def test_frozen_baseline(self):
        baseline = self.report['baseline']
        self.assertEqual(baseline['status'], 'matched')
        checks = baseline['checks']
        for name, check in checks.items():
            self.assertTrue(check['passed'], name)
        u01 = checks['U01_nine_repos_all_views']
        self.assertEqual([u01['repos'], u01['snapshots'], u01['views']],
                         [9, 9, 21])
        self.assertEqual(checks['U10-repositories_legacy']['resolved'],
                         '#ubs')
        self.assertEqual(checks['U10-overview_legacy']['resolved'],
                         '#ubs/repo/ubs-engine')
        self.assertEqual(checks['U10-prs_legacy']['resolved'],
                         '#ubs/repo/ubs-engine')
        self.assertEqual(checks['AC02_quality_legacy']['resolved'],
                         '#ubs/repo/ubs-engine/quality')
        self.assertEqual(checks['AC02_method_alias']['resolved'], '#method')
        self.assertIn('locked_by', checks['U11_unknown_repo_notice'])


if __name__ == '__main__':
    unittest.main()
