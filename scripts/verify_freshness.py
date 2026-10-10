#!/usr/bin/env python3
"""REQ-049 · 新鲜度与异常/空态表达保持 — 独立验证工具。

镜像 web/triton-core.js 的 freshnessSlots（上海时间、北京时间
08:00/13:00/18:00/20:00 计划槽位含前夜 20:00、90 分钟采集宽限、
每分钟检查由视图层 setInterval 承担），构造含 AC01 精确案例
（旧 08:17 快照在 13:00 槽位宽限结束的 14:30 仍未更新 → 显示延迟；
14:29 尚未越界不提醒）在内的矩阵，与真实 triton-core.js 单次 node
调用逐项核对。锁定 triton-view.js 提醒文案（表达最后一次成功采集
结果与应检查 Actions，不说成已证实的采集失败）、60 秒定时器与
销毁清理、各类空态（暂无数据/无匹配批次/选区无有效样本/NPU 明细
缺失不计入且不代表没有排队）、导出失败具体提示与 finally 恢复按钮、
采集时间与数据窗口分别显示、sameSessionMount 跨域返回不重挂载，
app.js 加载/读取失败/格式无效/HTTP 状态错误空态与 reloadGate 旧
响应防护，triton-core.js 槽位/宽限/严格比较公式与 index.html 挂载
点共 36 条源码契约。web/data/triton.json 指纹与审计冻结
artifact_sha256 一致时回放 M04（新鲜度延迟提醒按实际检查时刻显示）、
A04（导出失败明确且按钮恢复 error/enabled）、F02-triton-404
（异常提供明确空态）；输入更新后基线记 not_applicable，矩阵与
契约检查照常。
"""
import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

EVIDENCE_REL = Path('audit/2026-10-09/evidence')


def stamp():
    return datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def _utc_ms(year, month, day, hour, minute=0, second=0):
    """UTC 时刻 → 毫秒纪元（北京时间 = UTC+8，由调用方换算）。"""
    return int(datetime(year, month, day, hour, minute, second,
                        tzinfo=timezone.utc).timestamp() * 1000)


# ---- triton-core.js freshnessSlots 镜像 ----

def _bj_day_start(t):
    """JS: bj = new Date(t + 8h); day = Date.UTC(bj 的 UTC 年/月/日)。

    即北京时间当日零点对应的（位移坐标系）纪元值；整数下取整与
    JS Date.UTC 对齐。"""
    bj_ms = t + 8 * 3600000
    return (bj_ms // 86400000) * 86400000


def own_freshness_slots(now, collected_at):
    """北京时间槽位（含前夜 20:00）+ 90 分钟宽限 + 严格比较判定延迟。"""
    t = now  # 矩阵传数值，+new Date 数值恒等
    collected = None if collected_at is None else collected_at
    day = _bj_day_start(t)
    slots = [day + (hours - 8) * 3600000
             for hours in (-4, 8, 13, 18, 20)]
    slots = [slot for slot in slots if slot + 90 * 60000 <= t]
    latest = max(slots) if slots else None
    stale = (latest is not None and collected is not None
             and collected < latest)
    return {'slots': slots, 'latest': latest, 'stale': stale}


# ---- 矩阵案例：AC01 精确案例 + 槽位/宽限边界 + 日期翻转 ----
# 日期取 2026-10-09（北京时间），UTC = 北京时间 − 8 小时。

FRESHNESS_MATRIX = [
    # AC01：13:00 槽位宽限恰在 14:30 结束，旧 08:17 快照 → 延迟
    [_utc_ms(2026, 10, 9, 6, 30), _utc_ms(2026, 10, 9, 0, 17)],
    # 14:29 尚未越过宽限，最新槽位仍是 08:00，08:17 快照不延迟
    [_utc_ms(2026, 10, 9, 6, 29), _utc_ms(2026, 10, 9, 0, 17)],
    # 14:30:59 已越界 → 延迟
    [_utc_ms(2026, 10, 9, 6, 30, 59), _utc_ms(2026, 10, 9, 0, 17)],
    # 采集恰好落在最新槽位上：严格小于才延迟
    [_utc_ms(2026, 10, 9, 6, 30), _utc_ms(2026, 10, 9, 5, 0)],
    # 采集晚于最新槽位（13:30）→ 不延迟
    [_utc_ms(2026, 10, 9, 6, 30), _utc_ms(2026, 10, 9, 5, 30)],
    # 采集时间缺失 → 不判定延迟
    [_utc_ms(2026, 10, 9, 6, 30), None],
    # 凌晨 03:00：最新槽位为前夜 20:00；20:17 快照不延迟
    [_utc_ms(2026, 10, 8, 19, 0), _utc_ms(2026, 10, 8, 12, 17)],
    # 凌晨 03:00：19:00 快照早于前夜 20:00 槽位 → 延迟
    [_utc_ms(2026, 10, 8, 19, 0), _utc_ms(2026, 10, 8, 11, 0)],
    # 09:29 仍是前夜 20:00；09:30 起最新槽位为 08:00
    [_utc_ms(2026, 10, 9, 1, 29), _utc_ms(2026, 10, 9, 0, 17)],
    [_utc_ms(2026, 10, 9, 1, 30), _utc_ms(2026, 10, 9, 0, 17)],
    # 21:29 仍是 18:00；21:30 起为 20:00
    [_utc_ms(2026, 10, 9, 13, 29), _utc_ms(2026, 10, 9, 10, 17)],
    [_utc_ms(2026, 10, 9, 13, 30), _utc_ms(2026, 10, 9, 10, 17)],
    # 北京时间零点翻转：最新槽位为前夜 20:00
    [_utc_ms(2026, 10, 9, 16, 0), _utc_ms(2026, 10, 9, 12, 17)],
    [_utc_ms(2026, 10, 9, 16, 0), _utc_ms(2026, 10, 9, 11, 30)],
    # 恰在 08:00 槽位时刻：宽限未过，最新槽位仍是前夜 20:00
    [_utc_ms(2026, 10, 9, 0, 0), _utc_ms(2026, 10, 8, 12, 17)],
    # 次日 10:00：跨日后最新槽位为当日 08:00，昨日 08:17 快照延迟
    [_utc_ms(2026, 10, 10, 2, 0), _utc_ms(2026, 10, 9, 0, 17)],
    # 12:59：13:00 槽位宽限未到，最新槽位仍 08:00
    [_utc_ms(2026, 10, 9, 4, 59), _utc_ms(2026, 10, 9, 0, 17)],
]

MATRICES = {'freshnessSlots': FRESHNESS_MATRIX}


# ---- 与真实 triton-core.js 的单次 node 调用逐项核对 ----

_NODE_SCRIPT = r"""
const fs = require('fs');
const path = require('path');
const core = require(path.resolve(process.argv[2]));
const payload = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const out = {};
out.freshnessSlots = payload.freshnessSlots.map(a => core.freshnessSlots(a[0], a[1]));
fs.writeFileSync(process.argv[4], JSON.stringify(out));
"""


def _node_check(root):
    """node 载入真实 triton-core.js，对槽位矩阵求值并与镜像比对。"""
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
        own_values = [own_freshness_slots(row[0], row[1]) for row in rows]
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


# ---- 源码契约：新鲜度与异常/空态表达的静态锁定 ----

TRITON_VIEW_CONTRACTS = [
    ('freshness_slots_call', 'core.freshnessSlots(Date.now(), D.collected_at)'),
    ('freshness_notice_text',
     '数据更新已延迟：当前展示最后一次成功采集结果，请检查 GitHub Actions。'),
    ('freshness_notice_role',
     '<div class="notice" data-role="freshness" role="status" hidden></div>'),
    ('window_notice_role',
     '<div class="notice" data-role="windowNotice" role="status" hidden>'
     '</div>'),
    ('freshness_interval', 'const freshTimer = setInterval(updateFreshness,'
     ' 60000);'),
    ('destroy_fresh_timer', 'clearInterval(freshTimer);'),
    ('destroy_doc_listener', "document.removeEventListener('click',"
     ' onDocClick);'),
    ('same_session_mount',
     'if (core.sameSessionMount(mounted, payload, container)) {'),
    ('empty_no_data',
     "container.innerHTML = '<div class=\"empty\">暂无 Triton 门禁数据"
     "</div>';"),
    ('empty_no_batches_note',
     "priorityNoteEl.textContent = '当前分支与时间范围内没有批次。';"),
    ('empty_no_batches',
     '当前合入分支与时间范围内没有批次，请调整分支筛选或扩大时间范围。'),
    ('empty_e2e_samples', '当前选区暂无已完成的有效样本'),
    ('empty_npu_samples', '当前选区暂无有效的 NPU 排队样本'),
    ('npu_missing_notice',
     '个批次的 NPU 明细缺失或时间戳异常，未计入统计；缺失不代表没有排队。'),
    ('export_saving', "notice.textContent = '正在保存 CSV…';"),
    ('export_error_text',
     "notice.textContent = '导出失败：' + (err && err.message ? err.message"
     ' : err);'),
    ('export_disable', 'exportBtn.disabled = true;'),
    ('export_recover',
     '      } finally {\n        exportBtn.disabled = false;\n      }'),
    ('footer_collected_at', '采集于 ${fmtDate(D.collected_at)}'),
    ('window_span_note', '内有提交批次'),
    ('selected_range',
     'selectedRangeEl.textContent = `${fmtDate(viewStart)} — '
     '${fmtDate(viewEnd)}`;'),
]

APP_CONTRACTS = [
    ('reload_failed_notice', 'Triton 数据重新读取失败：'),
    ('reload_keep_last', '当前仍显示上一次成功读取的数据'),
    ('fetch_failed_empty', 'Triton 数据读取失败：'),
    ('ubs_unaffected', 'UBS 数据不受影响'),
    ('loading_state', '正在读取 Triton 数据…'),
    ('no_data_state', '暂无 Triton 数据'),
    ('http_error', "throw Error('HTTP '+r.status)"),
    ('payload_invalid', "throw Error('Triton 数据格式无效')"),
    ('stale_guard', 'reloadGate.isCurrent(gen)'),
    ('fetch_no_store', "fetch('data/triton.json',{cache:'no-store'})"),
]

CORE_CONTRACTS = [
    ('slots_hours', '[-4, 8, 13, 18, 20]'),
    ('grace_90', 'slot + 90 * 60000 <= t'),
    ('stale_strict',
     'const stale = latest != null && collected != null && collected'
     ' < latest;'),
    ('bj_shift', 'const bj = new Date(t + 8 * 3600000);'),
]

INDEX_HTML_CONTRACTS = [
    ('triton_section', '<section id="triton-view" class="view" hidden>'),
]

CONTRACT_GROUPS = {
    'triton-view.js': TRITON_VIEW_CONTRACTS,
    'app.js': APP_CONTRACTS,
    'triton-core.js': CORE_CONTRACTS,
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
    """triton.json 指纹匹配审计冻结 artifact_sha256 时回放三项检查基线。"""
    triton_path = root / 'web' / 'data' / 'triton.json'
    triton_sha = (hashlib.sha256(triton_path.read_bytes()).hexdigest()
                  if triton_path.exists() else None)
    evidence_dir = root / 'audit' / '2026-10-09' / 'evidence'
    audit_path = evidence_dir / 'triton-browser.json'
    additional_path = evidence_dir / 'additional-browser.json'
    visual_path = evidence_dir / 'visual-review.json'
    audit = (json.loads(audit_path.read_text('utf-8'))
             if audit_path.exists() else None)
    additional = (json.loads(additional_path.read_text('utf-8'))
                  if additional_path.exists() else None)
    visual = (json.loads(visual_path.read_text('utf-8'))
              if visual_path.exists() else None)
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
    f02 = by_id['F02-triton-404']
    checks = {
        'F02-triton-404': {
            'label': f02.get('label'), 'actual': f02.get('actual'),
            'expected': f02.get('expected'),
            'passed': (f02.get('state') == 'passed'
                       and f02.get('actual') == f02.get('expected')),
        },
    }
    if additional:
        a04 = {c['id']: c for c in additional['checks']}['A04']
        checks['A04'] = {
            'label': a04.get('label'), 'actual': a04.get('actual'),
            'expected': a04.get('expected'),
            'passed': (a04.get('state') == 'passed'
                       and a04.get('actual') == a04.get('expected')),
        }
    if visual:
        m04 = {c['id']: c for c in visual['checks']}['M04']
        checks['M04'] = {
            'label': m04.get('label'), 'actual': m04.get('actual'),
            'expected': m04.get('expected'),
            # M04 的 actual 为审查叙述（按实际检查时刻显示），由审计员
            # 判定 passed；回放断言 state=passed 并保留原文。
            'passed': m04.get('state') == 'passed',
        }
    result['checks'] = checks
    return result


def build_report(root):
    problems = []
    node_check = _node_check(root)
    cases = {fn: len(rows) for fn, rows in MATRICES.items()}
    if node_check['status'] != 'ok' or node_check['mismatches']:
        detail = (list(node_check['mismatches'])
                  if node_check['mismatches'] else node_check.get('error'))
        problems.append(f'新鲜度槽位矩阵与 triton-core.js 不一致: {detail}')
    contracts = _check_source_contracts(root)
    if contracts['missing']:
        problems.append(f"源码契约缺失: {contracts['missing']}")
    baseline = _replay_baseline(root)
    if baseline['status'] == 'matched':
        failed = [cid for cid, c in baseline['checks'].items()
                  if not c['passed']]
        if failed:
            problems.append(f'审计基线检查未通过: {failed}')
    overall = 'verified' if not problems else 'failed'
    return {
        'schema': 'ubs-freshness-evidence/1',
        'generated_at': stamp(),
        'requirement': 'REQ-049',
        'input': {
            'root': str(root),
            'triton_sha256': baseline['triton_sha256'],
            'audit_artifact_sha256': baseline['audit_artifact_sha256'],
            'matches_audit_frozen_input': baseline['status'] == 'matched',
        },
        'freshness_slots': {
            'cases': cases,
            'total': sum(cases.values()),
            'node_status': node_check['status'],
            'mismatches': node_check['mismatches'],
        },
        'source_contracts': contracts,
        'baseline': baseline,
        'overall': {'status': overall, 'problems': problems},
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='REQ-049 新鲜度与异常/空态表达保持验证')
    parser.add_argument('--root', default='.')
    parser.add_argument('--output',
                        default=str(EVIDENCE_REL / 'freshness-evidence.json'))
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    report = build_report(root)
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    slots = report['freshness_slots']
    mismatch_count = sum(len(v) for v in
                         (slots['mismatches'] or {}).values())
    print(f"[freshness] node: {slots['node_status']}, "
          f"{slots['total']} cases, mismatches {mismatch_count}")
    contracts = report['source_contracts']
    print(f"[freshness] contracts: {contracts['checked']} checked, "
          f"missing {len(contracts['missing'])}")
    baseline = report['baseline']
    if baseline['status'] == 'matched':
        failed = [cid for cid, c in baseline['checks'].items()
                  if not c['passed']]
        print(f"[freshness] baseline: matched — "
              f"{len(baseline['checks'])} checks, failed {failed or 0}")
    else:
        print(f"[freshness] baseline: {baseline['status']}")
    print(f"[freshness] overall: {report['overall']['status']}")
    for problem in report['overall']['problems']:
        print(f"::error::[freshness] {problem}")
    print(json.dumps({
        'overall_status': report['overall']['status'],
        'cases': slots['total'],
        'mismatches': mismatch_count,
        'contracts': contracts['checked'],
        'contracts_missing': len(contracts['missing']),
        'baseline': baseline['status'],
        'matches_audit_frozen_input': report['input'][
            'matches_audit_frozen_input'],
    }, ensure_ascii=False))
    return 0 if report['overall']['status'] == 'verified' else 1


if __name__ == '__main__':
    sys.exit(main())
