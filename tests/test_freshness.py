"""REQ-049 · 新鲜度与异常/空态表达保持 — 测试。

锁定 scripts/verify_freshness.py 的独立镜像语义：
- freshnessSlots：北京时间 08:00/12:00/16:00/18:00/20:00 计划槽位（含前夜
  20:00）、90 分钟宽限、严格小于判定；AC01 精确案例（旧 08:17 快照在
  12:00 槽位宽限结束的 13:30 显示延迟、13:29 不延迟）
- 合成目录树：干净树退出码 0；篡改槽位小时表、提醒文案、导出恢复
  finally、HTTP 状态错误抛出退出码 1（M04/A04/F02 口径）
- 提交证据（freshness-evidence.json）：冻结输入基线回放与结论
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

import verify_freshness as vfr  # noqa: E402

EVIDENCE_PATH = (ROOT / 'audit' / '2026-10-09' / 'evidence'
                 / 'freshness-evidence.json')

utc = vfr._utc_ms


class FreshnessMirrorTests(unittest.TestCase):
    """freshnessSlots 镜像：槽位、宽限与延迟判定（AC01）。"""

    def test_ac01_exact_case(self):
        # 北京时间 13:30 恰过 12:00 槽位宽限，08:17 快照 → 延迟
        result = vfr.own_freshness_slots(utc(2026, 10, 9, 5, 30),
                                         utc(2026, 10, 9, 0, 17))
        self.assertTrue(result['stale'])
        self.assertEqual(result['latest'], utc(2026, 10, 9, 4, 0))  # 12:00
        # 存活槽位：前夜 20:00、08:00、12:00（18/20 尚未到）
        self.assertEqual(result['slots'],
                         [utc(2026, 10, 8, 12, 0), utc(2026, 10, 9, 0, 0),
                          utc(2026, 10, 9, 4, 0)])

    def test_before_grace_not_stale(self):
        # 13:29 未过 12:00 槽位宽限 → 最新槽位仍 08:00，08:17 不延迟
        result = vfr.own_freshness_slots(utc(2026, 10, 9, 5, 29),
                                         utc(2026, 10, 9, 0, 17))
        self.assertFalse(result['stale'])
        self.assertEqual(result['latest'], utc(2026, 10, 9, 0, 0))

    def test_strict_comparison_and_newer(self):
        now = utc(2026, 10, 9, 5, 30)
        # 采集恰好等于最新槽位：严格小于才延迟
        self.assertFalse(vfr.own_freshness_slots(
            now, utc(2026, 10, 9, 4, 0))['stale'])
        # 采集晚于最新槽位（12:30 采集 > 12:00 槽位）
        self.assertFalse(vfr.own_freshness_slots(
            now, utc(2026, 10, 9, 4, 30))['stale'])

    def test_missing_collected(self):
        result = vfr.own_freshness_slots(utc(2026, 10, 9, 5, 30), None)
        self.assertFalse(result['stale'])
        self.assertIsNotNone(result['latest'])

    def test_early_morning_prev_day_slot(self):
        # 凌晨 03:00：最新槽位为前夜 20:00
        now = utc(2026, 10, 8, 19, 0)
        fresh = vfr.own_freshness_slots(now, utc(2026, 10, 8, 12, 17))
        self.assertEqual(fresh['latest'], utc(2026, 10, 8, 12, 0))
        self.assertFalse(fresh['stale'])  # 20:17 采集 ≥ 前夜 20:00 槽位
        stale = vfr.own_freshness_slots(now, utc(2026, 10, 8, 11, 0))
        self.assertTrue(stale['stale'])   # 19:00 采集早于前夜 20:00 槽位

    def test_midnight_rollover(self):
        # 北京时间零点翻转：最新槽位仍为前夜 20:00
        now = utc(2026, 10, 9, 16, 0)  # BJ 10-10 00:00
        self.assertEqual(vfr.own_freshness_slots(
            now, utc(2026, 10, 9, 12, 17))['latest'],
            utc(2026, 10, 9, 12, 0))  # BJ 10-09 20:00
        self.assertFalse(vfr.own_freshness_slots(
            now, utc(2026, 10, 9, 12, 17))['stale'])
        self.assertTrue(vfr.own_freshness_slots(
            now, utc(2026, 10, 9, 11, 30))['stale'])

    def test_next_day_and_boundaries(self):
        # 次日 10:00：最新槽位为当日 08:00，昨日 08:17 快照延迟
        result = vfr.own_freshness_slots(utc(2026, 10, 10, 2, 0),
                                         utc(2026, 10, 9, 0, 17))
        self.assertEqual(result['latest'], utc(2026, 10, 10, 0, 0))
        self.assertTrue(result['stale'])
        # 09:29/09:30：08:00 槽位宽限边界
        self.assertEqual(vfr.own_freshness_slots(
            utc(2026, 10, 9, 1, 29), utc(2026, 10, 9, 0, 17))['latest'],
            utc(2026, 10, 8, 12, 0))
        self.assertEqual(vfr.own_freshness_slots(
            utc(2026, 10, 9, 1, 30), utc(2026, 10, 9, 0, 17))['latest'],
            utc(2026, 10, 9, 0, 0))
        # 21:29/21:30：20:00 槽位宽限边界
        self.assertEqual(vfr.own_freshness_slots(
            utc(2026, 10, 9, 13, 29), utc(2026, 10, 9, 10, 17))['latest'],
            utc(2026, 10, 9, 10, 0))  # 18:00
        self.assertEqual(vfr.own_freshness_slots(
            utc(2026, 10, 9, 13, 30), utc(2026, 10, 9, 10, 17))['latest'],
            utc(2026, 10, 9, 12, 0))  # 20:00

    def test_bj_day_start_integer_math(self):
        # BJ 13:30 → 位移坐标当日零点 = 当日 UTC 00:00 纪元
        self.assertEqual(vfr._bj_day_start(utc(2026, 10, 9, 5, 30)),
                         utc(2026, 10, 9, 0, 0))
        # BJ 零点整：日期已翻至次日
        self.assertEqual(vfr._bj_day_start(utc(2026, 10, 9, 16, 0)),
                         utc(2026, 10, 10, 0, 0))
        # 槽位折算：day + (hours-8)h 即北京时间槽位
        day = vfr._bj_day_start(utc(2026, 10, 9, 5, 30))
        self.assertEqual(day + (8 - 8) * 3600000, utc(2026, 10, 9, 0, 0))
        self.assertEqual(day + (12 - 8) * 3600000, utc(2026, 10, 9, 4, 0))
        self.assertEqual(day + (-4 - 8) * 3600000, utc(2026, 10, 8, 12, 0))


class SyntheticTreeTests(unittest.TestCase):
    """合成目录树：干净树通过；篡改表达前提退出码 1。"""

    def build_tree(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        (root / 'web').mkdir(parents=True)
        for name in ('triton-core.js', 'triton-view.js', 'app.js',
                     'index.html'):
            shutil.copy(ROOT / 'web' / name, root / 'web' / name)
        return root

    def run_tool(self, root):
        output = root / 'report.json'
        with redirect_stdout(io.StringIO()):
            code = vfr.main(['--root', str(root), '--output', str(output)])
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
        self.assertEqual(report['freshness_slots'],
                         {'cases': {'freshnessSlots': 19}, 'total': 19,
                          'node_status': 'ok', 'mismatches': {}})
        self.assertEqual(report['source_contracts'],
                         {'checked': 36, 'missing': []})
        self.assertEqual(report['baseline']['status'], 'not_applicable')

    def test_tampered_slots_hours_exit_one(self):
        root = self.build_tree()
        self.tamper(root, 'triton-core.js', '[-4, 8, 12, 16, 18, 20]',
                    '[-4, 8, 12, 16, 18, 21]')
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertIn('triton-core.js:slots_hours',
                      report['source_contracts']['missing'])
        self.assertTrue(report['freshness_slots']['mismatches'])

    def test_tampered_freshness_text_exit_one(self):
        root = self.build_tree()
        self.tamper(root, 'triton-view.js', '当前展示最后一次成功采集结果',
                    '当前展示最近一次成功采集结果')
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertIn('triton-view.js:freshness_notice_text',
                      report['source_contracts']['missing'])

    def test_tampered_export_recover_exit_one(self):
        root = self.build_tree()
        self.tamper(root, 'triton-view.js', 'exportBtn.disabled = false;',
                    'exportBtn.disabled = true;')
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertIn('triton-view.js:export_recover',
                      report['source_contracts']['missing'])

    def test_tampered_http_error_exit_one(self):
        root = self.build_tree()
        self.tamper(root, 'app.js', "throw Error(label+' HTTP '+response.status)",
                    "throw Error(response.status)")
        code, report = self.run_tool(root)
        self.assertEqual(code, 1)
        self.assertIn('app.js:http_error',
                      report['source_contracts']['missing'])


class CommittedEvidenceTests(unittest.TestCase):
    """提交证据（freshness-evidence.json）：冻结输入保持结论。"""

    @classmethod
    def setUpClass(cls):
        cls.report = json.loads(EVIDENCE_PATH.read_text('utf-8'))

    def test_frozen_overall(self):
        self.assertTrue(self.report['input']['matches_audit_frozen_input'])
        self.assertEqual(self.report['input']['triton_sha256'],
                         'bc3d2d67d3b479eea71f5ec286e27f8e2ac2f2d3d4d002c7c'
                         '5b40d71d2642ceb')
        self.assertEqual(self.report['overall'], {'status': 'verified',
                                                  'problems': []})
        self.assertEqual(self.report['freshness_slots'],
                         {'cases': {'freshnessSlots': 17}, 'total': 17,
                          'node_status': 'ok', 'mismatches': {}})
        self.assertEqual(self.report['source_contracts'],
                         {'checked': 36, 'missing': []})

    def test_frozen_baseline(self):
        baseline = self.report['baseline']
        self.assertEqual(baseline['status'], 'matched')
        checks = baseline['checks']
        self.assertEqual(set(checks),
                         {'F02-triton-404', 'A04', 'M04'})
        f02 = checks['F02-triton-404']
        self.assertEqual(f02['label'], 'Triton 异常提供明确空态')
        self.assertEqual((f02['actual'], f02['expected']), (True, True))
        self.assertTrue(f02['passed'])
        a04 = checks['A04']
        self.assertEqual(a04['label'], 'Triton 导出失败明确且按钮恢复')
        self.assertEqual(a04['actual'], {'error': True, 'enabled': True})
        self.assertEqual(a04['expected'], {'error': True, 'enabled': True})
        self.assertTrue(a04['passed'])
        m04 = checks['M04']
        self.assertEqual(m04['label'], 'Triton新鲜度延迟提醒')
        self.assertEqual(
            m04['expected'],
            '超过北京时间13:00加90分钟且快照仍08:17时显示延迟')
        self.assertEqual(
            m04['actual'],
            '继续审查时已经14:39，提醒按实际检查时刻显示；这不是采集失败'
            '已证实的结论')
        self.assertTrue(m04['passed'])


if __name__ == '__main__':
    unittest.main()
