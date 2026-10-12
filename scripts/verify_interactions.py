#!/usr/bin/env python3
"""REQ-048 · 多浏览器与指针触屏操作保持 — 独立验证工具。

镜像 web/triton-core.js 的共享时间规则（指针、触屏与键盘同源）：
windowForHours/moveWindow/minWindowSpan/clampBoundary/keyWindow/
navSliderSemantics/recoverWindow/placeTipBox/axisTicks，并与真实
triton-core.js 单次 node 调用在矩阵案例上逐项核对（AC02：整体/左右
边界拖拽、空白跳转、五档快捷选择与键盘路径同约束不越界；AC03：固定
卡片级联放置）。锁定 triton-view.js 指针/键盘/悬浮固定/外部取消/批次
展开/销毁清理接线、triton-core.js 约束公式、style.css 触屏与滚动容器
契约、app.js Triton 挂载与跨域渲染、index.html 脚本加载共 52 条源码
契约。结构化核验 2N+3 主要视图可达（AC01）。web/data/triton.json
指纹与审计冻结 artifact_sha256 一致时回放 T22/T23/T24/T25/T28（拖拽/
边界/空白跳转/批次展开）、A09（触屏共享导航器）、E01/E02/E03（Edge
挂载/时间窗/跨域导航）与 consoleErrors（AC04）；输入更新后基线记
not_applicable，矩阵与契约检查照常。
"""
import argparse
import hashlib
import json
import math
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import verify_ubs_routes as vur  # noqa: E402  (own_views: 2N+3 视图枚举)

EVIDENCE_REL = Path('audit/2026-10-09/evidence')

HOUR = 3600000
MIN_SPAN_MS = 30 * 60000


def stamp():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _js_round(value):
    """JS Math.round：半值远离零方向（floor(x+0.5)），区别于 Python 银行家舍入。"""
    return math.floor(value + 0.5)


def _finite(value):
    """JS Number.isFinite：仅有限数值为真（null/bool/字符串均假）。"""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


# ---- triton-core.js 镜像：指针/触屏/键盘共享的时间规则 ----

def own_min_window_span(domain_start, domain_end):
    """minWindowSpan：30 分钟或整个采集窗（窗更短时以可用窗为限）。"""
    return min(30 * 60000, max(0, domain_end - domain_start))


def own_window_for_hours(domain_start, domain_end, hours):
    """windowForHours：五档快捷选择，向左展开并锚定采集窗末端。"""
    return [max(domain_start, domain_end - hours * 3600000), domain_end]


def own_move_window(domain_start, domain_end, start, end, delta):
    """moveWindow：整体拖拽/空白跳转平移，保持跨度并夹在采集窗内。"""
    span = end - start
    next_start = start + delta
    next_end = end + delta
    if next_start < domain_start:
        return [domain_start, domain_start + span]
    if next_end > domain_end:
        return [domain_end - span, domain_end]
    return [next_start, next_end]


def own_clamp_boundary(domain_start, domain_end, view_start, view_end, side, value):
    """clampBoundary：左右边界拖拽，不越采集窗且保住最小选区。"""
    min_span = own_min_window_span(domain_start, domain_end)
    if side == 'start':
        return max(domain_start, min(value, view_end - min_span))
    return min(domain_end, max(value, view_start + min_span))


def own_key_window(action, domain_start, domain_end, view_start, view_end):
    """keyWindow：键盘路径与指针拖拽共用同一约束（12 个动作）。"""
    span = view_end - view_start
    min_span = own_min_window_span(domain_start, domain_end)
    step = max(min_span, span / 10)
    whole = min(span, domain_end - domain_start)

    def clamp_start(value):
        return own_clamp_boundary(domain_start, domain_end, view_start,
                                  view_end, 'start', value)

    def clamp_end(value):
        return own_clamp_boundary(domain_start, domain_end, view_start,
                                  view_end, 'end', value)

    def pan(delta):
        target = max(domain_start, min(domain_end - span, view_start + delta))
        return [target, target + span]

    if action == 'window-left':
        return pan(-step)
    if action == 'window-right':
        return pan(step)
    if action == 'window-home':
        return [domain_start, domain_start + whole]
    if action == 'window-end':
        return [domain_end - whole, domain_end]
    if action == 'start-left':
        return [clamp_start(view_start - step), view_end]
    if action == 'start-right':
        return [clamp_start(view_start + step), view_end]
    if action == 'start-home':
        return [domain_start, view_end]
    if action == 'start-end':
        return [clamp_start(view_end - min_span), view_end]
    if action == 'end-left':
        return [view_start, clamp_end(view_end - step)]
    if action == 'end-right':
        return [view_start, clamp_end(view_end + step)]
    if action == 'end-home':
        return [view_start, clamp_end(view_start + min_span)]
    if action == 'end-end':
        return [view_start, domain_end]
    return [view_start, view_end]


def own_nav_slider_semantics(domain_start, domain_end, view_start, view_end):
    """navSliderSemantics：三个滑块的 min/max/now（整体窗报告中心）。"""
    min_span = own_min_window_span(domain_start, domain_end)
    return {
        'window': {'min': domain_start, 'max': domain_end,
                   'now': _js_round((view_start + view_end) / 2)},
        'start': {'min': domain_start, 'max': view_end - min_span,
                  'now': view_start},
        'end': {'min': view_start + min_span, 'max': domain_end,
                'now': view_end},
    }


def own_recover_window(old_start, old_end, new_start, new_end):
    """recoverWindow：快照更新后的选区恢复（交集足够取交集，否则尾窗）。"""
    min_ms = 30 * 60 * 1000
    if not (_finite(new_start) and _finite(new_end)) or new_end <= new_start:
        return None
    width = new_end - new_start
    threshold = min(min_ms, width)
    if not (_finite(old_start) and _finite(old_end)) or old_end <= old_start:
        return {'start': new_start, 'end': new_end, 'adjusted': False,
                'reason': None}
    span = old_end - old_start
    isect_start = max(old_start, new_start)
    isect_end = min(old_end, new_end)
    if isect_end - isect_start >= threshold:
        unchanged = isect_start == old_start and isect_end == old_end
        return {'start': isect_start, 'end': isect_end,
                'adjusted': not unchanged,
                'reason': None if unchanged else '原选区已按新采集窗口裁剪为交集'}
    length = min(width, max(span, threshold))
    return {'start': new_end - length, 'end': new_end, 'adjusted': True,
            'reason': '原选区与新采集窗口无有效交集，已恢复为新窗口末尾选区'}


def own_place_tip_box(ax, ay, width, height, vw, vh, mark_w, mark_h):
    """placeTipBox：固定卡片级联放置（夹入视口→上翻→左移，不遮发起散点）。"""
    pad, gap = 12, 14
    bx, by = ax - mark_w / 2, ay - mark_h / 2

    def clamp(value, lo, hi):
        return max(lo, min(value, hi))

    def covers(px, py):
        return (px < bx + mark_w and px + width > bx
                and py < by + mark_h and py + height > by)

    px = clamp(ax + gap, pad, max(pad, vw - width - pad))
    py = clamp(ay + gap, pad, max(pad, vh - height - pad))
    if covers(px, py):
        py = clamp(by - height - gap, pad, max(pad, vh - height - pad))
    if covers(px, py):
        px = clamp(bx - width - gap, pad, max(pad, vw - width - pad))
    return {'x': px, 'y': py}


def own_axis_ticks(start, end, plot_width, label_width, gap=10, max_ticks=7):
    """axisTicks：横轴刻度数随绘图区宽度自适应（首末两端恒为刻度）。"""
    from_ts, to_ts = start, end  # 矩阵传数值，+new Date 数值恒等
    span = max(to_ts - from_ts, 1)
    width = plot_width if _finite(plot_width) else 0
    fit = math.floor((width + gap) / (label_width + gap))
    count = min(max_ticks, max(2, fit))
    return [from_ts + (i * span) / (count - 1) for i in range(count)]


# ---- 矩阵案例：指针/触屏/键盘共享时间规则的独立期望 ----
# 主域：72 小时采集窗（毫秒）；另含 20 分钟短窗、零窗、边界与最小选区状态。

MOVE_WINDOW_MATRIX = [
    [0, 259200000, 100000000, 160000000, 10000000],    # 右移仍在窗内
    [0, 259200000, 100000000, 160000000, -10000000],   # 左移仍在窗内
    [0, 259200000, 100000000, 160000000, 0],           # 零位移恒等
    [100000000, 200000000, 120000000, 140000000, -60000000],  # 越左界夹回
    [100000000, 200000000, 120000000, 140000000, 80000000],   # 越右界夹回
    [0, 259200000, 0, 259200000, 5000000],             # 全窗右移夹回
    [0, 259200000, 0, 259200000, -5000000],            # 全窗左移夹回
    [0, 259200000, 246000000, 259200000, -30000000],   # 末段左移保持跨度
    [0, 1200000, 0, 600000, 600000],                   # 短窗恰好贴右界
    [0, 1200000, 0, 600000, 700000],                   # 短窗越右界夹回
    [1000, 1000, 1000, 1000, 500],                     # 零跨度域
    [0, 259200000, 253200000, 259200000, -2000000],    # 微移
    [0, 259200000, 100000000, 160000000, 99200000],    # 恰好右对齐
    [5000000, 259200000, 0, 10000000, 0],              # 起点越左界夹回
]

CLAMP_BOUNDARY_MATRIX = [
    [0, 259200000, 72000000, 144000000, 'start', 36000000],   # 域内
    [0, 259200000, 72000000, 144000000, 'start', -5000000],   # 低于域起点
    [0, 259200000, 72000000, 144000000, 'start', 120000000],  # 选区内移动
    [0, 259200000, 72000000, 144000000, 'start', 150000000],  # 压缩到最小选区
    [0, 259200000, 72000000, 144000000, 'end', 200000000],    # 域内
    [0, 259200000, 72000000, 144000000, 'end', 300000000],    # 超过域终点
    [0, 259200000, 72000000, 144000000, 'end', 70000000],     # 低于最小选区
    [0, 259200000, 72000000, 144000000, 'end', 73800000],     # 恰好最小选区
    [0, 1200000, 0, 600000, 'start', 500000],   # 短域：minSpan=整窗
    [0, 1200000, 0, 600000, 'end', 1300000],    # 短域：夹到域终点
    [0, 1200000, 0, 600000, 'end', 300000],     # 短域：低于最小选区
    [0, 259200000, 3600000, 3780000, 'start', 3000000],  # 30 分钟窗左界
    [0, 259200000, 3600000, 3780000, 'end', 4000000],    # 30 分钟窗右界
    [1000, 1000, 1000, 1000, 'start', 2000],    # 零跨度域
    [1000, 1000, 1000, 1000, 'end', 500],       # 零跨度域
    [0, 259200000, 72000000, 144000000, 'start', 0],     # 恰在域起点
]

KEY_ACTIONS = ['window-left', 'window-right', 'window-home', 'window-end',
               'start-left', 'start-right', 'start-home', 'start-end',
               'end-left', 'end-right', 'end-home', 'end-end']
KEY_STATES = [
    (0, 259200000, 72000000, 144000000),   # 域中 20 小时窗
    (0, 259200000, 0, 72000000),           # 贴左界
    (0, 259200000, 187200000, 259200000),  # 贴右界
    (0, 259200000, 3600000, 3780000),      # 最小选区（30 分钟）
    (0, 1200000, 0, 600000),               # 20 分钟短域
]
KEY_WINDOW_MATRIX = [[action, *state]
                     for state in KEY_STATES for action in KEY_ACTIONS]

WINDOW_FOR_HOURS_MATRIX = [
    [0, 259200000, 6],    # 五档快捷
    [0, 259200000, 12],
    [0, 259200000, 24],
    [0, 259200000, 48],
    [0, 259200000, 72],   # 恰为全窗
    [0, 259200000, 96],   # 超过采集窗
    [0, 259200000, 0],    # 零档（镜像 JS 行为）
    [0, 259200000, -6],   # 负档（镜像 JS 行为）
    [0, 1200000, 6],      # 短域
    [1000000, 259200000, 24],  # 非零起点域
]

MIN_SPAN_MATRIX = [
    [0, 259200000],   # 72 小时域 → 30 分钟
    [0, 1200000],     # 20 分钟域 → 整窗
    [1000, 1000],     # 零跨度
    [2000000, 1000000],  # 倒置域
    [0, 1800000],     # 恰 30 分钟
]

NAV_SLIDER_MATRIX = [
    [0, 259200000, 72000000, 144000000],
    [0, 259200000, 0, 72000000],
    [0, 259200000, 187200000, 259200000],
    [0, 259200000, 3600000, 3780000],
    [0, 1200000, 0, 600000],
    [0, 259200000, 1, 2],   # now=1.5 → JS 半值进位
    [0, 259200000, 0, 1],   # now=0.5 → JS 半值进位
    [0, 259200000, 0, 3],
]

RECOVER_MATRIX = [
    [72000000, 144000000, 0, 259200000],     # 完全包含：原样保留
    [72000000, 144000000, 0, 100000000],     # 右侧裁剪为交集
    [72000000, 144000000, 100000000, 259200000],  # 左侧裁剪为交集
    [0, 3600000, 72000000, 259200000],       # 无交集 → 尾窗（保留原跨度）
    [0, 600000, 72000000, 259200000],        # 无交集 → 尾窗（不小于 m）
    [144000000, 72000000, 0, 259200000],     # 旧选区非法 → 全新窗
    [None, None, 0, 259200000],              # 旧选区缺失 → 全新窗
    [0, 3600000, 72000000, 72000000],        # 新窗非法 → null
    [0, 3600000, None, None],                # 新窗缺失 → null
    [0, 3600000, 10000000, 1100000],         # 新窗短于 30 分钟
    [0, 1800000, 0, 259200000],              # 交集恰等于 m：保留
]

PLACE_TIP_MATRIX = [
    [400, 400, 300, 200, 1440, 1000, 16, 16],    # 视野宽裕
    [1300, 800, 300, 200, 1440, 1000, 16, 16],   # 右缘夹紧
    [1300, 950, 300, 200, 1440, 1000, 16, 16],   # 底缘夹紧
    [1300, 950, 300, 990, 1440, 1000, 16, 16],   # 高卡触发上翻再左移
    [400, 400, 300, 200, 200, 1000, 16, 16],     # 视口窄于卡片
    [10, 400, 300, 200, 1440, 1000, 16, 16],     # 散点贴左缘
    [0, 0, 300, 200, 1440, 1000, 16, 16],        # 左上角散点
    [1380, 500, 300, 200, 1440, 1000, 16, 16],   # 散点贴右缘
    [400, 400, 430, 200, 300, 1000, 16, 16],     # 卡片宽于视口
    [400, 150, 300, 400, 1000, 300, 16, 16],     # 卡片高于视口
]

AXIS_TICKS_MATRIX = [
    [0, 259200000, 800, 70],        # 宽绘图区 → 7 档
    [0, 259200000, 400, 70],        # 中等 → 5 档
    [0, 259200000, 120, 70],        # 窄屏 → 2 档
    [0, 259200000, 0, 70],          # 零宽 → 2 档
    [0, 259200000, None, 70],       # 宽度缺失（JS Number.isFinite(null)=false）
    [0, 259200000, -50, 70],        # 负宽 → 2 档
    [0, 3600000, 800, 70, 10, 3],   # maxTicks 参数
    [1000, 1000, 800, 70],          # 零跨度 → span=1
    [5000000, 0, 800, 70],          # 倒置跨度 → span=1
    [0, 259200000, 800, 200],       # 长标签 → 3 档
    [0, 259200000, 300, 70, 5],     # gap 参数
]

MATRICES = {
    'moveWindow': MOVE_WINDOW_MATRIX,
    'clampBoundary': CLAMP_BOUNDARY_MATRIX,
    'keyWindow': KEY_WINDOW_MATRIX,
    'windowForHours': WINDOW_FOR_HOURS_MATRIX,
    'minWindowSpan': MIN_SPAN_MATRIX,
    'navSlider': NAV_SLIDER_MATRIX,
    'recoverWindow': RECOVER_MATRIX,
    'placeTip': PLACE_TIP_MATRIX,
    'axisTicks': AXIS_TICKS_MATRIX,
}

OWN_DISPATCH = {
    'moveWindow': lambda a: own_move_window(*a),
    'clampBoundary': lambda a: own_clamp_boundary(*a),
    'keyWindow': lambda a: own_key_window(*a),
    'windowForHours': lambda a: own_window_for_hours(*a),
    'minWindowSpan': lambda a: own_min_window_span(*a),
    'navSlider': lambda a: own_nav_slider_semantics(*a),
    'recoverWindow': lambda a: own_recover_window(*a),
    'placeTip': lambda a: own_place_tip_box(*a),
    'axisTicks': lambda a: (own_axis_ticks(*a) if len(a) > 4
                            else own_axis_ticks(a[0], a[1], a[2], a[3])),
}


# ---- 与真实 triton-core.js 的单次 node 调用逐项核对 ----

_NODE_SCRIPT = r"""
const fs = require('fs');
const path = require('path');
const core = require(path.resolve(process.argv[2]));
const payload = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const out = {};
out.moveWindow = payload.moveWindow.map(a => core.moveWindow(a[0], a[1], a[2], a[3], a[4]));
out.clampBoundary = payload.clampBoundary.map(a => core.clampBoundary(a[0], a[1], a[2], a[3], a[4], a[5]));
out.keyWindow = payload.keyWindow.map(a => core.keyWindow(a[0], a[1], a[2], a[3], a[4]));
out.windowForHours = payload.windowForHours.map(a => core.windowForHours(a[0], a[1], a[2]));
out.minWindowSpan = payload.minWindowSpan.map(a => core.minWindowSpan(a[0], a[1]));
out.navSlider = payload.navSlider.map(a => core.navSliderSemantics(a[0], a[1], a[2], a[3]));
out.recoverWindow = payload.recoverWindow.map(a => core.recoverWindow(a[0], a[1], a[2], a[3]));
out.placeTip = payload.placeTip.map(a => core.placeTipBox(a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7]));
out.axisTicks = payload.axisTicks.map(a => a.length > 4
  ? core.axisTicks(a[0], a[1], a[2], a[3], a[4], a[5])
  : core.axisTicks(a[0], a[1], a[2], a[3]));
fs.writeFileSync(process.argv[4], JSON.stringify(out));
"""


def _node_check(root):
    """node 载入真实 triton-core.js，对全部矩阵案例求值并与镜像比对。"""
    core_path = root / 'web' / 'triton-core.js'
    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        payload_path = tmpdir / 'payload.json'
        result_path = tmpdir / 'result.json'
        script_path = tmpdir / 'check.js'
        payload_path.write_text(json.dumps(MATRICES), 'utf-8')
        script_path.write_text(_NODE_SCRIPT, 'utf-8')
        proc = subprocess.run(
            ['node', str(script_path), str(core_path),
             str(payload_path), str(result_path)],
            capture_output=True, text=True)
        if proc.returncode != 0:
            return {'status': 'failed',
                    'error': (proc.stderr or proc.stdout)[-2000:],
                    'mismatches': None}
        node_results = json.loads(result_path.read_text('utf-8'))
    mismatches = {}
    for fn, rows in MATRICES.items():
        own_values = [OWN_DISPATCH[fn](row) for row in rows]
        node_values = node_results.get(fn, [])
        bad = []
        for index, (own_value, node_value) in enumerate(
                zip(own_values, node_values)):
            if own_value != node_value:
                bad.append({'index': index, 'case': rows[index],
                            'own': own_value, 'node': node_value})
        if len(node_values) != len(rows):
            bad.append({'index': None, 'case': 'row_count',
                        'own': len(rows), 'node': len(node_values)})
        if bad:
            mismatches[fn] = bad
    return {'status': 'ok', 'mismatches': mismatches}


# ---- 源码契约：接线保持的静态锁定 ----

TRITON_VIEW_CONTRACTS = [
    ('preset_hours_6', 'data-hours="6">6 小时'),
    ('preset_hours_12', 'data-hours="12">12 小时'),
    ('preset_hours_24', 'data-hours="24">24 小时'),
    ('preset_hours_48', 'data-hours="48">48 小时'),
    ('preset_hours_72', 'data-hours="72">72 小时'),
    ('preset_click',
     '[viewStart, viewEnd] = core.windowForHours(domainStart, domainEnd,'
     ' Number(btn.dataset.hours));'),
    ('pointerdown_prevent_default',
     "e.preventDefault();\n      const mode = (e.target.dataset &&"
     " e.target.dataset.drag) || 'jump';"),
    ('pointer_capture', 'navSvg.setPointerCapture(e.pointerId);'),
    ('pointermove_window',
     "if (navDrag.mode === 'window') [viewStart, viewEnd] ="
     ' core.moveWindow(domainStart, domainEnd, navDrag.start, navDrag.end,'
     ' delta);'),
    ('pointermove_start',
     "else if (navDrag.mode === 'start') viewStart ="
     " core.clampBoundary(domainStart, domainEnd, viewStart, viewEnd,"
     " 'start', navDrag.start + delta);"),
    ('pointermove_end',
     "else viewEnd = core.clampBoundary(domainStart, domainEnd, viewStart,"
     " viewEnd, 'end', navDrag.end + delta);"),
    ('pointerup_cancel',
     "navSvg.onpointerup = navSvg.onpointercancel = () => { navDrag = null; };"),
    ('keyboard_directions',
     "const directions = { ArrowLeft: 'left', ArrowDown: 'left',"
     " ArrowRight: 'right', ArrowUp: 'right', Home: 'home', End: 'end' };"),
    ('keyboard_key_window',
     '[viewStart, viewEnd] = core.keyWindow(`${mode}-${direction}`,'
     ' domainStart, domainEnd, viewStart, viewEnd);'),
    ('mark_hover_enter',
     'mark.onmouseenter = e => { clearTimeout(tipTimer); placeTip(e, b,'
     ' html); };'),
    ('mark_hover_move',
     'mark.onmousemove = e => { if (!tipPinned) placeTip(e, b, html); };'),
    ('mark_hover_leave',
     'mark.onmouseleave = () => { if (!tipPinned) tipTimer ='
     ' setTimeout(() => hideTip(mark), 180); };'),
    ('mark_click_pin',
     "mark.onclick = e => { e.stopPropagation(); tipPinned = true;"
     ' lastPinnedMark = mark; placeTip(e, b, html); };'),
    ('mark_keyboard_pin', "if (e.key !== 'Enter' && e.key !== ' ') return;"),
    ('tip_escape_close',
     "tip.onkeydown = e => { if (e.key === 'Escape') { e.preventDefault();"
     ' hideTip(); } };'),
    ('tip_button_close',
     "tip.onclick = e => { if (e.target.closest('.tip-close')) {"
     ' e.stopPropagation(); hideTip(); } };'),
    ('outside_click_close',
     "if (!e.target.closest('.tooltip') && !e.target.closest('.mark-hit'))"
     ' hideTip();'),
    ('focus_return',
     'if (wasInside && target && target.isConnected) target.focus();'),
    ('row_click_expand', "if (e.target.closest('a')) return;"),
    ('row_aria_expanded', "btn.setAttribute('aria-expanded', String(open));"),
    ('row_toggle_button',
     'class="row-toggle" aria-expanded="false" aria-controls="${ids.detailId}"'),
    ('destroy_timer', 'clearInterval(freshTimer);'),
    ('destroy_resize', "window.removeEventListener('resize', onResize);"),
    ('destroy_click', "document.removeEventListener('click', onDocClick);"),
    ('default_window_72',
     '[viewStart, viewEnd] = core.windowForHours(domainStart, domainEnd, 72);'),
    ('recover_state',
     'const recovered = prevState ? core.recoverWindow(prevState.start,'
     ' prevState.end, domainStart, domainEnd) : null;'),
]

TRITON_CORE_CONTRACTS = [
    ('min_span_formula',
     'return Math.min(30 * 60000, Math.max(0, domainEnd - domainStart));'),
    ('clamp_start_formula',
     "if (side === 'start') return Math.max(domainStart, Math.min(value,"
     ' viewEnd - minSpan));'),
    ('clamp_end_formula',
     'return Math.min(domainEnd, Math.max(value, viewStart + minSpan));'),
    ('key_step_formula', 'const step = Math.max(minSpan, span / 10);'),
    ('move_window_clamp',
     'if (nextStart < domainStart) return [domainStart, domainStart + span];'),
]

STYLE_CONTRACTS = [
    ('nav_touch_action',
     '.nav-svg{display:block;width:100%;height:72px;touch-action:none;'
     'user-select:none}'),
    ('tooltip_viewport_cap',
     'width:min(430px,calc(100vw - 24px));max-height:min(76vh,680px,'
     'calc(50vh - 24px));overflow:auto'),
    ('table_scroll', '.table-scroll{overflow-x:auto}'),
    ('batch_content_scroll', '.batch-content{overflow-x:auto}'),
    ('media_1150', '@media(max-width:1150px)'),
    ('media_900', '@media(max-width:900px)'),
    ('media_800', '@media(max-width:800px)'),
    ('media_760', '@media(max-width:760px)'),
    ('media_560', '@media(max-width:560px)'),
]

APP_CONTRACTS = [
    ('triton_mount', 'window.TritonView.render(window.tritonPayload,el)'),
    ('triton_fetch', "readJSON('data/triton.json','Triton 数据')"),
    ('json_fetch_options', "fetch(url,{cache:'no-store',signal:controller.signal})"),
    ('json_body_in_read', 'return response.json();'),
    ('json_full_read_timeout', 'await readWithTimeout(reading,label,()=>controller.abort())'),
    ('view_switch',
     "for(const id of ['ubs-view','ubs-repo-view','triton-view','method-view'])"
     "$(id).hidden=id!==(ubs?(repo?'ubs-repo-view':'ubs-view'):domain+'-view');"),
    ('cross_domain_render',
     "if(ubs)render();else if(domain==='triton')renderTritonView();"),
]

INDEX_HTML_CONTRACTS = [
    ('triton_core_script', '<script src="triton-core.js" defer></script>'),
    ('triton_view_script', '<script src="triton-view.js" defer></script>'),
    ('triton_section', '<section id="triton-view" class="view" hidden>'),
]

CONTRACT_GROUPS = {
    'triton-view.js': TRITON_VIEW_CONTRACTS,
    'triton-core.js': TRITON_CORE_CONTRACTS,
    'style.css': STYLE_CONTRACTS,
    'app.js': APP_CONTRACTS,
    'index.html': INDEX_HTML_CONTRACTS,
}


def _check_source_contracts(root):
    """逐文件核对源码契约 needle（文件缺失记为全部缺失）。"""
    missing = []
    checked = 0
    for name, contracts in CONTRACT_GROUPS.items():
        path = root / 'web' / name
        text = path.read_text('utf-8') if path.exists() else ''
        for cid, needle in contracts:
            checked += 1
            if needle not in text:
                missing.append(f'{name}:{cid}')
    return {'checked': checked, 'missing': missing}


def _replay_baseline(root):
    """triton.json 指纹匹配审计冻结 artifact_sha256 时回放浏览器检查基线。"""
    triton_path = root / 'web' / 'data' / 'triton.json'
    triton_sha = (hashlib.sha256(triton_path.read_bytes()).hexdigest()
                  if triton_path.exists() else None)
    audit_path = root / 'audit' / '2026-10-09' / 'evidence' / 'triton-browser.json'
    additional_path = (root / 'audit' / '2026-10-09' / 'evidence'
                       / 'additional-browser.json')
    audit = (json.loads(audit_path.read_text('utf-8'))
             if audit_path.exists() else None)
    additional = (json.loads(additional_path.read_text('utf-8'))
                  if additional_path.exists() else None)
    audit_sha = audit.get('artifact_sha256') if audit else None
    matched = bool(triton_sha and audit_sha and triton_sha == audit_sha)
    result = {'status': 'matched' if matched else 'not_applicable',
              'triton_sha256': triton_sha,
              'audit_artifact_sha256': audit_sha}
    if not matched:
        result['reason'] = ('当前 web/data/triton.json 指纹与审计冻结 '
                            'artifact_sha256 不一致或证据文件缺失，基线回放记 '
                            'not_applicable')
        return result
    by_id = {c['id']: c for c in audit['checks']}

    def entry(cid):
        c = by_id[cid]
        return {'label': c.get('label'), 'actual': c.get('actual'),
                'expected': c.get('expected'),
                'passed': (c.get('state') == 'passed'
                           and c.get('actual') == c.get('expected'))}

    checks = {cid: entry(cid)
              for cid in ('T22', 'T23', 'T24', 'T25', 'T28', 'E01', 'E02',
                          'E03')}
    if additional:
        c = {x['id']: x for x in additional['checks']}['A09']
        checks['A09'] = {'label': c.get('label'), 'actual': c.get('actual'),
                         'expected': c.get('expected'),
                         'passed': (c.get('state') == 'passed'
                                    and c.get('actual') == c.get('expected'))}
    result['checks'] = checks
    result['supporting'] = {cid: entry(cid) for cid in ('T21', 'V-mobile-tip')}
    result['console_errors'] = audit.get('consoleErrors', [])
    result['audit_counts'] = audit.get('counts')
    return result


def _enumerate_views(root):
    """AC01：2N+3 主要视图结构化可达（复用 REQ-047 的独立枚举器）。"""
    index_path = root / 'web' / 'data' / 'repositories.json'
    if not index_path.exists():
        return {'status': 'missing', 'total': None, 'expected_total': None}
    index = json.loads(index_path.read_text('utf-8'))
    entries = index.get('repositories', [])
    snapshots = {}
    for entry in entries:
        snap_path = root / 'web' / 'data' / entry['snapshot']
        snapshots[entry['name']] = (json.loads(snap_path.read_text('utf-8'))
                                    if snap_path.exists() else {})
    views = vur.own_views(index, snapshots)
    per_repo = [v for v in views if v.get('repo')]
    globals_ = [v for v in views if not v.get('repo')]
    per_repo_ok = all(v.get('roundtrip_ok') and v.get('canonical_ok')
                      and v.get('snapshot_attribution_ok') for v in per_repo)
    globals_ok = all(v.get('canonical_ok') for v in globals_)
    return {'status': 'ok', 'total': len(views),
            'expected_total': len(entries) * 2 + 3, 'repos': len(entries),
            'per_repo_views': len(per_repo), 'global_views': len(globals_),
            'per_repo_checks_ok': per_repo_ok, 'global_checks_ok': globals_ok}


def build_report(root):
    problems = []
    node_check = _node_check(root)
    cases = {fn: len(rows) for fn, rows in MATRICES.items()}
    if node_check['status'] != 'ok' or node_check['mismatches']:
        detail = (list(node_check['mismatches'])
                  if node_check['mismatches'] else node_check.get('error'))
        problems.append(f'时间规则矩阵与 triton-core.js 不一致: {detail}')
    contracts = _check_source_contracts(root)
    if contracts['missing']:
        problems.append(f"源码契约缺失: {contracts['missing']}")
    views = _enumerate_views(root)
    if (views.get('status') != 'ok'
            or views.get('total') != views.get('expected_total')
            or not views.get('per_repo_checks_ok')
            or not views.get('global_checks_ok')):
        problems.append(f"主要视图可达性异常: {views}")
    baseline = _replay_baseline(root)
    if baseline['status'] == 'matched':
        failed = [cid for cid, c in baseline['checks'].items()
                  if not c['passed']]
        if failed:
            problems.append(f'审计基线检查未通过: {failed}')
        if baseline['console_errors']:
            problems.append(
                f"审计运行存在页面脚本错误: {baseline['console_errors']}")
    overall = 'verified' if not problems else 'failed'
    return {
        'schema': 'ubs-interaction-evidence/1',
        'generated_at': stamp(),
        'requirement': 'REQ-048',
        'input': {
            'root': str(root),
            'triton_sha256': baseline['triton_sha256'],
            'audit_artifact_sha256': baseline['audit_artifact_sha256'],
            'matches_audit_frozen_input': baseline['status'] == 'matched',
        },
        'time_rules': {
            'cases': cases,
            'total': sum(cases.values()),
            'node_status': node_check['status'],
            'mismatches': node_check['mismatches'],
        },
        'source_contracts': contracts,
        'views': views,
        'baseline': baseline,
        'overall': {'status': overall, 'problems': problems},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='REQ-048 多浏览器与指针触屏操作保持验证')
    parser.add_argument('--root', default='.')
    parser.add_argument('--output',
                        default=str(EVIDENCE_REL / 'interaction-evidence.json'))
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    report = build_report(root)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    time_rules = report['time_rules']
    mismatch_count = sum(len(v) for v in
                         (time_rules['mismatches'] or {}).values())
    print(f"[interaction] node: {time_rules['node_status']}, "
          f"{time_rules['total']} cases, mismatches {mismatch_count}")
    contracts = report['source_contracts']
    print(f"[interaction] contracts: {contracts['checked']} checked, "
          f"missing {len(contracts['missing'])}")
    views = report['views']
    print(f"[interaction] views: {views.get('total')}/"
          f"{views.get('expected_total')} ({views.get('repos')} repos)")
    baseline = report['baseline']
    if baseline['status'] == 'matched':
        failed = [cid for cid, c in baseline['checks'].items()
                  if not c['passed']]
        print(f"[interaction] baseline: matched — "
              f"{len(baseline['checks'])} checks, failed {failed or 0}, "
              f"consoleErrors {len(baseline['console_errors'])}")
    else:
        print(f"[interaction] baseline: {baseline['status']}")
    print(f"[interaction] overall: {report['overall']['status']}")
    for problem in report['overall']['problems']:
        print(f"::error::[interaction] {problem}")
    print(json.dumps({
        'overall_status': report['overall']['status'],
        'cases': time_rules['total'],
        'mismatches': mismatch_count,
        'contracts': contracts['checked'],
        'contracts_missing': len(contracts['missing']),
        'views': views.get('total'),
        'baseline': baseline['status'],
        'matches_audit_frozen_input': report['input'][
            'matches_audit_frozen_input'],
    }, ensure_ascii=False))
    return 0 if report['overall']['status'] == 'verified' else 1


if __name__ == '__main__':
    sys.exit(main())
