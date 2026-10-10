"""REQ-048 · 多浏览器与指针触屏操作保持 — 测试。

锁定 scripts/verify_interactions.py 的独立镜像语义：
- triton-core.js 共享时间规则：minWindowSpan（30 分钟或整窗）、
  windowForHours（五档快捷锚定末端）、moveWindow（整体拖拽/空白跳转
  平移夹界）、clampBoundary（边界拖拽保最小选区）、keyWindow（键盘
  路径 12 动作与指针同约束）、navSliderSemantics（JS Math.round 半值
  进位）、recoverWindow（快照更新选区恢复）、placeTipBox（固定卡片
  级联放置不遮散点）、axisTicks（窄屏刻度收敛）（AC02/AC03 口径）
- 合成目录树：干净树退出码 0；篡改 triton-core.js 最小选区公式、
  triton-view.js 快捷档、style.css 触屏 touch-action、app.js 挂载
  退出码 1（T22–T25/T28/A09/E01–E03 的静态前提）
- 提交证据（interaction-evidence.json）：冻结输入基线回放与结论
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

import verify_interactions as vin  # noqa: E402

EVIDENCE_PATH = (ROOT / 'audit' / '2026-10-09' / 'evidence'
                 / 'interaction-evidence.json')
HOUR = 3600000
DAY3 = 72 * HOUR


class RoundAndSpanTests(unittest.TestCase):
    """JS 舍入与最小选区语义。"""

    def test_js_round_half_up(self):
        # JS Math.round 半值进位；Python round 是银行家舍入（0.5→0、2.5→2）
        self.assertEqual(vin._js_round(0.5), 1)
        self.assertEqual(vin._js_round(1.5), 2)
        self.assertEqual(vin._js_round(2.5), 3)
        self.assertEqual(vin._js_round(-0.5), 0)
        self.assertEqual(vin._js_round(2), 2)
        self.assertNotEqual(round(0.5), vin._js_round(0.5))

    def test_min_window_span(self):
        self.assertEqual(vin.own_min_window_span(0, DAY3), 1800000)
        self.assertEqual(vin.own_min_window_span(0, 1200000), 1200000)  # 短窗=整窗
        self.assertEqual(vin.own_min_window_span(1000, 1000), 0)
        self.assertEqual(vin.own_min_window_span(2000000, 1000000), 0)  # 倒置域
        self.assertEqual(vin.own_min_window_span(0, 1800000), 1800000)


class TimeRuleTests(unittest.TestCase):
    """指针/触屏/键盘共享的时间规则（AC02）。"""

    def test_window_for_hours(self):
        de = DAY3
        self.assertEqual(vin.own_window_for_hours(0, de, 6), [de - 6 * HOUR, de])
        self.assertEqual(vin.own_window_for_hours(0, de, 12), [de - 12 * HOUR, de])
        self.assertEqual(vin.own_window_for_hours(0, de, 24), [de - 24 * HOUR, de])
        self.assertEqual(vin.own_window_for_hours(0, de, 48), [de - 48 * HOUR, de])
        self.assertEqual(vin.own_window_for_hours(0, de, 72), [0, de])
        self.assertEqual(vin.own_window_for_hours(0, de, 96), [0, de])  # 超窗取整窗
        self.assertEqual(vin.own_window_for_hours(0, de, 0), [de, de])  # 镜像 JS
        self.assertEqual(vin.own_window_for_hours(0, 1200000, 6), [0, 1200000])
        self.assertEqual(vin.own_window_for_hours(1000000, de, 24),
                         [de - 24 * HOUR, de])

    def test_move_window(self):
        self.assertEqual(vin.own_move_window(0, DAY3, 100000000, 160000000, 0),
                         [100000000, 160000000])
        self.assertEqual(vin.own_move_window(0, DAY3, 100000000, 160000000,
                                             10000000),
                         [110000000, 170000000])
        # 越界夹回且保持跨度
        self.assertEqual(vin.own_move_window(100000000, 200000000,
                                             120000000, 140000000, -60000000),
                         [100000000, 120000000])
        self.assertEqual(vin.own_move_window(100000000, 200000000,
                                             120000000, 140000000, 80000000),
                         [180000000, 200000000])
        self.assertEqual(vin.own_move_window(0, DAY3, 0, DAY3, 5000000),
                         [0, DAY3])  # 全窗不可再移
        self.assertEqual(vin.own_move_window(1000, 1000, 1000, 1000, 500),
                         [1000, 1000])  # 零跨度域
        # 恰好右对齐（nextEnd == domainEnd 不触发夹界）
        self.assertEqual(vin.own_move_window(0, DAY3, 100000000, 160000000,
                                             99200000),
                         [199200000, 259200000])

    def test_clamp_boundary(self):
        vs, ve = 20 * HOUR, 40 * HOUR
        self.assertEqual(vin.own_clamp_boundary(0, DAY3, vs, ve, 'start', HOUR),
                         HOUR)
        self.assertEqual(vin.own_clamp_boundary(0, DAY3, vs, ve, 'start', -5),
                         0)  # 低于域起点
        self.assertEqual(vin.own_clamp_boundary(0, DAY3, vs, ve, 'start',
                                                150 * HOUR),
                         ve - 1800000)  # 压缩到最小选区
        self.assertEqual(vin.own_clamp_boundary(0, DAY3, vs, ve, 'end',
                                                50 * HOUR), 50 * HOUR)
        self.assertEqual(vin.own_clamp_boundary(0, DAY3, vs, ve, 'end', DAY3),
                         DAY3)
        self.assertEqual(vin.own_clamp_boundary(0, DAY3, vs, ve, 'end',
                                                10 * HOUR),
                         vs + 1800000)  # 不低于最小选区
        # 短域：minSpan 即整窗
        self.assertEqual(vin.own_clamp_boundary(0, 1200000, 0, 600000, 'start',
                                                500000), 0)
        self.assertEqual(vin.own_clamp_boundary(0, 1200000, 0, 600000, 'end',
                                                1300000), 1200000)
        self.assertEqual(vin.own_clamp_boundary(1000, 1000, 1000, 1000,
                                                'start', 2000), 1000)

    def test_key_window(self):
        vs, ve = 20 * HOUR, 40 * HOUR  # 跨度 20h，步长 span/10 = 2h
        self.assertEqual(vin.own_key_window('window-left', 0, DAY3, vs, ve),
                         [18 * HOUR, 38 * HOUR])
        self.assertEqual(vin.own_key_window('window-right', 0, DAY3, vs, ve),
                         [22 * HOUR, 42 * HOUR])
        self.assertEqual(vin.own_key_window('window-home', 0, DAY3, vs, ve),
                         [0, 20 * HOUR])
        self.assertEqual(vin.own_key_window('window-end', 0, DAY3, vs, ve),
                         [52 * HOUR, 72 * HOUR])
        self.assertEqual(vin.own_key_window('start-home', 0, DAY3, vs, ve),
                         [0, 40 * HOUR])
        self.assertEqual(vin.own_key_window('start-end', 0, DAY3, vs, ve),
                         [39 * HOUR + 1800000, 40 * HOUR])  # 收到最小选区
        self.assertEqual(vin.own_key_window('end-home', 0, DAY3, vs, ve),
                         [20 * HOUR, 20 * HOUR + 1800000])
        self.assertEqual(vin.own_key_window('end-end', 0, DAY3, vs, ve),
                         [20 * HOUR, 72 * HOUR])
        # 贴左界再左移不动；贴右界再右移不动
        self.assertEqual(vin.own_key_window('window-left', 0, DAY3, 0, 20 * HOUR),
                         [0, 20 * HOUR])
        self.assertEqual(vin.own_key_window('window-right', 0, DAY3,
                                            52 * HOUR, 72 * HOUR),
                         [52 * HOUR, 72 * HOUR])
        # 最小选区窗：步长至少 minSpan
        self.assertEqual(vin.own_key_window('start-left', 0, DAY3,
                                            HOUR, HOUR + 1800000),
                         [HOUR - 1800000, HOUR + 1800000])
        # 未知动作原样返回
        self.assertEqual(vin.own_key_window('noop', 0, DAY3, vs, ve), [vs, ve])

    def test_nav_slider_semantics(self):
        sem = vin.own_nav_slider_semantics(0, DAY3, 20 * HOUR, 40 * HOUR)
        self.assertEqual(sem['window'], {'min': 0, 'max': DAY3,
                                         'now': 30 * HOUR})
        self.assertEqual(sem['start'], {'min': 0, 'max': 40 * HOUR - 1800000,
                                        'now': 20 * HOUR})
        self.assertEqual(sem['end'], {'min': 20 * HOUR + 1800000, 'max': DAY3,
                                      'now': 40 * HOUR})
        # JS 半值进位（Python round(0.5)==0 会失真）
        self.assertEqual(vin.own_nav_slider_semantics(0, DAY3, 0, 1)['window']
                         ['now'], 1)
        self.assertEqual(vin.own_nav_slider_semantics(0, DAY3, 1, 2)['window']
                         ['now'], 2)

    def test_recover_window(self):
        full = {'start': 20 * HOUR, 'end': 40 * HOUR, 'adjusted': False,
                'reason': None}
        self.assertEqual(vin.own_recover_window(20 * HOUR, 40 * HOUR, 0, DAY3),
                         full)  # 完全包含原样保留
        clipped = vin.own_recover_window(20 * HOUR, 40 * HOUR, 0, 30 * HOUR)
        self.assertEqual(clipped['start'], 20 * HOUR)
        self.assertEqual(clipped['end'], 30 * HOUR)
        self.assertTrue(clipped['adjusted'])
        self.assertEqual(clipped['reason'], '原选区已按新采集窗口裁剪为交集')
        tail = vin.own_recover_window(0, HOUR, 20 * HOUR, DAY3)
        self.assertEqual(tail['end'], DAY3)
        self.assertEqual(tail['start'], DAY3 - HOUR)  # L=min(W,max(span,m))
        self.assertEqual(tail['reason'],
                         '原选区与新采集窗口无有效交集，已恢复为新窗口末尾选区')
        self.assertEqual(vin.own_recover_window(40 * HOUR, 20 * HOUR, 0, DAY3),
                         {'start': 0, 'end': DAY3, 'adjusted': False,
                          'reason': None})  # 旧选区非法 → 全新窗
        self.assertIsNone(vin.own_recover_window(0, HOUR, 20 * HOUR, 20 * HOUR))
        self.assertIsNone(vin.own_recover_window(0, HOUR, None, None))
        # 交集恰达 m 时保留交集
        exact = vin.own_recover_window(0, 1800000, 0, DAY3)
        self.assertEqual((exact['start'], exact['end']), (0, 1800000))
        self.assertFalse(exact['adjusted'])

    def test_place_tip_box(self):
        roomy = vin.own_place_tip_box(400, 400, 300, 200, 1440, 1000, 16, 16)
        self.assertEqual(roomy, {'x': 414, 'y': 414})
        # 右缘夹紧
        right = vin.own_place_tip_box(1300, 400, 300, 200, 1440, 1000, 16, 16)
        self.assertEqual(right['x'], 1128)
        # 高卡先上翻再左移，且结果不遮 16×16 散点框
        tall = vin.own_place_tip_box(1300, 950, 300, 990, 1440, 1000, 16, 16)
        bx, by = 1300 - 8, 950 - 8
        self.assertFalse(tall['x'] < bx + 16 and tall['x'] + 300 > bx
                         and tall['y'] < by + 16 and tall['y'] + 990 > by)
        # 视口窄于卡片：夹到 pad
        narrow = vin.own_place_tip_box(400, 400, 300, 200, 200, 1000, 16, 16)
        self.assertEqual(narrow['x'], 12)
        wider = vin.own_place_tip_box(400, 400, 430, 200, 300, 1000, 16, 16)
        self.assertEqual(wider['x'], 12)

    def test_axis_ticks(self):
        self.assertEqual(len(vin.own_axis_ticks(0, DAY3, 800, 70)), 7)
        self.assertEqual(len(vin.own_axis_ticks(0, DAY3, 400, 70)), 5)
        self.assertEqual(len(vin.own_axis_ticks(0, DAY3, 120, 70)), 2)  # 窄屏
        self.assertEqual(len(vin.own_axis_ticks(0, DAY3, 0, 70)), 2)
        self.assertEqual(len(vin.own_axis_ticks(0, DAY3, -50, 70)), 2)
        self.assertEqual(len(vin.own_axis_ticks(0, DAY3, None, 70)), 2)  # 缺宽
        self.assertEqual(len(vin.own_axis_ticks(0, HOUR, 800, 70, 10, 3)), 3)
        self.assertEqual(len(vin.own_axis_ticks(0, DAY3, 300, 70, 5)), 4)
        # 零跨度/倒置跨度以 1ms 兜底，首末刻度仍为端点
        ticks = vin.own_axis_ticks(1000, 1000, 800, 70)
        self.assertEqual(len(ticks), 7)
        self.assertEqual(ticks[0], 1000)
        inv = vin.own_axis_ticks(5000000, 0, 800, 70)
        self.assertEqual(inv[0], 5000000)
        self.assertEqual(len(inv), 7)


class SyntheticTreeTests(unittest.TestCase):
    """合成目录树：干净树通过；篡改交互前提退出码 1。"""

    def build_tree(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / 'web/data/repos').mkdir(parents=True)
        for name in ('triton-core.js', 'triton-view.js', 'style.css',
                     'app.js', 'index.html'):
            shutil.copy(ROOT / 'web' / name, root / 'web' / name)
        index = {'schema_version': 3, 'start_ms': 1000, 'end_ms': 9000,
                 'repositories': [
                     {'name': 'alpha', 'repository': 'org/alpha',
                      'snapshot': 'repos/alpha.json', 'status': 'success'}]}
        snapshot = {'meta': {'repository': 'org/alpha', 'start_ms': 1000,
                             'end_ms': 9000}, 'prs': []}
        (root / 'web/data/repositories.json').write_text(
            json.dumps(index), 'utf-8')
        (root / 'web/data/repos/alpha.json').write_text(
            json.dumps(snapshot), 'utf-8')
        return root

    def run_tool(self, root):
        output = root / 'report.json'
        with redirect_stdout(io.StringIO()):
            code = vin.main(['--root', str(root), '--output', str(output)])
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
        self.assertEqual(report['time_rules']['node_status'], 'ok')
        self.assertEqual(report['time_rules']['mismatches'], {})
        self.assertEqual(report['time_rules']['total'], 145)
        self.assertEqual(report['source_contracts'],
                         {'checked': 52, 'missing': []})
        self.assertEqual(report['views']['total'], 5)  # 1 仓 ×2 + 3 全局
        self.assertEqual(report['baseline']['status'], 'not_applicable')

    def test_tampered_min_span_exit_one(self):
        root = self.build_tree()
        self.tamper(root, 'triton-core.js', 'Math.min(30 * 60000',
                    'Math.min(20 * 60000')
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertIn('triton-core.js:min_span_formula',
                      report['source_contracts']['missing'])
        mismatches = report['time_rules']['mismatches']
        for fn in ('minWindowSpan', 'clampBoundary', 'keyWindow'):
            self.assertIn(fn, mismatches)

    def test_tampered_preset_hours_exit_one(self):
        root = self.build_tree()
        self.tamper(root, 'triton-view.js', 'data-hours="6">6 小时',
                    'data-hours="7">6 小时')
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertIn('triton-view.js:preset_hours_6',
                      report['source_contracts']['missing'])

    def test_tampered_touch_action_exit_one(self):
        root = self.build_tree()
        self.tamper(root, 'style.css', 'touch-action:none',
                    'touch-action:pan-y')
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertIn('style.css:nav_touch_action',
                      report['source_contracts']['missing'])

    def test_tampered_app_mount_exit_one(self):
        root = self.build_tree()
        self.tamper(root, 'app.js',
                    'window.TritonView.render(window.tritonPayload,el)',
                    'TritonView.render(window.tritonPayload,el)')
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertIn('app.js:triton_mount',
                      report['source_contracts']['missing'])


class CommittedEvidenceTests(unittest.TestCase):
    """提交证据（interaction-evidence.json）：冻结输入保持结论。"""

    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(EVIDENCE_PATH.read_text('utf-8'))

    def test_frozen_overall(self):
        self.assertTrue(self.report['input']['matches_audit_frozen_input'])
        self.assertEqual(self.report['overall'], {'status': 'verified',
                                                  'problems': []})
        time_rules = self.report['time_rules']
        self.assertEqual(time_rules['cases'],
                         {'moveWindow': 14, 'clampBoundary': 16,
                          'keyWindow': 60, 'windowForHours': 10,
                          'minWindowSpan': 5, 'navSlider': 8,
                          'recoverWindow': 11, 'placeTip': 10,
                          'axisTicks': 11})
        self.assertEqual(time_rules['total'], 145)
        self.assertEqual(time_rules['node_status'], 'ok')
        self.assertEqual(time_rules['mismatches'], {})
        self.assertEqual(self.report['source_contracts'],
                         {'checked': 52, 'missing': []})
        self.assertEqual(self.report['views'],
                         {'status': 'ok', 'total': 21, 'expected_total': 21,
                          'repos': 9, 'per_repo_views': 18,
                          'global_views': 3, 'per_repo_checks_ok': True,
                          'global_checks_ok': True})

    def test_frozen_baseline(self):
        baseline = self.report['baseline']
        self.assertEqual(baseline['status'], 'matched')
        self.assertEqual(baseline['triton_sha256'],
                         'bc3d2d67d3b479eea71f5ec286e27f8e2ac2f2d3d4d002c7c5b'
                         '40d71d2642ceb')
        expected = {
            'T22': True, 'T23': True, 'T24': True, 'T25': True, 'T28': True,
            'A09': True,
            'E01': 2, 'E02': [65], 'E03': 9,
        }
        self.assertEqual(set(baseline['checks']), set(expected))
        for cid, value in expected.items():
            check = baseline['checks'][cid]
            self.assertEqual(check['actual'], value, cid)
            self.assertEqual(check['expected'], value, cid)
            self.assertTrue(check['passed'], cid)
        self.assertEqual(baseline['console_errors'], [])
        self.assertEqual(baseline['audit_counts'],
                         {'passed': 54, 'failed': 10, 'unverified': 1})
        supporting = baseline['supporting']
        self.assertEqual((supporting['T21']['actual'],
                          supporting['T21']['expected'],
                          supporting['T21']['passed']), (False, False, True))
        self.assertEqual((supporting['V-mobile-tip']['actual'],
                          supporting['V-mobile-tip']['expected'],
                          supporting['V-mobile-tip']['passed']),
                         (True, True, True))


if __name__ == '__main__':
    unittest.main()
