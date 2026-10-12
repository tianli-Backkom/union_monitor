#!/usr/bin/env python3
"""REQ-045：UBS 正常详情与下钻能力保持验证。

独立重算详情与下钻语义：每 PR 事件分组（未知关联组与原因文案、全部批次
恰好出现一次）、代表批次默认展开标志、失败等待选择（含取消终态，状态
failure 且 E2E 有限的批次按 E2E 降序、并列编号升序）与跨仓失败等待/最长
E2E 列表排序（E2E 降序、并列创建时间降序）、后续成功不抹去历史失败标志、
UI 分钟显示与精确值（zh-CN 千分位、<0.01、ms/s 单位）公式；与
web/core.js detailGroups/failedWait/sortPRs/metrics 单次 node 调用交叉
核对；锁定 app.js 详情渲染、三类下钻入口与关闭/清理源码契约；指纹匹配
审计冻结输入时回放 U24/U25/U27/U28/U30/U32/U33/A07（交互行为按契约锁定）；
输入更新后基线比对记 not_applicable，交叉核对与契约检查照常执行。
"""
from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_ubs_csv as vcc  # noqa: E402
import verify_ubs_semantics as vsm  # noqa: E402
import verify_ubs_sorting as vso  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_REL = Path('audit/2026-10-09/evidence')
REPORT_NAME = 'ubs-detail-evidence.json'

AUDIT_BASELINE_FINGERPRINT = vsm.AUDIT_BASELINE_FINGERPRINT

SHANGHAI = timezone(timedelta(hours=8))


def stamp():
    return datetime.now(tz=SHANGHAI).isoformat(timespec='seconds')


def own_failed_wait(pr):
    """镜像 core.js failedWait：失败且 E2E 有限非负，E2E 降序、编号升序取首。"""
    candidates = [b for b in pr.get('batches') or []
                  if b.get('status') == 'failure'
                  and isinstance(b.get('e2e_ms'), (int, float))
                  and not isinstance(b.get('e2e_ms'), bool)
                  and math.isfinite(b['e2e_ms']) and b['e2e_ms'] >= 0]
    if not candidates:
        return None
    return sorted(candidates,
                  key=lambda b: (-b['e2e_ms'], b['number']))[0]


def own_later_success(pr, batch):
    """后续成功不抹去历史失败：存在成功批次请求时间晚于失败批次。

    JS 关系比较把 null 按 0 处理，镜像为 ``or 0``。
    """
    return any(x.get('status') == 'success'
               and (x.get('request_ms') or 0) > (batch.get('request_ms') or 0)
               for x in pr.get('batches') or [])


def own_detail_groups(pr):
    """镜像 core.js detailGroups：事件分组 + 未知关联组（含原因文案）。"""
    groups = {}
    for b in pr.get('batches') or []:
        groups.setdefault(b.get('event_id') or '', []).append(b)
    events = {}
    for e in pr.get('events') or []:
        events[e['id']] = e
    seen = set(events)
    out = [{'event': e, 'batches': groups.get(e['id'], []),
            'reason': None} for e in events.values()]
    unmatched = [b for key, bs in groups.items() if key not in seen
                 for b in bs]
    if unmatched:
        empty = sum(1 for b in unmatched if not b.get('event_id'))
        out.append({'event': {'kind': 'unmatched'}, 'batches': unmatched,
                    'reason': (f'{empty} 批 event_id 为空，'
                               f'{len(unmatched) - empty} 批 '
                               f'event_id 不在事件列表')})
    return out


def own_num(n, digits=2):
    """镜像 app.js num()：zh-CN 千分位、固定小数位、空值 '—'。"""
    if n is None:
        return '—'
    return f'{n:,.{digits}f}'


def own_minute(ms):
    """镜像 app.js minute()：分钟两位小数，(0,600)ms 显示 '<0.01'。"""
    if ms is not None and 0 < ms < 600:
        return '<0.01'
    return own_num(None if ms is None else ms / 60000)


def own_exact(ms):
    """镜像 app.js exact()：<1000ms 整数毫秒，否则三位小数秒。"""
    if ms is None:
        return '—'
    if ms < 1000:
        return own_num(ms, 0) + ' ms'
    return own_num(ms / 1000, 3) + ' s'


def own_cross_pairs(index, snapshots):
    """跨仓参与仓库（vsm.participation 镜像 repositoryRows）的 (仓库名, PR)。"""
    pairs = []
    for entry in vsm.participation(index, snapshots):
        if entry['participates']:
            snap = snapshots[entry['name']]
            pairs += [(entry['name'], p)
                      for p in snap.get('prs') or []]
    return pairs


def own_failed_wait_rows(pairs):
    """跨仓失败等待完整序列：E2E 降序、并列创建时间降序（镜像排序）。"""
    rows = []
    for repo, p in pairs:
        b = own_failed_wait(p)
        if b is not None:
            rows.append({'repo': repo, 'pr': p['number'],
                         'trigger': b['number'], 'url': b['url'],
                         'e2e_ms': b['e2e_ms'],
                         'created_ms': p.get('created_ms') or 0,
                         'cancelled': bool(b.get('cancelled')),
                         'later_success': own_later_success(p, b)})
    rows.sort(key=lambda r: (-r['e2e_ms'], -r['created_ms']))
    return rows


def own_exception_rows(pairs):
    """跨仓最长 E2E 完整序列：代表 E2E 降序（空值最后）、并列创建降序。"""
    rows = []
    for repo, p in pairs:
        metrics, _best = vsm.representative(p)
        if metrics['e2e_ms'] is not None:
            rows.append({'repo': repo, 'pr': p['number'],
                         'e2e_ms': metrics['e2e_ms'],
                         'created_ms': p.get('created_ms') or 0,
                         'rep_url': metrics['representative_batch_url']})
    rows.sort(key=lambda r: (-r['e2e_ms'], -r['created_ms']))
    return rows

# ------------------------------------------------------------- node 交叉核对

_NODE_SCRIPT = r"""'use strict';
const fs = require('fs'), path = require('path');
const Metrics = require(process.argv[2]);
const appSrc = fs.readFileSync(process.argv[3], 'utf8');
function extractFn(name) {
  const at = appSrc.indexOf('function ' + name + '(');
  if (at < 0) throw Error('app.js 未找到函数 ' + name);
  let i = appSrc.indexOf('{', at) + 1, depth = 1;
  while (depth > 0) {
    const c = appSrc[i++];
    if (c === '{') depth++;
    else if (c === '}') depth--;
  }
  return appSrc.slice(at, i);
}
const fmt = new Function(
  extractFn('num') + extractFn('minute') + extractFn('exact')
  + ';return {num:num,minute:minute,exact:exact};')();
const payload = JSON.parse(fs.readFileSync(process.argv[4], 'utf8'));
const index = JSON.parse(fs.readFileSync(payload.index_path, 'utf8'));
const snapshots = {};
for (const e of index.repositories) {
  if (!e.snapshot) continue;
  snapshots[e.name] = JSON.parse(
    fs.readFileSync(path.join(payload.snapshot_dir, e.snapshot), 'utf8'));
}
const out = {repos: {}, minute: {}, exact: {},
             fw_sequence: [], exc_sequence: [], cross_max_e2e: null};
for (const e of index.repositories) {
  const snap = snapshots[e.name];
  if (!snap) continue;
  const prs = snap.prs || [], groups = {}, fw = {};
  for (const p of prs) {
    groups[p.number] = Metrics.detailGroups(p).map(g => ({
      event_id: g.event.id ?? null, kind: g.event.kind ?? null,
      batches: g.batches.map(b => b.url), reason: g.reason ?? null}));
    const w = Metrics.failedWait(p);
    fw[p.number] = w ? w.url : null;
  }
  const top = Metrics.sortPRs(prs, 'e2e')[0];
  const m = top ? Metrics.metrics(top.batches) : null;
  out.repos[e.name] = {
    groups, failed_wait: fw,
    max_e2e: top ? {pr: top.number, e2e_ms: m.e2e_ms,
                    rep_url: m.representative_batch_url} : null};
}
const rows = Metrics.repositoryRows(index, snapshots, '');
const repoOf = new Map(), flat = [];
for (const r of rows) for (const p of r.prs) {flat.push(p); repoOf.set(p, r.name);}
const fwRows = [];
for (const p of flat) {
  const w = Metrics.failedWait(p);
  if (w) fwRows.push({repo: repoOf.get(p), pr: p.number, trig: w.number,
                      e2e_ms: w.e2e_ms, created_ms: p.created_ms || 0});
}
fwRows.sort((a, b) => b.e2e_ms - a.e2e_ms
  || (b.created_ms || 0) - (a.created_ms || 0));
out.fw_sequence = fwRows.map(x => ({repo: x.repo, pr: x.pr, trig: x.trig}));
for (const p of Metrics.sortPRs(flat, 'e2e')
     .filter(p => Metrics.metrics(p.batches).e2e_ms != null)) {
  out.exc_sequence.push({repo: repoOf.get(p), pr: p.number,
                         e2e_ms: Metrics.metrics(p.batches).e2e_ms});
}
const crossTop = Metrics.sortPRs(flat, 'e2e')[0];
if (crossTop) {
  const cm = Metrics.metrics(crossTop.batches);
  out.cross_max_e2e = {repo: repoOf.get(crossTop), pr: crossTop.number,
                       e2e_ms: cm.e2e_ms, rep_url: cm.representative_batch_url};
}
payload.minute_samples.forEach((ms, i) => {
  out.minute[String(i)] = fmt.minute(ms);
  out.exact[String(i)] = fmt.exact(ms);
});
fs.writeFileSync(process.argv[5], JSON.stringify(out));
"""


def _node_check(root, minute_samples):
    """单次 node 调用：detailGroups/failedWait/maxE2E、跨仓序列与格式公式。"""
    payload = {
        'index_path': str(root / 'web/data/repositories.json'),
        'snapshot_dir': str(root / 'web/data'),
        'minute_samples': minute_samples,
    }
    with tempfile.TemporaryDirectory() as tmp:
        payload_path = os.path.join(tmp, 'payload.json')
        script_path = os.path.join(tmp, 'check.cjs')
        result_path = os.path.join(tmp, 'result.json')
        with open(payload_path, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False)
        with open(script_path, 'w', encoding='utf-8') as fh:
            fh.write(_NODE_SCRIPT)
        proc = subprocess.run(
            ['node', script_path, str(root / 'web/core.js'),
             str(root / 'web/app.js'), payload_path, result_path],
            capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            return {'status': 'error', 'stderr': proc.stderr[-2000:]}
        with open(result_path, encoding='utf-8') as fh:
            return json.load(fh)


# --------------------------------------------------------------- 源码契约

CORE_CONTRACTS = [
    ('failedWait_filter',
     "filter(b=>b.status==='failure'&&Number.isFinite(b.e2e_ms)&&b.e2e_ms>=0)"),
    ('failedWait_pick',
     '.sort((a,b)=>b.e2e_ms-a.e2e_ms||Number(b.number)-Number(a.number))'
     '[0]||null;'),
    ('detailGroups_key', "const key=b.event_id||''"),
    ('detailGroups_events_map',
     'new Map((pr.events||[]).map(e=>[e.id,e])).values()'),
    ('detailGroups_unmatched_reason',
     '`${empty} 批 event_id 为空，${unmatched.length-empty} 批 '
     'event_id 不在事件列表`'),
    ('detailGroups_unmatched_group',
     "out.push({event:{kind:'unmatched'},batches:unmatched,reason:"),
]

APP_CONTRACTS = [
    ('open_detail_find', 'detailPR=snapshot.prs.find(p=>p.number===n)'),
    ('open_detail_state',
     'detailRepo=currentRepository;detailSnapshot=snapshot;'),
    ('open_detail_metrics_groups', 'detailGroups=Metrics.detailGroups(p),'),
    ('open_detail_full_rerender', "$('detailBody').innerHTML="),
    ('open_detail_show_modal',
     "if(!$('detail').open)$('detail').showModal();"),
    ('unmatched_heading', '`<strong>关联未知/失配</strong><span>'),
    ('unmatched_note', '；批次身份与 Jenkins 链接保留，不伪造事件'),
    ('empty_event_placeholder', '此事件未关联到 trigger，详见数据质量提示'),
    ('rep_expand_flag',
     'bs.map(b=>batchHTML(b,mode(b)))'),
    ('default_expanded_choice',
     'Detail.defaultExpandedBatch(p.batches,{entryId,'
     'representativeUrl:s.representative_batch_url,'
     'representativeNumber:s.representative_batch_number})'),
    ('no_representative_note',
     "data-role=\"no-representative\">该 PR 无代表批次：展示最近采集批次"),
    ('detail_evidence_line',
     'data-role="evidence">${esc(evidence)}'),
    ('batch_details_attrs',
     'data-batch-url="${esc(b.url)}" data-expand-reason="${esc(mode||\'\')}" '
     'class="batch ${cls}" ${open?\'open\':\'\'}>'),
    ('batch_label',
     "mode==='representative'?'用于 PR 效率汇总':mode==='entry'?'选中批次':"
     "mode==='no-representative'?'无代表 · 最近批次':"
     "b.eligible?'有效批次':'未纳入 E2E 统计'"),
    ('batch_context_range',
     '请求：${date(b.request_ms)} → 全批结束：${date(b.end_ms)}'),
    ('batch_e2e_minute', 'E2E ${minute(b.e2e_ms)} min'),
    ('timeline_heads',
     '<span style="text-align:right">排队 min</span>'
     '<span style="text-align:right">执行 min</span>'
     '<span style="text-align:right">总计 min</span>'),
    ('timeline_rail_precise',
     'title="排队 ${exact(j.queue_ms)} / 执行 ${exact(j.duration_ms)}"'),
    ('timeline_queue_precise',
     'title="${exact(j.queue_ms)}">${minute(j.queue_ms)}'),
    ('timeline_duration_precise',
     'title="${exact(j.duration_ms)}">${minute(j.duration_ms)}'),
    ('timeline_total_precise', 'title="${exact(j.total_ms)}"'),
    ('num_fn',
     "function num(n,d=2){return n==null?'—':Number(n)."
     "toLocaleString('zh-CN',{maximumFractionDigits:d,"
     'minimumFractionDigits:d});}'),
    ('minute_fn',
     "function minute(ms){return ms!=null&&ms>0&&ms<600?'<0.01':"
     'num(ms==null?null:ms/60000);}'),
    ('exact_fn',
     "function exact(ms){if(ms==null)return '—';return ms<1000?"
     "num(ms,0)+' ms':num(ms/1000,3)+' s';}"),
    ('exceptions_attrs',
     'data-repo="${esc(repo)}" data-exception="${p.number}"'),
    ('exceptions_onclick',
     "currentRepository=el.dataset.repo;navigate('#ubs/repo/'+"
     'encodeURIComponent(currentRepository));setTimeout(()=>openDetail('
     'Number(el.dataset.exception)),0);'),
    ('failed_wait_sort',
     '.sort((a,b)=>b.b.e2e_ms-a.b.e2e_ms||(b.p.created_ms||0)'
     '-(a.p.created_ms||0))'),
    ('failed_wait_batch_attr', 'data-batch="${esc(b.url)}"'),
    ('failed_wait_cancelled_label', "${b.cancelled?' · 中止/未执行':''}"),
    ('failed_wait_later_success_label',
     "p.batches.some(x=>x.status==='success'&&x.request_ms>"
     "b.request_ms)?' · 后续批次有成功':''"),
    ('failed_wait_onclick',
     'openDetail(Number(el.dataset.pr),el.dataset.batch);'),
    ('quality_drill',
     'if(Number(a.dataset.open))openDetail(Number(a.dataset.open))'),
    ('close_button', "$('closeDetail').onclick=()=>$('detail').close();"),
    ('close_cleanup',
     "addEventListener('close',()=>{if(!$('detail').open){detailPR=null;"
     'detailSnapshot=null;detailRepo=null;detailChoice=null;}});'),
    ('route_context_cleanup',
     "function closeDetailContext(){if($('detail').open)$('detail').close();"
     'detailPR=null;detailRepo=null;detailSnapshot=null;detailChoice=null;}'),
    ('outside_click_close',
     "if(e.target===$('detail')){const r=$('detail')."
     'getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||'
     "e.clientY<r.top||e.clientY>r.bottom)$('detail').close()}"),
    ('route_switch_close',
     "if((detailPR||$('detail').open)&&(domain!=='ubs'||!repo||"
     "currentRepository!==detailRepo))closeDetailContext();"),
    ('max_e2e_fn',
     "function maxE2E(prs){const p=Metrics.sortPRs(prs,'e2e')[0],"
     'm=p&&Metrics.metrics(p.batches);return {p,m};}'),
]


def _check_source_contracts(root):
    app = (root / 'web/app.js').read_text(encoding='utf-8')
    core = (root / 'web/core.js').read_text(encoding='utf-8')
    missing = []
    for name, needle in APP_CONTRACTS:
        if needle not in app:
            missing.append(f'app.js:{name}')
    for name, needle in CORE_CONTRACTS:
        if needle not in core:
            missing.append(f'core.js:{name}')
    return {'checked': len(APP_CONTRACTS) + len(CORE_CONTRACTS),
            'missing': missing}


# ------------------------------------------------------------- 基线回放

def _replay_baseline(index, snapshots, contracts):
    """指纹匹配审计冻结输入时回放 U24/U25/U27/U28/U30/U32/U33/A07。"""
    missing = set(contracts['missing'])
    engine = snapshots['ubs-engine']
    p1600 = next(p for p in engine['prs'] if p['number'] == 1600)
    groups = own_detail_groups(p1600)
    covered = sorted(b['url'] for g in groups for b in g['batches'])
    all_urls = sorted(b['url'] for b in p1600['batches'])
    rep_url = vsm.representative(p1600)[0]['representative_batch_url']
    rep_batch = next((b for b in p1600['batches'] if b['url'] == rep_url),
                     None)
    quality_targets = sorted({
        r[0] for r in vcc.own_quality_rows(engine['prs'], engine['meta'])
        if isinstance(r[0], int)})
    engine_numbers = {p['number'] for p in engine['prs']}
    pairs = own_cross_pairs(index, snapshots)
    fw_top8 = [(r['repo'], r['pr'], r['trigger'])
               for r in own_failed_wait_rows(pairs)[:8]]
    exc_top8 = [(r['repo'], r['pr'])
                for r in own_exception_rows(pairs)[:8]]

    def batch_exists(repo, pr, trig):
        snap = snapshots.get(repo)
        p = (next((x for x in snap['prs'] if x['number'] == pr), None)
             if snap else None)
        return p is not None and any(b['number'] == trig
                                     for b in p['batches'])

    def pr_exists(repo, pr):
        snap = snapshots.get(repo)
        return bool(snap) and any(x['number'] == pr for x in snap['prs'])

    fw_targets_ok = all(batch_exists(*t) for t in fw_top8)
    exc_targets_ok = all(pr_exists(*t) for t in exc_top8)
    checks = {
        'U24_detail_keeps_all_batches': {
            'pr': 1600, 'batches': len(p1600['batches']),
            'groups': len(groups), 'covered_batches': len(covered),
            'expected': {'batches': 5, 'groups': 5},
            'passed': (len(p1600['batches']) == 5 and len(groups) == 5
                       and covered == all_urls)},
        'U25_representative_expanded': {
            'rep_trigger': rep_batch['number'] if rep_batch else None,
            'expected_rep_trigger': 7469,
            'locked_by': 'app.js:rep_expand_flag+batch_details_attrs 源码契约',
            'passed': (rep_batch is not None and rep_batch['number'] == 7469
                       and 'app.js:rep_expand_flag' not in missing
                       and 'app.js:batch_details_attrs' not in missing)},
        'U27_esc_close': {
            'expected': 'Esc 关闭后 dialog.open=false',
            'locked_by': 'app.js:open_detail_show_modal（原生 dialog Esc）'
                         '源码契约',
            'passed': 'app.js:open_detail_show_modal' not in missing},
        'U28_close_button': {
            'expected': '关闭按钮关闭后 dialog.open=false',
            'locked_by': 'app.js:close_button+close_cleanup 源码契约',
            'passed': 'app.js:close_button' not in missing
                      and 'app.js:close_cleanup' not in missing},
        'A07_outside_click_close': {
            'expected': '点击弹窗外部关闭后 dialog.open=false',
            'locked_by': 'app.js:outside_click_close 源码契约',
            'passed': 'app.js:outside_click_close' not in missing},
        'U30_quality_drill': {
            'engine_quality_targets': quality_targets,
            'targets_exist': all(n in engine_numbers
                                 for n in quality_targets),
            'locked_by': 'app.js:quality_drill 源码契约',
            'passed': (all(n in engine_numbers for n in quality_targets)
                       and 'app.js:quality_drill' not in missing)},
        'U32_cross_max_drill': {
            'top': [list(t) for t in exc_top8],
            'expected_top1': ['ubturbo', 442],
            'targets_exist': exc_targets_ok,
            'locked_by': 'app.js:exceptions_attrs+exceptions_onclick 源码契约',
            'passed': (exc_targets_ok
                       and list(exc_top8[0]) == ['ubturbo', 442]
                       and 'app.js:exceptions_onclick' not in missing)},
        'U33_failed_wait_drill': {
            'top': [list(t) for t in fw_top8],
            'expected_top1': ['ubs-engine', 1600, 7469],
            'targets_exist': fw_targets_ok,
            'locked_by': 'app.js:failed_wait_batch_attr+failed_wait_onclick '
                         '源码契约',
            'passed': (fw_targets_ok
                       and list(fw_top8[0]) == ['ubs-engine', 1600, 7469]
                       and 'app.js:failed_wait_onclick' not in missing)},
    }
    ok = all(c['passed'] for c in checks.values())
    return {'status': 'matched' if ok else 'mismatch', 'checks': checks}


# ---------------------------------------------------------------- 报告

def build_report(root):
    index = json.loads((root / 'web/data/repositories.json')
                       .read_text(encoding='utf-8'))
    snapshots = {}
    for entry in index['repositories']:
        if entry.get('snapshot'):
            snapshots[entry['name']] = json.loads(
                (root / 'web/data' / entry['snapshot'])
                .read_text(encoding='utf-8'))

    try:
        fingerprint, _digests, manifest_state, bundle_errors = (
            vsm._bundle_fingerprint(root))
    except Exception as error:  # noqa: BLE001 - 执行错误如实入报告
        fingerprint, manifest_state, bundle_errors = (
            None, f'error: {error!r}', [])
    matches_baseline = fingerprint == AUDIT_BASELINE_FINGERPRINT

    participation = vsm.participation(index, snapshots)
    pairs = own_cross_pairs(index, snapshots)

    group_stats, fw_stats, rep_census = {}, {}, {}
    own_groups_by_repo, own_fw_by_repo, own_max_by_repo = {}, {}, {}
    for name, snap in snapshots.items():
        prs = snap.get('prs') or []
        groups_total = unmatched_prs = unmatched_batches = empty_ids = 0
        coverage_ok = True
        fw_count = cancelled = later = 0
        with_rep = 0
        own_groups, own_fw = {}, {}
        for p in prs:
            gs = own_detail_groups(p)
            own_groups[p['number']] = [
                (g['event'].get('id'), g['event'].get('kind'),
                 [b['url'] for b in g['batches']], g['reason'])
                for g in gs]
            groups_total += len(gs)
            covered = sorted(b['url'] for g in gs for b in g['batches'])
            if covered != sorted(b['url'] for b in p.get('batches') or []):
                coverage_ok = False
            for g in gs:
                if g['event'].get('kind') == 'unmatched':
                    unmatched_prs += 1
                    unmatched_batches += len(g['batches'])
                    empty_ids += sum(1 for b in g['batches']
                                     if not b.get('event_id'))
            b = own_failed_wait(p)
            own_fw[p['number']] = b['url'] if b else None
            if b is not None:
                fw_count += 1
                cancelled += 1 if b.get('cancelled') else 0
                later += 1 if own_later_success(p, b) else 0
            if vsm.representative(p)[0]['representative_batch_url']:
                with_rep += 1
        top = vso.own_sort_prs(prs, 'e2e')[0] if prs else None
        if top is not None:
            metrics = vsm.representative(top)[0]
            own_max_by_repo[name] = {
                'pr': top['number'], 'e2e_ms': metrics['e2e_ms'],
                'rep_url': metrics['representative_batch_url']}
        else:
            own_max_by_repo[name] = None
        own_groups_by_repo[name] = own_groups
        own_fw_by_repo[name] = own_fw
        group_stats[name] = {
            'prs': len(prs), 'groups': groups_total,
            'prs_with_unmatched_group': unmatched_prs,
            'unmatched_batches': unmatched_batches,
            'empty_event_id_batches': empty_ids,
            'coverage_all_batches_ok': coverage_ok}
        fw_stats[name] = {'prs_with_failed_wait': fw_count,
                          'cancelled_batches': cancelled,
                          'later_success_prs': later}
        rep_census[name] = {'prs_with_representative': with_rep}

    fw_rows = own_failed_wait_rows(pairs)
    exc_rows = own_exception_rows(pairs)
    fw_sequence = [(r['repo'], r['pr'], r['trigger']) for r in fw_rows]
    exc_sequence = [(r['repo'], r['pr'], r['e2e_ms']) for r in exc_rows]
    cross_prs = [p for _, p in pairs]
    cross_top = vso.own_sort_prs(cross_prs, 'e2e')[0] if cross_prs else None
    repo_by_id = {id(p): repo for repo, p in pairs}
    if cross_top is not None:
        tm = vsm.representative(cross_top)[0]
        own_cross_max = {'repo': repo_by_id[id(cross_top)],
                         'pr': cross_top['number'],
                         'e2e_ms': tm['e2e_ms'],
                         'rep_url': tm['representative_batch_url']}
    else:
        own_cross_max = None

    fixed_samples = [None, 0, 1, 60, 599, 600, 999, 1000, 61470, 232188,
                     4288049, 11064101, 50640069]
    dynamic = [r['e2e_ms'] for r in fw_rows[:8]]
    dynamic += [m['e2e_ms'] for m in own_max_by_repo.values()
                if m and m['e2e_ms'] is not None]
    if own_cross_max and own_cross_max['e2e_ms'] is not None:
        dynamic.append(own_cross_max['e2e_ms'])
    samples, seen = [], set()
    for value in fixed_samples + dynamic:
        if value not in seen:
            seen.add(value)
            samples.append(value)

    node = _node_check(root, samples)
    problems = []
    group_mismatch, fw_mismatch, max_mismatch = {}, {}, {}
    fw_seq_equal = exc_seq_equal = cross_max_equal = None
    minute_mismatch = {}
    if node.get('status') == 'error':
        problems.append('node 交叉核对执行失败')
    else:
        node_fw_seq = [(r['repo'], r['pr'], r['trig'])
                       for r in node['fw_sequence']]
        fw_seq_equal = node_fw_seq == fw_sequence
        if not fw_seq_equal:
            problems.append('跨仓失败等待序列与 renderFailedWaits 排序不一致')
        node_exc_seq = [(r['repo'], r['pr'], r['e2e_ms'])
                        for r in node['exc_sequence']]
        exc_seq_equal = node_exc_seq == exc_sequence
        if not exc_seq_equal:
            problems.append('跨仓最长 E2E 序列与 renderExceptions 排序不一致')
        cross_max_equal = node['cross_max_e2e'] == own_cross_max
        if not cross_max_equal:
            problems.append('跨仓最长 E2E 与 maxE2E 不一致')
        for name, own_groups in own_groups_by_repo.items():
            node_groups = node['repos'].get(name, {}).get('groups', {})
            diffs = [pr for pr, compact in own_groups.items()
                     if [(g['event_id'], g['kind'], g['batches'], g['reason'])
                         for g in node_groups.get(str(pr), [])] != compact]
            diffs += [int(pr) for pr in node_groups
                      if int(pr) not in own_groups]
            if diffs:
                group_mismatch[name] = sorted(set(diffs))
        if group_mismatch:
            problems.append('事件分组与 core.js detailGroups 不一致')
        for name, own_fw in own_fw_by_repo.items():
            node_fw = node['repos'].get(name, {}).get('failed_wait', {})
            diffs = [pr for pr, url in own_fw.items()
                     if node_fw.get(str(pr)) != url]
            diffs += [int(pr) for pr in node_fw if int(pr) not in own_fw]
            if diffs:
                fw_mismatch[name] = sorted(set(diffs))
        if fw_mismatch:
            problems.append('失败等待批次与 core.js failedWait 不一致')
        for name, own_max in own_max_by_repo.items():
            if node['repos'].get(name, {}).get('max_e2e') != own_max:
                max_mismatch[name] = {
                    'own': own_max,
                    'node': node['repos'].get(name, {}).get('max_e2e')}
        if max_mismatch:
            problems.append('单仓最长 E2E 与 sortPRs/metrics 不一致')
        for i, ms in enumerate(samples):
            if (own_minute(ms) != node['minute'].get(str(i))
                    or own_exact(ms) != node['exact'].get(str(i))):
                minute_mismatch[str(i)] = {
                    'ms': ms, 'own_minute': own_minute(ms),
                    'node_minute': node['minute'].get(str(i)),
                    'own_exact': own_exact(ms),
                    'node_exact': node['exact'].get(str(i))}
        if minute_mismatch:
            problems.append('分钟/精确值格式与 app.js num/minute/exact 不一致')

    if any(not s['coverage_all_batches_ok'] for s in group_stats.values()):
        problems.append('事件分组未恰好覆盖全部批次')

    def batch_exists(repo, pr, trig):
        snap = snapshots.get(repo)
        if snap is None:
            return False
        p = next((x for x in snap.get('prs') or []
                  if x['number'] == pr), None)
        return p is not None and any(b['number'] == trig
                                     for b in p.get('batches') or [])

    def pr_exists(repo, pr):
        snap = snapshots.get(repo)
        return bool(snap) and any(x['number'] == pr
                                  for x in snap.get('prs') or [])

    fw_top8 = [(r['repo'], r['pr'], r['trigger']) for r in fw_rows[:8]]
    exc_top8 = [(r['repo'], r['pr']) for r in exc_rows[:8]]
    fw_targets_ok = all(batch_exists(*t) for t in fw_top8)
    exc_targets_ok = all(pr_exists(*t) for t in exc_top8)
    quality_targets = {}
    for name, snap in snapshots.items():
        numbers = {p['number'] for p in snap['prs']}
        targets = sorted({
            r[0] for r in vcc.own_quality_rows(snap['prs'], snap['meta'])
            if isinstance(r[0], int)})
        quality_targets[name] = {
            'targets': targets,
            'targets_exist': all(n in numbers for n in targets)}
    if not fw_targets_ok:
        problems.append('失败等待下钻目标批次不存在')
    if not exc_targets_ok:
        problems.append('最长 E2E 下钻目标 PR 不存在')
    if any(not v['targets_exist'] for v in quality_targets.values()):
        problems.append('质量记录下钻目标 PR 不存在')

    contracts = _check_source_contracts(root)
    if contracts['missing']:
        problems.append('源码契约缺失: ' + ','.join(contracts['missing']))
    if matches_baseline:
        baseline = _replay_baseline(index, snapshots, contracts)
        if baseline['status'] != 'matched':
            problems.append('审计基线回放不一致')
    else:
        baseline = {
            'status': 'not_applicable',
            'reason': '输入指纹与审计冻结基线不一致，基线比对跳过；'
                      '交叉核对与契约检查照常执行'}

    ok = not problems
    report = {
        'requirement': 'REQ-045',
        'tool': 'scripts/verify_ubs_detail.py',
        'executed_at': stamp(),
        'input': {
            'bundle_fingerprint': fingerprint,
            'matches_audit_frozen_input': matches_baseline,
            'manifest_state': manifest_state,
            'bundle_errors': bundle_errors,
        },
        'participation': participation,
        'detail_groups': {
            'per_repo': group_stats,
            'semantics': '批次按 event_id||空串 分组；事件按 id 去重'
                         '（后写覆盖值、保留首插位置）；失配批次进入'
                         '关联未知/失配组并注明原因，不伪造事件',
            'node_equal': not group_mismatch,
            'mismatches': group_mismatch,
        },
        'representative_expand': {
            'per_repo': rep_census,
            'locked_by': 'app.js:rep_expand_flag+batch_details_attrs 源码契约',
        },
        'failed_wait': {
            'per_repo': fw_stats,
            'cross_total': len(fw_rows),
            'cancelled_total': sum(s['cancelled_batches']
                                   for s in fw_stats.values()),
            'later_success_total': sum(s['later_success_prs']
                                       for s in fw_stats.values()),
            'later_success_rule': '存在成功批次 request_ms 晚于失败批次'
                                  '（JS null 按 0 参与比较）；取消终态'
                                  'status=failure 纳入失败等待',
            'top8': [list(t) for t in fw_top8],
            'node_equal': not fw_mismatch,
            'sequence_node_equal': fw_seq_equal,
        },
        'cross_max_e2e': {
            'value': own_cross_max,
            'node_equal': cross_max_equal,
        },
        'exceptions': {
            'total_valid': len(exc_rows),
            'top8': [list(t) for t in exc_top8],
            'sequence_node_equal': exc_seq_equal,
        },
        'minute_exact': {
            'samples_checked': len(samples),
            'mismatches': minute_mismatch,
            'examples': {str(ms): {'minute': own_minute(ms),
                                   'exact': own_exact(ms)}
                         for ms in samples if ms is not None},
        },
        'drill_targets': {
            'failed_wait_top8_ok': fw_targets_ok,
            'exceptions_top8_ok': exc_targets_ok,
            'quality_per_repo': quality_targets,
        },
        'source_contracts': contracts,
        'baseline': baseline,
        'node_cross_check': {
            'status': 'error' if node.get('status') == 'error' else 'ok',
            'compared': ['detailGroups_per_pr', 'failedWait_per_pr',
                         'max_e2e_per_repo', 'fw_sequence',
                         'exc_sequence', 'cross_max_e2e',
                         'minute_exact_samples'],
        },
        'overall': {'status': 'verified' if ok else 'failed',
                    'problems': problems},
    }
    return report, ok


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='REQ-045 UBS正常详情与下钻能力保持 — 保持验证工具')
    parser.add_argument('--root', default=str(ROOT), help='仓库根目录')
    parser.add_argument('--output', default=None, help='报告输出路径')
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    output = (Path(args.output).resolve() if args.output
              else root / EVIDENCE_REL / REPORT_NAME)
    try:
        report, ok = build_report(root)
    except Exception as error:  # noqa: BLE001 - 执行错误如实入报告
        print(json.dumps({'requirement': 'REQ-045', 'error': repr(error)},
                         ensure_ascii=False))
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                      'utf-8')
    print(json.dumps({
        'overall_status': report['overall']['status'],
        'groups_coverage_ok': all(
            s['coverage_all_batches_ok']
            for s in report['detail_groups']['per_repo'].values()),
        'groups_node_equal': report['detail_groups']['node_equal'],
        'failed_wait_per_repo': {k: v['prs_with_failed_wait']
                                 for k, v in
                                 report['failed_wait']['per_repo'].items()},
        'failed_wait_top8': report['failed_wait']['top8'],
        'exceptions_top8': report['exceptions']['top8'],
        'minute_exact_mismatches':
            len(report['minute_exact']['mismatches']),
        'drill_targets': {
            'failed_wait_top8_ok': report['drill_targets']
            ['failed_wait_top8_ok'],
            'exceptions_top8_ok': report['drill_targets']
            ['exceptions_top8_ok'],
        },
        'contracts': report['source_contracts'],
        'baseline': report['baseline']['status'],
        'matches_audit_frozen_input':
            report['input']['matches_audit_frozen_input'],
        'problems': report['overall']['problems'],
        'report': str(output),
    }, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
