"""REQ-042 · UBS筛选保持PR集合及代表批次 — 保持验证工具。

审计期 U12-63、U19-queue、U19-duration、U19-total、U20 已核对正确的 UBS 筛选
语义，经 REQ-001..041 整改后须保持。本工具以独立谓词（沿用审计
ubs-browser.cjs ownFilter 口径，并按生产契约实现事件身份去重）对任意快照束
（默认 web/data/）验收计算契约：

- 组合筛选（状态 × 编号/标题/作者/SHA 搜索 × 完整性 × push/retest 触发）的
  PR 身份集合与 web/core.js filterPRs 逐仓逐组合一致；搜索大小写不敏感、
  首尾空格剥离保持（AC01）
- 触发请求按事件身份（id）去重：独立重算 triggerCounts（create/push/retest/
  other 计数、无关联事件、未知来源批次）与生产一致；审计期非去重谓词在冻结
  输入上与去重契约一致，分歧仅作事实记录、不作为门禁（AC02）
- 完整性按已声明条件选择：complete = 有批次且全部可测量且无 PR 级问题；
  incomplete = 无批次 / 有问题 / 存在不可测量批次（AC02）
- 无关联请求与未知来源批次仍可追踪：此类 PR 保留在默认集合，任何筛选组合
  都不截掉 PR 的批次（AC02）
- 筛选不重写效率事实：同一 PR 在所有组合中的代表批次 URL 与全局/存储值一致，
  E2E 与 x86 排队/总耗时（含空值）逐组合不变、空值不补 0（AC03/AC04）
- 无结果组合返回空集、默认参数返回完整 PR 集合（重置语义 = 清空四项筛选）；
  跨仓按状态汇聚的 PR 计数与 repositoryRows 一致（AC01/AC04）
- 输入指纹与审计冻结基线一致时，回放审计 U12 组合计数与 U19 首行代表批次
  （含 x86 排队/执行/总耗时算术 4.125s+127ms=4.252s）；输入更新后基线比对记
  not_applicable，契约检查照常（不硬编码数量）

退出码：全部一致为 0；任何集合失配、事实重写、去重分歧（生产 vs 独立）、
跨仓失配或执行错误为 1。
"""
import argparse
import json
import math
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_REL = Path('audit/2026-10-09/evidence')
REPORT_NAME = 'ubs-filtering-evidence.json'
BASELINE_REL = EVIDENCE_REL / 'ubs-browser.json'
AUDIT_BASELINE_FINGERPRINT = (
    'sha256:66f1da360414424006878e771a2bdf3f5922051ef2c0bf56385a4cb64593ec39')
STATES = ('', 'open', 'merged', 'closed')
QUALITIES = ('', 'complete', 'incomplete')
TRIGGERS = ('', 'create', 'push', 'retest')
KINDS = ('create', 'push', 'retest')
NO_RESULT_QUERY = '__NO_RESULTS__'


def stamp():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text('utf-8'))


def own_trigger_counts(pr):
    """独立重算触发计数：事件按 id 去重（后写覆盖，镜像生产 Map 语义）。"""
    events = {}
    for event in pr.get('events') or []:
        events[event['id']] = event
    ids = set(events)
    batches = pr.get('batches') or []
    out = {'create': 0, 'push': 0, 'retest': 0, 'other': 0,
           'unlinked': 0, 'unknownBatches': 0}
    for event in events.values():
        kind = event.get('kind')
        out[kind if kind in KINDS else 'other'] += 1
        if not any(b.get('event_id') == event['id'] for b in batches):
            out['unlinked'] += 1
    out['unknownBatches'] = sum(1 for b in batches if b.get('event_id') not in ids)
    return out


def own_filter(prs, state='', query='', quality='', trigger=''):
    """独立谓词：状态/搜索/完整性/触发组合筛选（镜像生产契约，不导入生产代码）。"""
    q = query.strip().lower()

    def haystack(p):
        parts = [str(p.get('number', '')), str(p.get('title') or ''),
                 str(p.get('author') or '')]
        parts += [str(b.get('sha') or '') for b in p.get('batches') or []]
        return ' '.join(parts).lower()

    def keep(p):
        if state and p.get('state') != state:
            return False
        if q and q not in haystack(p):
            return False
        if trigger and own_trigger_counts(p).get(trigger, 0) <= 0:
            return False
        batches = p.get('batches') or []
        issues = p.get('issues') or []
        if quality == 'complete':
            if not (batches and all(b.get('eligible') for b in batches)
                    and not issues):
                return False
        elif quality == 'incomplete':
            if not (not batches or issues
                    or any(not b.get('eligible') for b in batches)):
                return False
        return True

    return [p for p in prs if keep(p)]


def _participating(index, snapshots):
    out = []
    for entry in index['repositories']:
        snap = snapshots.get(entry['name'])
        current = bool(snap and snap.get('meta', {}).get('start_ms')
                       == index['start_ms'] and snap.get('meta', {}).get('end_ms')
                       == index['end_ms'])
        out.append((entry['name'], current and entry['status']
                    in ('success', 'partial')))
    return out


def _bundle_fingerprint(root):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import validate_bundle  # noqa: PLC0415 - 仓库根模块，按需导入
    return validate_bundle.verify(root)


def _node_filter_check(root, combos_by_repo):
    core = root / 'web' / 'core.js'
    if not core.exists():
        return {'status': 'skipped_no_web_core'}
    snippet = (
        "const fs=require('fs'),m=require('./web/core.js');"
        "const i=JSON.parse(fs.readFileSync('web/data/repositories.json','utf8'));"
        "const combos=" + json.dumps(combos_by_repo) + ";"
        "const out={repos:{},cross:{}};"
        "for(const r of i.repositories){"
        "if(!r.snapshot){out.repos[r.name]={prs:0,globalRep:{},storedRep:{},"
        "storedE2e:{},batches:{},counts:{},per:[],first:null};continue;}"
        "const snap=JSON.parse(fs.readFileSync('web/data/'+r.snapshot,'utf8'));"
        "const prs=snap.prs||[];"
        "const g={},st={},se={},b={},tc={};"
        "for(const p of prs){const mm=m.metrics(p.batches);"
        "g[p.number]=mm.representative_batch_url;"
        "st[p.number]=(p.metrics||{}).representative_batch_url??null;"
        "se[p.number]=(p.metrics||{}).e2e_ms??null;"
        "b[p.number]=p.batches.length;tc[p.number]=m.triggerCounts(p);}"
        "const per=[];"
        "for(const c of (combos[r.name]||[])){"
        "per.push(m.filterPRs(prs,c).map(p=>{const mm=m.metrics(p.batches);"
        "return {n:p.number,b:p.batches.length,r:mm.representative_batch_url,"
        "e:mm.e2e_ms,q:mm.x86.queue_ms,t:mm.x86.total_ms};}));}"
        "const first=m.sortPRs(prs)[0]||null;"
        "out.repos[r.name]={prs:prs.length,globalRep:g,storedRep:st,storedE2e:se,"
        "batches:b,counts:tc,per,"
        "first:first?{number:first.number,"
        "rep:m.metrics(first.batches).representative_batch_url,"
        "x86:m.metrics(first.batches).x86}:null};}"
        "const snaps=Object.fromEntries(i.repositories.map(r=>[r.name,"
        "JSON.parse(fs.readFileSync('web/data/'+r.snapshot,'utf8'))]));"
        "for(const s of ['','open','merged','closed'])"
        "out.cross[s]=m.repositoryRows(i,snaps,s).reduce((n,r)=>n+r.prs.length,0);"
        "console.log(JSON.stringify(out));"
    )
    try:
        proc = subprocess.run(['node', '-e', snippet], cwd=str(root),
                              capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        return {'status': 'node_unavailable', 'error': repr(error)}
    if proc.returncode != 0:
        return {'status': 'node_failed', 'error': proc.stderr[-500:]}
    return {'status': 'ran', 'output': json.loads(proc.stdout)}


def _same_value(a, b):
    """容差比较（沿用审计口径：数值 rel 1e-12 / abs 1e-6；None 只与 None 等）。"""
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-6)
    return a == b


def build_report(root):
    problems = []
    index = read_json(root / 'web/data/repositories.json')
    snapshots = {e['name']: read_json(root / 'web/data' / e['snapshot'])
                 for e in index['repositories'] if e.get('snapshot')}

    combos_by_repo, queries_by_repo = {}, {}
    for name, snap in snapshots.items():
        prs = snap.get('prs') or []
        queries = {}
        if prs:
            first = prs[0]
            queries['number'] = str(first.get('number', ''))
            author = str(first.get('author') or '')
            queries['author'] = author
            queries['author_upper'] = author.upper()
            queries['author_padded'] = f'  {author}  '
            for b in first.get('batches') or []:
                if b.get('sha'):
                    queries['sha8'] = b['sha'][:8]
                    break
            title = str(first.get('title') or '')
            if title:
                queries['title_lower'] = title[:6].lower()
        queries['none'] = NO_RESULT_QUERY
        base = [{'state': s, 'query': '', 'quality': q, 'trigger': t}
                for s in STATES for q in QUALITIES for t in TRIGGERS]
        qcombos = [{'state': '', 'query': v, 'quality': '', 'trigger': ''}
                   for v in queries.values()]
        mixed = [{'state': '', 'query': '', 'quality': 'incomplete',
                  'trigger': 'push'}]
        if 'number' in queries:
            mixed.insert(0, {'state': 'merged', 'query': queries['number'],
                             'quality': '', 'trigger': 'retest'})
        if 'author_upper' in queries:
            mixed.insert(1, {'state': '', 'query': queries['author_upper'],
                             'quality': 'complete', 'trigger': ''})
        combos_by_repo[name] = base + qcombos + mixed
        queries_by_repo[name] = queries

    py = {}
    for name, snap in snapshots.items():
        prs = snap.get('prs') or []
        stored = {}
        for p in prs:
            metrics = p.get('metrics') or {}
            x86 = metrics.get('x86') or {}
            stored[p['number']] = {
                'rep': metrics.get('representative_batch_url'),
                'e2e': metrics.get('e2e_ms'),
                'x86_queue': x86.get('queue_ms'),
                'x86_total': x86.get('total_ms'),
            }
        py[name] = {
            'prs': len(prs),
            'per': [sorted(p['number'] for p in own_filter(prs, **c))
                    for c in combos_by_repo[name]],
            'default': sorted(p['number'] for p in own_filter(prs)),
            'counts': {p['number']: own_trigger_counts(p) for p in prs},
            'stored': stored,
            'batches': {p['number']: len(p.get('batches') or []) for p in prs},
        }

    node = _node_filter_check(root, combos_by_repo)
    combo_mismatches, fact_mismatches, dedup_mismatches, stored_mismatches = [], [], [], []
    normalization, cross_repo = {}, {s: {'python': None, 'node': None, 'match': False}
                                     for s in STATES}
    total_combos = no_result_empty = default_full = None
    null_e2e_prs = prs_with_rep = 0

    if node['status'] != 'ran':
        problems.append(f"前端交叉核对未完成：{node['status']}")
    else:
        outj = node['output']
        total_combos = 0
        no_result_empty = True
        default_full = True
        for name, snap in snapshots.items():
            nr = outj['repos'].get(name)
            if nr is None:
                problems.append(f'前端输出缺少仓库 {name}')
                continue
            info = py[name]
            for number, counts in info['counts'].items():
                if not _same_value(counts, nr['counts'].get(str(number))):
                    dedup_mismatches.append({'repo': name, 'pr': number})
            for number, st in info['stored'].items():
                null_e2e_prs += 1 if st['e2e'] is None else 0
                prs_with_rep += 1 if st['rep'] is not None else 0
                if not _same_value(st['rep'], nr['globalRep'].get(str(number))):
                    stored_mismatches.append({'repo': name, 'pr': number})
            combos = combos_by_repo[name]
            base_len = len(STATES) * len(QUALITIES) * len(TRIGGERS)
            qkeys = list(queries_by_repo[name])
            norm_idx = [base_len + qkeys.index(label)
                        for label in ('author', 'author_upper', 'author_padded')
                        if label in queries_by_repo[name]]
            norm_sets = [info['per'][i] for i in norm_idx]
            norm_node = [sorted(r['n'] for r in nr['per'][i]) for i in norm_idx]
            normalization[name] = {
                'agree': (all(s == norm_sets[0] for s in norm_sets)
                          and all(s == norm_node[0] for s in norm_node)),
                'sizes': {label: len(info['per'][i]) for label, i
                          in zip(('author', 'author_upper', 'author_padded'),
                                 norm_idx)},
            }
            for idx, combo in enumerate(combos):
                total_combos += 1
                rows = nr['per'][idx] if idx < len(nr['per']) else None
                if rows is None:
                    combo_mismatches.append({'repo': name, 'combo': combo,
                                             'reason': '前端缺少该组合'})
                    continue
                node_numbers = sorted(r['n'] for r in rows)
                if node_numbers != info['per'][idx]:
                    combo_mismatches.append({'repo': name, 'combo': combo,
                                             'python': info['per'][idx][:20],
                                             'node': node_numbers[:20]})
                if (combo['query'] == NO_RESULT_QUERY and not combo['state']
                        and not combo['quality'] and not combo['trigger']):
                    no_result_empty = no_result_empty and not node_numbers
                if idx == 0:
                    default_full = (default_full
                                    and node_numbers == sorted(info['stored']))
                for r in rows:
                    n = r['n']
                    st = info['stored'].get(n)
                    if st is None:
                        fact_mismatches.append({'repo': name, 'pr': n,
                                                'type': 'unknown-pr'})
                        continue
                    if r['b'] != info['batches'].get(n):
                        fact_mismatches.append({'repo': name, 'pr': n,
                                                'type': 'batches-truncated'})
                    if not _same_value(r['r'], nr['globalRep'].get(str(n))):
                        fact_mismatches.append({'repo': name, 'pr': n,
                                                'type': 'rep-not-invariant'})
                    if not _same_value(r['r'], st['rep']):
                        fact_mismatches.append({'repo': name, 'pr': n,
                                                'type': 'rep-vs-stored'})
                    if (not _same_value(r['e'], st['e2e'])
                            or not _same_value(r['q'], st['x86_queue'])
                            or not _same_value(r['t'], st['x86_total'])):
                        fact_mismatches.append({'repo': name, 'pr': n,
                                                'type': 'metric-rewrite'})
        included = [n for n, ok in _participating(index, snapshots) if ok]
        for s in STATES:
            pooled = sum(len(own_filter(snapshots[n].get('prs') or [], state=s))
                         for n in included)
            cross_repo[s] = {'python': pooled, 'node': outj['cross'].get(s),
                             'match': pooled == outj['cross'].get(s)}

    audit_divergences, predicate_compared = [], 0
    for name, snap in snapshots.items():
        for p in snap.get('prs') or []:
            naive = {e.get('kind') for e in p.get('events') or []}
            counts = py[name]['counts'][p['number']]
            for kind in KINDS:
                predicate_compared += 1
                if (kind in naive) != (counts[kind] > 0):
                    audit_divergences.append({'repo': name, 'pr': p['number'],
                                              'kind': kind})

    orphan = {'unknown_batches_prs': 0, 'unknown_batches_total': 0,
              'unlinked_event_prs': 0, 'unlinked_events_total': 0,
              'all_in_default_set': True}
    for name, info in py.items():
        for number, counts in info['counts'].items():
            if counts['unknownBatches'] > 0:
                orphan['unknown_batches_prs'] += 1
                orphan['unknown_batches_total'] += counts['unknownBatches']
                if number not in info['default']:
                    orphan['all_in_default_set'] = False
            if counts['unlinked'] > 0:
                orphan['unlinked_event_prs'] += 1
                orphan['unlinked_events_total'] += counts['unlinked']

    if combo_mismatches:
        problems.append(f'组合筛选身份集合失配 {len(combo_mismatches)} 处')
    if dedup_mismatches:
        problems.append(f'触发计数（事件身份去重）与生产不一致 {len(dedup_mismatches)} 处')
    if fact_mismatches:
        problems.append(f'筛选重写效率事实 {len(fact_mismatches)} 处')
    if stored_mismatches:
        problems.append(f'代表批次 URL 与存储值不一致 {len(stored_mismatches)} 处')
    if any(not v['match'] for v in cross_repo.values()):
        problems.append('跨仓状态筛选计数不一致')
    if any(not v['agree'] for v in normalization.values()):
        problems.append('搜索规范化（大小写/首尾空格）行为不一致')
    if no_result_empty is False:
        problems.append('无结果查询未返回空集')
    if default_full is False:
        problems.append('默认参数未返回完整 PR 集合')

    try:
        fingerprint, _digests, manifest_state, bundle_errors = _bundle_fingerprint(root)
    except Exception as error:  # noqa: BLE001 - 指纹失败如实记录
        fingerprint, manifest_state, bundle_errors = None, f'error: {error!r}', []
    if bundle_errors:
        problems.append(f'快照束完整性错误 {bundle_errors}')
    matches_baseline = fingerprint == AUDIT_BASELINE_FINGERPRINT

    baseline = {'status': 'not_applicable_input_drifted'}
    if matches_baseline:
        browser = read_json(root / BASELINE_REL)
        engine = snapshots['ubs-engine'].get('prs') or []
        u12 = []
        for c in browser.get('checks', []):
            if c['id'].startswith('U12-') and c['state'] == 'passed':
                combo = json.loads(c['label'][c['label'].index('{'):])
                mapped = {'state': combo.get('state', ''),
                          'query': combo.get('q', ''),
                          'quality': combo.get('quality', ''),
                          'trigger': combo.get('trigger', '')}
                computed = len(own_filter(engine, **mapped))
                u12.append({'combo': combo, 'computed': computed,
                            'baseline': c['expected'],
                            'match': computed == c['expected']})
        u19_entries = {c['id'].split('-', 1)[1]: c for c in browser.get('checks', [])
                       if c['id'].startswith('U19-') and c['state'] == 'passed'}
        first = node['output']['repos']['ubs-engine']['first'] if node['status'] == 'ran' else None

        def tooltip_ms(text):
            value, unit = text.split()
            return round(float(value) * 1000) if unit.startswith('s') else round(float(value))

        u19 = None
        if first and all(k in u19_entries for k in ('queue', 'duration', 'total')):
            x86 = first['x86']
            u19 = {
                'first_pr': first['number'],
                'representative_url': {
                    'computed': first['rep'],
                    'baseline': u19_entries['queue']['expected'],
                    'match': first['rep'] == u19_entries['queue']['expected']},
                'x86_queue_ms': {'computed': x86['queue_ms'],
                                 'baseline': tooltip_ms(u19_entries['queue']['firstTaskTooltip'])},
                'x86_duration_ms': {'computed': x86['duration_ms'],
                                    'baseline': tooltip_ms(u19_entries['duration']['firstTaskTooltip'])},
                'x86_total_ms': {'computed': x86['total_ms'],
                                 'baseline': tooltip_ms(u19_entries['total']['firstTaskTooltip'])},
            }
            for key in ('x86_queue_ms', 'x86_duration_ms', 'x86_total_ms'):
                u19[key]['match'] = _same_value(u19[key]['computed'],
                                                u19[key]['baseline'])
            u19['queue_plus_duration_equals_total'] = _same_value(
                x86['queue_ms'] + x86['duration_ms'], x86['total_ms'])
        u12_ok = bool(u12) and all(e['match'] for e in u12)
        u19_ok = bool(u19) and u19['representative_url']['match'] \
            and all(u19[k]['match'] for k in ('x86_queue_ms', 'x86_duration_ms',
                                              'x86_total_ms')) \
            and u19['queue_plus_duration_equals_total']
        baseline = {'status': 'matched' if (u12_ok and u19_ok) else 'mismatched',
                    'u12_replay': u12, 'u19': u19}
        if baseline['status'] != 'matched':
            problems.append('审计基线回放失配（U12 组合计数或 U19 代表批次）')

    report = {
        'requirement': 'REQ-042',
        'generated_at': stamp(),
        'input': {
            'repositories': list(snapshots),
            'repos_checked': len(snapshots),
            'bundle_fingerprint': fingerprint,
            'manifest_state': manifest_state,
            'matches_audit_frozen_input': matches_baseline,
        },
        'combos': {
            'total_compared': total_combos,
            'per_repo': {name: len(c) for name, c in combos_by_repo.items()},
            'dimensions': {'states': list(STATES), 'qualities': list(QUALITIES),
                           'triggers': list(TRIGGERS),
                           'query_variants': ['编号', '作者', '作者大写',
                                              '作者首尾空格', 'SHA 前 8 位',
                                              '标题小写片段', '无结果']},
        },
        'identity': {
            'combo_mismatches': combo_mismatches[:20],
            'combo_mismatch_count': len(combo_mismatches),
            'query_normalization': normalization,
        },
        'trigger_dedup': {
            'prs_compared': sum(i['prs'] for i in py.values()),
            'mismatches': dedup_mismatches[:20],
            'mismatch_count': len(dedup_mismatches),
            'audit_predicate': {
                'compared': predicate_compared,
                'divergences': audit_divergences[:20],
                'divergence_count': len(audit_divergences),
                'note': ('审计 ownFilter 以 events.some(kind) 非去重谓词取期望值；'
                         '生产契约按事件 id 去重。冻结输入两者一致，分歧仅记录'
                         '事实、不作为门禁'),
            },
        },
        'quality': {
            'rule_complete': '有批次 且 全部批次可测量(eligible) 且 无 PR 级问题',
            'rule_incomplete': '无批次 或 有 PR 级问题 或 存在不可测量批次',
            'agreement': '独立谓词与生产 filterPRs 逐仓逐组合一致'
                         if not combo_mismatches else '存在失配',
        },
        'orphan_tracking': orphan,
        'representative_invariance': {
            'prs': sum(i['prs'] for i in py.values()),
            'prs_with_rep': prs_with_rep,
            'null_e2e_prs': null_e2e_prs,
            'stored_mismatches': stored_mismatches[:20],
            'stored_mismatch_count': len(stored_mismatches),
            'fact_mismatches': fact_mismatches[:20],
            'fact_mismatch_count': len(fact_mismatches),
            'nulls_preserved': not any(
                f['type'] == 'metric-rewrite' for f in fact_mismatches),
            'note': '代表批次 URL 与 E2E/x86 排队/总耗时在全部组合中与存储值一致，'
                    '空值保持为空、不补 0',
        },
        'no_result_and_reset': {
            'no_result_empty': no_result_empty,
            'default_full': default_full,
            'reset_semantics': '重置清空 搜索/状态/完整性/触发 四项筛选并回第一页，'
                               '恢复默认 PR 集合（app.js reset 处理器）',
        },
        'cross_repo': cross_repo,
        'audit_baseline_comparison': baseline,
        'overall': {'status': 'verified' if not problems else 'failed',
                    'problems': problems},
    }
    return report, not problems


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='REQ-042 UBS筛选保持PR集合及代表批次 — 保持验证工具')
    parser.add_argument('--root', default=str(ROOT), help='仓库根目录')
    parser.add_argument('--output', default=None, help='报告输出路径')
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    output = (Path(args.output).resolve() if args.output
              else root / EVIDENCE_REL / REPORT_NAME)
    try:
        report, ok = build_report(root)
    except Exception as error:  # noqa: BLE001 - 执行错误如实入报告
        print(json.dumps({'requirement': 'REQ-042', 'error': repr(error)},
                         ensure_ascii=False))
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(json.dumps({
        'overall_status': report['overall']['status'],
        'repos': report['input']['repos_checked'],
        'combos_compared': report['combos']['total_compared'],
        'combo_mismatches': report['identity']['combo_mismatch_count'],
        'dedup_mismatches': report['trigger_dedup']['mismatch_count'],
        'fact_mismatches': report['representative_invariance']['fact_mismatch_count'],
        'stored_mismatches': report['representative_invariance']['stored_mismatch_count'],
        'normalization_agree': all(v['agree'] for v
                                   in report['identity']['query_normalization'].values()),
        'audit_predicate_divergences': report['trigger_dedup']['audit_predicate']['divergence_count'],
        'orphan_tracking': report['orphan_tracking'],
        'cross_repo_all_match': all(v['match'] for v in report['cross_repo'].values()),
        'no_result_empty': report['no_result_and_reset']['no_result_empty'],
        'default_full': report['no_result_and_reset']['default_full'],
        'baseline': report['audit_baseline_comparison']['status'],
        'matches_audit_frozen_input': report['input']['matches_audit_frozen_input'],
        'problems': report['overall']['problems'],
        'report': str(output),
    }, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
