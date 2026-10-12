#!/usr/bin/env python3
"""REQ-044：UBS 四类 CSV 内容与格式保持验证。

独立重算仓库汇总 / PR / 批次 / 质量四类 CSV 的表头、行构造与文本序列化：
PR 导出为完整筛选集（不受 15 行分页限制）、批次导出覆盖全部批次 × 全部子任务
（无子任务批次占位一行）、质量导出跟随当前筛选。文本序列化（BOM、公式前缀
转义、引号倍增、CRLF）与 web/core.js csv() 单次 node 调用逐字节核对；
仓库汇总行与 repositoryRows、PR 导出排序与 filterPRs/sortPRs 交叉核对；
批次 eligible 字段与独立重算互证；锁定 app.js/core.js 导出布局、毫秒单位、
文件名与失败提示源码契约；本地保存与 Pages Blob 下载共用同一 content。
输入指纹与审计冻结基线一致时回放 U21/U23/U26/U29/U31/U38/A11；
输入更新后基线比对记 not_applicable，交叉核对与契约检查照常执行。
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_ubs_filtering as vuf  # noqa: E402
import verify_ubs_semantics as vsm  # noqa: E402
import verify_ubs_sorting as vso  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_REL = Path('audit/2026-10-09/evidence')
REPORT_NAME = 'ubs-csv-evidence.json'

AUDIT_BASELINE_FINGERPRINT = vsm.AUDIT_BASELINE_FINGERPRINT
REPOS = ('ubs-engine', 'ubs-comm', 'ubs-virt', 'ubs-io', 'ubs-mem',
         'OmniStateStore', 'ham', 'ubturbo', 'ubs-atomic')

STATE_NAME = {'open': '开启中', 'merged': '已合入', 'closed': '已关闭未合入'}
RESULT_NAME = {'success': '成功', 'failure': '失败', 'running': '执行中',
               'incomplete': '数据不完整'}
KIND_NAME = {'create': '创建 PR', 'push': '推送提交', 'retest': '重跑请求',
             'unknown': '请求未关联', 'note': '评论触发', 'merge_request': 'PR 事件'}
FORMULA_CHARS = frozenset('=+-@\t\r')
SHANGHAI = timezone(timedelta(hours=8))

PR_HEADS = (['仓库', 'PR', '标题', '状态', '作者', '创建时间', '合入时间', '提交次数',
             '全部批次数', '创建请求数', '推送请求数', '重跑请求数', '代表trigger编号',
             '代表trigger链接', 'E2E ms']
            + [f'{k}{f}ms' for k in ('x86', 'ARM', 'DT')
               for f in ('排队', '执行', '总计')])
REPO_HEADS = (['仓库', '采集状态', '纳入跨仓汇总', '采集时间', 'PR数', '开启', '合入',
               '关闭', '有效代表PR数', '覆盖率', 'E2E平均ms', 'E2EP90ms',
               'E2E有效PR数']
              + [f'{k}{f}' for k in ('x86', 'ARM', 'DT')
                 for f in ('总耗时平均ms', '总耗时P90ms', '有效PR数')])
BATCH_HEADS = ['仓库', 'PR', 'trigger', 'E2E结果', '触发类型', 'SHA', '请求时间',
               'E2E ms', 'Jenkins ms', '有效E2E批次', '用于PR效率汇总', '子任务',
               '子任务结果', '排队ms', '执行ms', '总计ms', '数据问题']
QUALITY_HEADS = ['仓库', 'PR', '批次', '原因']

# 覆盖中文、逗号、引号、换行、全部公式前缀（= + - @ 制表符 回车）、
# 空值、布尔、数字、撇号转义与混合文本（U38/A11 语义）。
NASTY_MATRIX = [
    ['中文标题', '带,逗号', '带"引号', '带\n换行', '=SUM(A1)', '+1024', '-42',
     '@cmd', '\tTab', '\r回车'],
    [None, '', 0, 4288049, 2710318.4, True, False, "'已转义",
     '混合"中文,\n=公式', '—'],
    ['=中文,"带换行\n标题'],
]


def stamp():
    return datetime.now(tz=SHANGHAI).isoformat(timespec='seconds')


def own_csv(rows):
    """镜像 web/core.js csv()：BOM + 公式前缀转义 + 引号倍增 + CRLF。"""

    def js_string(x):
        # JS String(x)：整值浮点不带 .0（232188.0 → '232188'）
        if (isinstance(x, float) and x.is_integer() and abs(x) < 1e21):
            return str(int(x))
        return str(x)

    def cell(x):
        if isinstance(x, bool):
            s = 'true' if x else 'false'
        elif x is None:
            s = ''
        else:
            s = js_string(x)
        if s and s[0] in FORMULA_CHARS:
            s = "'" + s
        return '"' + s.replace('"', '""') + '"'

    return ('\ufeff'
            + '\r\n'.join(','.join(cell(x) for x in row) for row in rows))


def own_parse(text):
    """RFC4180 解析 own_csv 产物；公式转义撇号按审计口径保留。"""
    if text.startswith('\ufeff'):
        text = text[1:]
    rows, row, cell, i, quoted = [], [], [], 0, False
    while i < len(text):
        ch = text[i]
        if quoted:
            if ch == '"':
                if i + 1 < len(text) and text[i + 1] == '"':
                    cell.append('"')
                    i += 2
                else:
                    quoted = False
                    i += 1
            else:
                cell.append(ch)
                i += 1
        elif ch == '"':
            quoted = True
            i += 1
        elif ch == ',':
            row.append(''.join(cell))
            cell = []
            i += 1
        elif ch in '\r\n':
            i += 2 if (ch == '\r' and i + 1 < len(text)
                       and text[i + 1] == '\n') else 1
            row.append(''.join(cell))
            cell = []
            rows.append(row)
            row = []
        else:
            cell.append(ch)
            i += 1
    if row or cell:
        row.append(''.join(cell))
        rows.append(row)
    return rows


def own_date(ms):
    """镜像 app.js date()：空值 '—'；sv-SE 上海时区完整时间。"""
    if not ms:
        return '—'
    return datetime.fromtimestamp(int(ms) / 1000, tz=SHANGHAI).strftime(
        '%Y-%m-%d %H:%M:%S')


def own_repository_state(entry, snap, index):
    """镜像 app.js repositoryState() 采集状态文案。"""
    if not snap:
        return ('未获取数据 · 采集失败' if entry['status'] == 'failed'
                else '未获取数据 · 待采集')
    if (snap['meta']['start_ms'] != index['start_ms']
            or snap['meta']['end_ms'] != index['end_ms']):
        return '过期快照 · 不计跨仓汇总'
    return {'success': '采集完成', 'partial': '部分采集 · 需关注',
            'failed': '采集失败 · 保留快照',
            'pending': '待采集'}.get(entry['status'], entry['status'])


def own_repo_csv_rows(index, snapshots):
    """独立重算仓库汇总 CSV 行（默认跨仓视图：state=''、P90 降序）。"""
    names, rows = [], []
    for entry in index['repositories']:
        snap = snapshots.get(entry['name'])
        included = bool(
            snap and snap['meta']['start_ms'] == index['start_ms']
            and snap['meta']['end_ms'] == index['end_ms']
            and entry['status'] in ('success', 'partial'))
        prs = vuf.own_filter(snap['prs'], state='') if included else []
        counts = {k: sum(1 for p in prs if p['state'] == k)
                  for k in ('open', 'merged', 'closed')}
        metrics = vsm.aggregate([vsm.representative(p)[0] for p in prs])
        row = [entry['repository'],
               own_repository_state(entry, snap, index),
               included,
               snap['meta'].get('collected_at') if snap else None,
               len(prs) if included else None,
               *(counts[k] if included else None
                 for k in ('open', 'merged', 'closed')),
               metrics['e2e']['n'],
               metrics['e2e']['n'] / len(prs) if included and prs else None,
               metrics['e2e']['mean'], metrics['e2e']['p90'],
               metrics['e2e']['n']]
        for kind in ('x86', 'arm', 'dt'):
            row += [metrics[kind]['total']['mean'],
                    metrics[kind]['total']['p90'],
                    metrics[kind]['total']['n']]
        names.append(entry['name'])
        rows.append(row)
    order = sorted(range(len(rows)),
                   key=lambda i: (rows[i][11] if rows[i][11] is not None
                                  else -1),
                   reverse=True)
    return [rows[i] for i in order], [names[i] for i in order]


def own_pr_csv_rows(snap, state='', query='', quality='', trigger='',
                    sort='e2e'):
    """独立重算 PR 导出 CSV：完整筛选集（不受 15 行分页限制），当前排序。"""
    prs = vuf.own_filter(snap['prs'], state=state, query=query,
                         quality=quality, trigger=trigger)
    prs = vso.own_sort_prs(prs, sort)
    rows = []
    for p in prs:
        metrics, _best = vsm.representative(p)
        tc = vuf.own_trigger_counts(p)
        row = [snap['meta']['repository'], p['number'], p.get('title'),
               STATE_NAME.get(p['state']), p.get('author'),
               own_date(p.get('created_ms')), own_date(p.get('merged_ms')),
               p.get('submission_count'), len(p['batches']),
               tc['create'], tc['push'], tc['retest'],
               metrics['representative_batch_number'],
               metrics['representative_batch_url'], metrics['e2e_ms']]
        for kind in ('x86', 'arm', 'dt'):
            for field in ('queue', 'duration', 'total'):
                row.append(metrics[kind][f'{field}_ms'])
        rows.append(row)
    return rows


def own_batch_csv_rows(snap, pr):
    """独立重算批次导出 CSV：全部批次 × 全部子任务（无子任务批次占位一行）。"""
    metrics, _best = vsm.representative(pr)
    rep_url = metrics['representative_batch_url']
    rows = []
    for b in pr['batches']:
        kind = b.get('event_type')
        for j in (b['children'] if b.get('children') else [{}]):
            rows.append([snap['meta']['repository'], pr['number'], b['url'],
                         RESULT_NAME.get(b.get('status')),
                         KIND_NAME.get(kind) or kind,
                         b.get('sha'), own_date(b.get('request_ms')),
                         b.get('e2e_ms'), b.get('jenkins_ms'),
                         b.get('eligible'), b['url'] == rep_url,
                         j.get('url'), j.get('result'), j.get('queue_ms'),
                         j.get('duration_ms'), j.get('total_ms'),
                         '; '.join(b.get('issues') or [])])
    return rows


def own_quality_rows(prs, meta):
    """镜像 app.js qualityRows()：PR/批次问题、运行中批次与采集错误。"""
    rows = []
    for p in prs:
        for reason in p.get('issues') or []:
            rows.append([p['number'], 'PR', reason])
        for b in p['batches']:
            for reason in b.get('issues') or []:
                rows.append([p['number'], f"#{b['number']}", reason])
            if b['status'] == 'running':
                rows.append([p['number'], f"#{b['number']}",
                             '仍在执行：排除主要耗时统计'])
    for e in meta.get('errors') or []:
        rows.append(['采集', e.get('source'), e.get('reason')])
    return rows

APP_CONTRACTS = (
    ('pr_heads', "const heads=['仓库','PR','标题','状态','作者','创建时间','合入时间','提交次数','全部批次数','创建请求数','推送请求数','重跑请求数','代表trigger编号','代表trigger链接','E2E ms']"),
    ('pr_ms_heads', "for(const k of ['x86','ARM','DT'])for(const f of ['排队','执行','总计'])heads.push(`${k}${f}ms`)"),
    ('pr_full_filter_set', 'const rows=filtered.map(p=>{const s=Metrics.metrics(p.batches)'),
    ('pr_filename', "download([heads,...rows],currentRepository+'-pr-summary.csv',versionedMeta('L 记录（PR）','当前筛选 PR',filtered.length,'分钟'))"),
    ('repo_heads', "const heads=['仓库','采集状态','纳入跨仓汇总','采集时间','PR数','开启','合入','关闭','有效代表PR数','覆盖率','E2E平均ms','E2EP90ms','E2E有效PR数']"),
    ('repo_ms_heads', "for(const k of ['x86','ARM','DT'])heads.push(k+'总耗时平均ms',k+'总耗时P90ms',k+'有效PR数')"),
    ('repo_source', 'const rows=crossRows().map(r=>{'),
    ('repo_filename', "download([heads,...rows],'repositories-summary.csv',versionedMeta('S 分析汇总','九仓跨仓汇总',rows.length,'分钟'))"),
    ('batch_heads', "const rows=[['仓库','PR','trigger','E2E结果','触发类型','SHA','请求时间','E2E ms','Jenkins ms','有效E2E批次','用于PR效率汇总','子任务','子任务结果','排队ms','执行ms','总计ms','数据问题']]"),
    ('batch_task_expansion', 'for(const j of b.children.length?b.children:[{}])'),
    ('batch_representative_flag', 'b.url===Metrics.metrics(detailPR.batches).representative_batch_url'),
    ('batch_issues_join', "(b.issues||[]).join('; ')"),
    ('batch_guard_notice', '无法导出批次：当前没有打开有效的 PR 详情。'),
    ('batch_filename', 'download(rows,`${detailRepo}-pr-${detailPR.number}-batches.csv`,versionedMeta(\'PR 全部批次\',\'PR #\'+detailPR.number+\' 全部已采集批次\',detailPR.batches.length,\'分钟\'))'),
    ('quality_heads_and_prefix', "const rows=[['仓库','PR','批次','原因']]"),
    ('quality_dedupe', "QueryState.dedupeConcerns(concerns,c=>c.batch_id,c=>[c.reason])"),
    ('quality_dedupe_reasons', "entry.reasons.join('; ')"),
    ('quality_filename', "currentRepository+'-concerns.csv'"),
    ('quality_pr_issues', "for(const reason of p.issues||[])rows.push([p.number,'PR',reason])"),
    ('quality_running_rule', "if(b.status==='running')rows.push([p.number,'#'+b.number,'仍在执行：排除主要耗时统计'])"),
    ('quality_collect_errors', "for(const e of snapshot.meta.errors||[])rows.push(['采集',e.source,e.reason])"),
    ('notice_saving', "notice.textContent='正在保存 CSV…'"),
    ('notice_failure', "notice.innerHTML='导出失败：'+esc(e.message)+' <button type=\"button\" data-role=\"retry-export\">重试</button>'"),
    ('notice_retry', "btn.onclick=()=>download(rows,name,meta)"),
    ('notice_role_status', "setAttribute('role','status')"),
    ('date_shanghai', "toLocaleString('sv-SE',{timeZone:'Asia/Shanghai'"),
)

CORE_CONTRACTS = (
    ('csv_bom', "'\\ufeff'+rows.map"),
    ('csv_formula_escape', '/^[=+\\-@\\t\\r]/.test(s)'),
    ('csv_escape_quote', 's="\'"+s'),
    ('csv_quote_doubling', '.replaceAll(\'"\',\'""\')'),
    ('csv_crlf', ".join('\\r\\n')"),
    ('csv_null_empty', "x==null?'':String(x)"),
    ('save_single_content', 'const content=csv(rows)'),
    ('save_local_hosts', "['localhost','127.0.0.1','::1'].includes(host)"),
    ('save_local_post', 'body:JSON.stringify({name,csv:content})'),
    ('save_blob_same_content', "new env.Blob([content],{type:'text/csv;charset=utf-8'})"),
)

_NODE_SCRIPT = r"""
const fs = require('fs');
const payload = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const Metrics = require(process.argv[3]);
const out = {nasty_csv: Metrics.csv(payload.nasty), row_sets: {}, dates: {}};
for (const key of Object.keys(payload.row_sets))
  out.row_sets[key] = Metrics.csv(payload.row_sets[key]);
for (const ms of payload.date_samples)
  out.dates[String(ms)] = new Date(ms).toLocaleString('sv-SE', {
    timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit',
    day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit'});
const rc = payload.repository_check;
if (rc) {
  const index = JSON.parse(fs.readFileSync(rc.index_path, 'utf8'));
  const snapshots = {};
  for (const e of index.repositories)
    if (e.snapshot)
      snapshots[e.name] = JSON.parse(
        fs.readFileSync(rc.snapshot_dir + '/' + e.snapshot, 'utf8'));
  const rows = Metrics.repositoryRows(index, snapshots, '');
  out.repo_values = {};
  for (const r of rows)
    out.repo_values[r.name] = {
      repository: r.repository, included: r.included, prs: r.prs.length,
      counts: r.counts,
      e2e: [r.metrics.e2e.n, r.metrics.e2e.mean, r.metrics.e2e.p90],
      x86: [r.metrics.x86.total.mean, r.metrics.x86.total.p90, r.metrics.x86.total.n],
      arm: [r.metrics.arm.total.mean, r.metrics.arm.total.p90, r.metrics.arm.total.n],
      dt: [r.metrics.dt.total.mean, r.metrics.dt.total.p90, r.metrics.dt.total.n]};
  const engine = snapshots[rc.engine];
  if (engine) {
    out.engine_default_seq = Metrics.sortPRs(
      Metrics.filterPRs(engine.prs, {state: ''}), 'e2e').map(p => p.number);
    out.engine_merged_seq = Metrics.sortPRs(
      Metrics.filterPRs(engine.prs, {state: 'merged'}), 'e2e').map(p => p.number);
  }
}
fs.writeFileSync(process.argv[4], JSON.stringify(out));
"""


def _node_check(root, row_sets, date_samples):
    """单次 node 调用：csv 序列化逐字节、Intl 日期、repositoryRows 与排序核对。"""
    payload = {
        'nasty': NASTY_MATRIX,
        'row_sets': row_sets,
        'date_samples': date_samples,
        'repository_check': {
            'index_path': str(root / 'web/data/repositories.json'),
            'snapshot_dir': str(root / 'web/data'),
            'engine': 'ubs-engine',
        },
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
            ['node', script_path, payload_path, str(root / 'web/core.js'),
             result_path],
            capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            return {'status': 'error', 'stderr': proc.stderr[-2000:]}
        with open(result_path, encoding='utf-8') as fh:
            return json.load(fh)


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


def _replay_baseline(index, snapshots):
    """指纹匹配审计冻结输入时回放 U21/U23/U26/U29/U31/U38/A11。"""
    engine = snapshots['ubs-engine']
    merged_rows = own_pr_csv_rows(engine, state='merged', sort='e2e')
    first = merged_rows[0] if merged_rows else None
    p1600 = next(p for p in engine['prs'] if p['number'] == 1600)
    batch_rows = own_batch_csv_rows(engine, p1600)
    rep_url = vsm.representative(p1600)[0]['representative_batch_url']
    rep_batch = next((b for b in p1600['batches'] if b['url'] == rep_url),
                     None)
    rep_expected = ((len(rep_batch['children']) if rep_batch['children'] else 1)
                    if rep_batch else 0)
    rep_actual = sum(1 for r in batch_rows if r[10] is True)
    quality = own_quality_rows(engine['prs'], engine['meta'])
    repo_rows, _names = own_repo_csv_rows(index, snapshots)
    roundtrip = own_parse(own_csv([['=中文,"带换行\n标题']]))[0][0]
    checks = {
        'U21_pr_export_full_merged_set': {
            'rows': len(merged_rows), 'expected': 50,
            'passed': len(merged_rows) == 50},
        'U23_first_row_representative_fields': {
            'repository': first[0] if first else None,
            'pr': first[1] if first else None,
            'e2e_ms': first[14] if first else None,
            'expected': ['openeuler/ubs-engine', 1599, 4288049],
            'passed': bool(first) and first[0] == 'openeuler/ubs-engine'
            and first[1] == 1599 and first[14] == 4288049},
        'U26_detail_batch_task_rows': {
            'pr': 1600, 'batches': len(p1600['batches']),
            'rows': len(batch_rows), 'representative_rows': rep_actual,
            'expected': {'batches': 5, 'rows': 23,
                         'representative_rows': rep_expected},
            'passed': (len(p1600['batches']) == 5 and len(batch_rows) == 23
                       and rep_actual == rep_expected)},
        'U29_quality_export_records': {
            'rows': len(quality), 'expected': 17,
            'passed': len(quality) == 17},
        'U31_repository_csv_repos': {
            'rows': len(repo_rows), 'expected': 9,
            'passed': len(repo_rows) == 9},
        'U38_text_roundtrip': {
            'value': roundtrip,
            'expected': "'=中文,\"带换行\n标题",
            'passed': roundtrip == "'=中文,\"带换行\n标题"},
        'A11_pages_blob_filename': {
            'filename': 'ubs-engine' + '-pr-summary.csv',
            'expected': 'ubs-engine-pr-summary.csv',
            'locked_by': 'app.js:pr_filename 源码契约',
            'passed': 'ubs-engine' + '-pr-summary.csv'
            == 'ubs-engine-pr-summary.csv'},
    }
    ok = all(c['passed'] for c in checks.values())
    return {'status': 'matched' if ok else 'mismatch', 'checks': checks}


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

    pr_default, pr_repo_ok = {}, {}
    batch_rows_total, batch_rep_rows, batch_rep_expected = {}, {}, {}
    eligible_mismatch, quality_counts = {}, {}
    row_sets, date_samples = {}, []
    for name in REPOS:
        snap = snapshots.get(name)
        if snap is None:
            continue
        rows = own_pr_csv_rows(snap)
        pr_default[name] = len(rows)
        pr_repo_ok[name] = all(r[0] == snap['meta']['repository']
                               for r in rows)
        row_sets[f'pr_default_{name}'] = [PR_HEADS] + rows
        all_batch, rep_rows, reps = [], 0, 0
        mism = 0
        for p in snap['prs']:
            prows = own_batch_csv_rows(snap, p)
            all_batch += prows
            rep_rows += sum(1 for r in prows if r[10] is True)
            rep_url = vsm.representative(p)[0]['representative_batch_url']
            if rep_url:
                rb = next(b for b in p['batches'] if b['url'] == rep_url)
                reps += len(rb['children']) if rb['children'] else 1
            mism += sum(1 for b in p['batches']
                        if b.get('eligible') != vsm.own_batch(b)['eligible'])
        batch_rows_total[name] = len(all_batch)
        batch_rep_rows[name] = rep_rows
        batch_rep_expected[name] = reps
        eligible_mismatch[name] = mism
        quality = own_quality_rows(snap['prs'], snap['meta'])
        quality_counts[name] = len(quality)
        row_sets[f'quality_{name}'] = (
            [QUALITY_HEADS]
            + [[snap['meta']['repository'], *r] for r in quality])
        if name == 'ubs-engine':
            row_sets['batches_ubs-engine'] = [BATCH_HEADS] + all_batch
        if snap['prs']:
            head = snap['prs'][0]
            for key in ('created_ms', 'merged_ms'):
                if head.get(key):
                    date_samples.append(head[key])
            if head['batches'] and head['batches'][0].get('request_ms'):
                date_samples.append(head['batches'][0]['request_ms'])

    engine = snapshots.get('ubs-engine')
    merged_rows = (own_pr_csv_rows(engine, state='merged', sort='e2e')
                   if engine is not None else [])
    if engine is not None:
        row_sets['pr_merged_ubs-engine'] = [PR_HEADS] + merged_rows
    repo_rows, repo_names = own_repo_csv_rows(index, snapshots)
    row_sets['repositories'] = [REPO_HEADS] + repo_rows
    date_samples = sorted(set(date_samples) | {1759971042000})

    node = _node_check(root, row_sets, date_samples)
    problems = []
    byte_equal, date_mismatch, repo_diffs = {}, {}, {}
    sequences_equal = None
    if node.get('status') == 'error':
        problems.append('node 交叉核对执行失败')
    else:
        byte_equal = {'nasty': node['nasty_csv'] == own_csv(NASTY_MATRIX)}
        for key, rows in row_sets.items():
            byte_equal[key] = node['row_sets'].get(key) == own_csv(rows)
        if not all(byte_equal.values()):
            problems.append('csv 序列化与 core.js 不一致')
        date_mismatch = {
            str(ms): {'own': own_date(ms), 'node': node['dates'].get(str(ms))}
            for ms in date_samples
            if own_date(ms) != node['dates'].get(str(ms))}
        if date_mismatch:
            problems.append('日期格式与 sv-SE 上海时区不一致')
        own_by_name = dict(zip(repo_names, repo_rows))
        for name, nv in node['repo_values'].items():
            row = own_by_name.get(name)
            if row is None:
                repo_diffs[name] = ['missing_own_row']
                continue
            diffs = []
            if row[0] != nv['repository']:
                diffs.append('repository')
            if row[2] != nv['included']:
                diffs.append('included')
            if ((row[4] is None) != (not nv['included'])
                    or (nv['included'] and row[4] != nv['prs'])):
                diffs.append('prs')
            for pos, key in ((5, 'open'), (6, 'merged'), (7, 'closed')):
                if nv['included']:
                    if row[pos] != nv['counts'][key]:
                        diffs.append(f'counts.{key}')
                elif nv['counts'][key] != 0:
                    diffs.append(f'counts.{key}')
            if (row[8], row[10], row[11]) != tuple(nv['e2e']):
                diffs.append('e2e')
            for base, key in ((13, 'x86'), (16, 'arm'), (19, 'dt')):
                if tuple(row[base:base + 3]) != tuple(nv[key]):
                    diffs.append(key)
            if diffs:
                repo_diffs[name] = diffs
        if repo_diffs:
            problems.append('仓库汇总行与 repositoryRows 不一致')
        if engine is not None:
            own_default_seq = [p['number'] for p in vso.own_sort_prs(
                vuf.own_filter(engine['prs']), 'e2e')]
            own_merged_seq = [p['number'] for p in vso.own_sort_prs(
                vuf.own_filter(engine['prs'], state='merged'), 'e2e')]
            sequences_equal = (node['engine_default_seq'] == own_default_seq
                               and node['engine_merged_seq'] == own_merged_seq)
            if not sequences_equal:
                problems.append('PR 导出排序序列与 core.js 不一致')

    if not all(pr_repo_ok.values()):
        problems.append('PR 导出行仓库标识与快照不一致')
    if any(eligible_mismatch.values()):
        problems.append('批次 eligible 字段与独立重算不一致')
    for name in REPOS:
        if (name in batch_rep_rows
                and batch_rep_rows[name] != batch_rep_expected[name]):
            problems.append(f'{name} 代表批次导出行数与代表批次任务数不一致')
            break
    contracts = _check_source_contracts(root)
    if contracts['missing']:
        problems.append('源码契约缺失: ' + ','.join(contracts['missing']))
    if matches_baseline:
        baseline = _replay_baseline(index, snapshots)
        if baseline['status'] != 'matched':
            problems.append('审计基线回放不一致')
    else:
        baseline = {
            'status': 'not_applicable',
            'reason': '输入指纹与审计冻结基线不一致，基线比对跳过；'
                      '交叉核对与契约检查照常执行'}

    ok = not problems
    report = {
        'requirement': 'REQ-044',
        'tool': 'scripts/verify_ubs_csv.py',
        'executed_at': stamp(),
        'input': {
            'bundle_fingerprint': fingerprint,
            'matches_audit_frozen_input': matches_baseline,
            'manifest_state': manifest_state,
            'bundle_errors': bundle_errors,
        },
        'csv_encoding': {
            'nasty_matrix_bytes_equal': byte_equal.get('nasty'),
            'real_row_sets_bytes_equal': {k: v for k, v in byte_equal.items()
                                          if k != 'nasty'},
            'bom_and_crlf': own_csv([['a'], ['b']]) == '\ufeff"a"\r\n"b"',
            'roundtrip_formula_prefix_kept': (
                own_parse(own_csv([['=中文,"带换行\n标题']]))[0][0]
                == "'=中文,\"带换行\n标题"),
        },
        'date_format': {
            'samples_checked': len(date_samples),
            'mismatches': date_mismatch,
            'examples': {str(ms): own_date(ms) for ms in date_samples[:3]},
        },
        'pr_csv': {
            'per_repo_default_rows': pr_default,
            'per_repo_repository_column_ok': pr_repo_ok,
            'engine_merged_rows': len(merged_rows),
            'engine_merged_first_row': (merged_rows[0][:2] + [merged_rows[0][14]]
                                        if merged_rows else None),
            'engine_sequences_equal': sequences_equal,
        },
        'repo_csv': {
            'rows': len(repo_rows),
            'default_order_names': repo_names,
            'values_equal_to_repository_rows': not repo_diffs,
            'diffs': repo_diffs,
        },
        'batch_csv': {
            'per_repo_rows': batch_rows_total,
            'per_repo_representative_rows': batch_rep_rows,
            'representative_rows_expected': batch_rep_expected,
            'eligible_field_mismatches': eligible_mismatch,
        },
        'quality_csv': {'per_repo_default_counts': quality_counts},
        'source_contracts': contracts,
        'baseline': baseline,
        'node_cross_check': {
            'status': node.get('status', 'error'),
            'row_sets_compared': sorted(row_sets) + ['nasty'],
        },
        'overall': {'status': 'verified' if ok else 'failed',
                    'problems': problems},
    }
    return report, ok


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='REQ-044 UBS四类CSV内容与格式保持正确 — 保持验证工具')
    parser.add_argument('--root', default=str(ROOT), help='仓库根目录')
    parser.add_argument('--output', default=None, help='报告输出路径')
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    output = (Path(args.output).resolve() if args.output
              else root / EVIDENCE_REL / REPORT_NAME)
    try:
        report, ok = build_report(root)
    except Exception as error:  # noqa: BLE001 - 执行错误如实入报告
        print(json.dumps({'requirement': 'REQ-044', 'error': repr(error)},
                         ensure_ascii=False))
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                      'utf-8')
    print(json.dumps({
        'overall_status': report['overall']['status'],
        'csv_bytes_equal': (
            report['csv_encoding']['nasty_matrix_bytes_equal'] is True
            and all(report['csv_encoding']
                    ['real_row_sets_bytes_equal'].values())),
        'date_mismatches': len(report['date_format']['mismatches']),
        'pr_rows': report['pr_csv']['per_repo_default_rows'],
        'engine_merged_rows': report['pr_csv']['engine_merged_rows'],
        'engine_merged_first_row':
            report['pr_csv']['engine_merged_first_row'],
        'repo_rows': report['repo_csv']['rows'],
        'repo_values_equal':
            report['repo_csv']['values_equal_to_repository_rows'],
        'batch_representative_ok': (
            report['batch_csv']['per_repo_representative_rows']
            == report['batch_csv']['representative_rows_expected']),
        'eligible_mismatches': report['batch_csv']['eligible_field_mismatches'],
        'quality_counts': report['quality_csv']['per_repo_default_counts'],
        'contracts': report['source_contracts'],
        'baseline': report['baseline']['status'],
        'matches_audit_frozen_input':
            report['input']['matches_audit_frozen_input'],
        'problems': report['overall']['problems'],
        'report': str(output),
    }, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
