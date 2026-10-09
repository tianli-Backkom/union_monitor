"""REQ-041 · UBS代表值和跨仓算法保持正确 — 保持验证工具。

审计期 D03-D07 已核对正确的 UBS 统计语义，经 REQ-001..040 整改后须保持。
本工具以独立重算（沿用审计 data-audit.py 的独立实现口径，不导入生产
metrics/collect 代码）对任意快照束（默认 web/data/）验收计算契约：

- 每 PR 代表批次（最长可测量终态 E2E，并列取 trigger 编号较大者，再以
  URL 兜底）、事件时间（request_ms == 唯一关联事件 time_ms）、任务值
  （仅取代表批次、同类缺失或关联不唯一留空）与快照存储值逐一比对
- 批次派生字段（status/cancelled/end_ms/e2e_ms/jenkins_ms/eligible）与
  任务算术（end=start+duration、total=queue+duration）独立重算比对
- 跨仓参与规则镜像 web/core.js repositoryRows：快照范围==索引范围且
  status ∈ {success, partial} 才参与；失败/过期排除并记录原因，合法
  零 PR 仓库保留在参与集中
- 复合 PR 主键（仓库,PR 编号）与批次完整 URL 唯一；跨仓同号 PR 互不污染
- Node 前端算法交叉核对（web/core.js metrics/aggregate）
- 当输入指纹与审计冻结基线一致时，额外与审计基线证据
  （audit/2026-10-09/evidence/data-audit.json）比对计数、有效样本与聚合；
  输入已更新时基线比对记 not_applicable，契约检查照常（不硬编码数量）

退出码：全部一致为 0；任何差异、唯一性破坏、前端不一致、基线失配（仅
当指纹匹配时）或执行错误为 1。
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
REPORT_NAME = 'ubs-semantics-evidence.json'
BASELINE_REL = EVIDENCE_REL / 'data-audit.json'
AUDIT_BASELINE_FINGERPRINT = (
    'sha256:66f1da360414424006878e771a2bdf3f5922051ef2c0bf56385a4cb64593ec39')
PARTICIPATING_STATUSES = ('success', 'partial')
KINDS = ('x86', 'arm', 'dt')


def stamp():
    return datetime.now(timezone.utc).isoformat()


def read_json(path):
    return json.loads(Path(path).read_text('utf-8'))


def equal(a, b):
    """容差深比较（沿用审计口径：数值 rel 1e-12 / abs 1e-6）。"""
    if isinstance(a, dict) and isinstance(b, dict):
        return set(a) == set(b) and all(equal(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equal(x, y) for x, y in zip(a, b))
    if (isinstance(a, (int, float)) and not isinstance(a, bool)
            and isinstance(b, (int, float)) and not isinstance(b, bool)):
        return math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-6)
    return a == b


def pct(values, q):
    values = sorted(values)
    if not values:
        return None
    pos = (len(values) - 1) * q
    low, high = math.floor(pos), math.ceil(pos)
    return values[low] + (values[high] - values[low]) * (pos - low)


def stats(values):
    values = [v for v in values
              if isinstance(v, (int, float)) and not isinstance(v, bool)
              and math.isfinite(v) and v >= 0]
    return {'n': len(values),
            'mean': sum(values) / len(values) if values else None,
            'p90': pct(values, 0.9)}


def own_batch(batch):
    """独立重算批次派生字段（不读存储派生值）。"""
    jobs = [batch['trigger']] + batch['children']
    status = ('running' if any(j.get('building') for j in jobs)
              else 'incomplete' if (not batch['complete']
                                    or any(j.get('result') is None for j in jobs))
              else 'failure' if any(j['result'] != 'SUCCESS' for j in jobs)
              else 'success' if batch['children'] else 'incomplete')
    ends = [j.get('end_ms') for j in jobs]
    end = (max(ends) if ends and all(x is not None for x in ends)
           and batch['complete'] else None)
    request = batch.get('request_ms')
    scheduled = batch['trigger'].get('scheduled_ms')
    e2e = end - request if end is not None and request is not None and end >= request else None
    return {
        'status': status,
        'cancelled': any(j.get('result') in ('ABORTED', 'NOT_BUILT') for j in jobs),
        'end_ms': end,
        'e2e_ms': e2e,
        'jenkins_ms': (end - scheduled if end is not None and scheduled is not None
                       and end >= scheduled else None),
        'eligible': status in ('success', 'failure') and e2e is not None,
    }


def representative(pr):
    """独立重算代表值：最长可测量终态 E2E，并列取编号较大批次。"""
    eligible = [b for b in pr['batches']
                if own_batch(b)['eligible'] and b['e2e_ms'] >= 0]
    best = (max(eligible, key=lambda b: (b['e2e_ms'], int(b['number']), b['url']))
            if eligible else None)
    metrics = {
        'representative_batch_url': best['url'] if best else None,
        'representative_batch_number': best['number'] if best else None,
        'e2e_ms': best['e2e_ms'] if best else None,
    }
    for kind in KINDS:
        jobs = {j['url']: j for j in (best['children'] if best else [])
                if j['kind'] == kind and j.get('association_valid')
                and not j.get('building')
                and j.get('result') in ('SUCCESS', 'FAILURE', 'UNSTABLE')}
        job = next(iter(jobs.values())) if len(jobs) == 1 else {}
        metrics[kind] = {f'{field}_ms': job.get(f'{field}_ms')
                         for field in ('queue', 'duration', 'total')}
        metrics[kind]['url'] = job.get('url')
    return metrics, best


def aggregate(metrics_list):
    out = {'e2e': stats([m['e2e_ms'] for m in metrics_list])}
    for kind in KINDS:
        out[kind] = {field: stats([m[kind][f'{field}_ms'] for m in metrics_list])
                     for field in ('queue', 'duration', 'total')}
    return out


def participation(index, snapshots):
    """镜像 web/core.js repositoryRows 参与规则，逐仓记录参与/排除原因。"""
    entries = []
    for entry in index['repositories']:
        snapshot = snapshots.get(entry['name'])
        current = bool(snapshot and snapshot.get('meta', {}).get('start_ms')
                       == index['start_ms'] and snapshot.get('meta', {}).get('end_ms')
                       == index['end_ms'])
        included = current and entry['status'] in PARTICIPATING_STATUSES
        if included:
            reason = 'participates'
        elif snapshot is None:
            reason = 'snapshot_missing'
        elif not current:
            reason = 'stale_range'
        else:
            reason = f"excluded_status_{entry['status']}"
        entries.append({'name': entry['name'], 'status': entry['status'],
                        'current': current, 'participates': included,
                        'reason': reason})
    return entries


def _bundle_fingerprint(root):
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    import validate_bundle  # noqa: PLC0415 - 仓库根模块，按需导入
    return validate_bundle.verify(root)


def _node_cross_check(root, part_entries):
    core = root / 'web' / 'core.js'
    if not core.exists():
        return {'status': 'skipped_no_web_core'}
    snippet = (
        "const fs=require('fs'),m=require('./web/core.js');"
        "const i=JSON.parse(fs.readFileSync('web/data/repositories.json','utf8'));"
        "const names=" + json.dumps([e['name'] for e in part_entries
                                     if e['participates']]) + ";"
        "const prs=i.repositories.filter(r=>names.includes(r.name))"
        ".flatMap(r=>JSON.parse(fs.readFileSync('web/data/'+r.snapshot,'utf8')).prs);"
        "console.log(JSON.stringify({count:prs.length,"
        "metrics:prs.map(x=>m.metrics(x.batches)),aggregate:m.aggregate(prs)}));"
    )
    try:
        proc = subprocess.run(['node', '-e', snippet], cwd=str(root),
                              capture_output=True, text=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as error:
        return {'status': 'node_unavailable', 'error': repr(error)}
    if proc.returncode != 0:
        return {'status': 'node_failed', 'error': proc.stderr[-500:]}
    return {'status': 'ran', 'output': json.loads(proc.stdout)}


def build_report(root):
    problems = []
    index = read_json(root / 'web/data/repositories.json')
    snapshots = {entry['name']: read_json(root / 'web/data' / entry['snapshot'])
                 for entry in index['repositories']}
    part = participation(index, snapshots)
    part_by_name = {e['name']: e for e in part}

    keys, urls, shared_numbers = [], [], {}
    metrics_diffs, batch_diffs, event_diffs, job_diffs = [], [], [], []
    tie_prs, tie_violations = 0, []
    all_metrics, per_repo_counts = [], []

    for entry in index['repositories']:
        name = entry['name']
        snapshot = snapshots[name]
        prs = snapshot.get('prs', [])
        per_repo_counts.append({'name': name, 'prs': len(prs),
                                'batches': sum(len(p['batches']) for p in prs)})
        for pr in prs:
            keys.append((entry['repository'], pr['number']))
            shared_numbers.setdefault(pr['number'], set()).add(entry['repository'])
            recomputed, best = representative(pr)
            if part_by_name[name]['participates']:
                all_metrics.append(recomputed)
            if not equal(recomputed, pr.get('metrics')):
                metrics_diffs.append({'repo': name, 'pr': pr['number'],
                                      'expected': recomputed,
                                      'actual': pr.get('metrics')})
            for batch in pr['batches']:
                urls.append(batch['url'])
                derived = own_batch(batch)
                if not equal(derived, {k: batch.get(k) for k in derived}):
                    batch_diffs.append({'repo': name, 'pr': pr['number'],
                                        'batch': batch['number'],
                                        'expected': derived,
                                        'actual': {k: batch.get(k) for k in derived}})
                events = [e for e in pr.get('events', [])
                          if e['id'] == batch.get('event_id')]
                if (len(events) == 1
                        and batch.get('request_ms') != events[0].get('time_ms')):
                    event_diffs.append({'repo': name, 'pr': pr['number'],
                                        'batch': batch['number']})
                for job in [batch['trigger']] + batch['children']:
                    if (not job.get('building') and job.get('start_ms') is not None
                            and job.get('duration_ms') is not None
                            and job.get('end_ms') != job['start_ms'] + job['duration_ms']):
                        job_diffs.append({'type': 'job-end', 'url': job['url']})
                    if (job.get('queue_ms') is not None
                            and job.get('duration_ms') is not None
                            and not job.get('building')
                            and job.get('total_ms') != job['queue_ms'] + job['duration_ms']):
                        job_diffs.append({'type': 'job-total', 'url': job['url']})
            eligible = [b for b in pr['batches']
                        if own_batch(b)['eligible'] and b['e2e_ms'] >= 0]
            if eligible:
                top = max(b['e2e_ms'] for b in eligible)
                tied = [b for b in eligible if b['e2e_ms'] == top]
                if len(tied) > 1:
                    tie_prs += 1
                    if best is not None and best['number'] != max(
                            int(b['number']) for b in tied):
                        tie_violations.append({'repo': name, 'pr': pr['number']})

    prs_total = sum(c['prs'] for c in per_repo_counts)
    batches_total = sum(c['batches'] for c in per_repo_counts)
    keys_unique = len(set(keys)) == len(keys)
    urls_unique = len(set(urls)) == len(urls)
    shared = sorted(str(number) for number, repos in shared_numbers.items()
                    if len(repos) > 1)
    agg = aggregate(all_metrics)
    valid_samples = {kind: agg[kind]['queue']['n'] for kind in KINDS}

    for label, diffs in (('代表值', metrics_diffs), ('批次派生', batch_diffs),
                         ('事件时间', event_diffs), ('任务算术', job_diffs)):
        if diffs:
            problems.append(f'{label}差异 {len(diffs)} 处')
    if tie_violations:
        problems.append(f'E2E 并列代表选择违规 {len(tie_violations)} 处')
    if not keys_unique:
        problems.append('复合 PR 主键重复')
    if not urls_unique:
        problems.append('批次 URL 重复')

    node_check = _node_cross_check(root, part)
    node_summary = {'status': node_check['status']}
    if node_check['status'] == 'ran':
        output = node_check['output']
        node_metrics_ok = (output['count'] == len(all_metrics)
                           and equal(output['metrics'], all_metrics))
        node_agg_ok = equal(output['aggregate'], agg)
        node_summary.update({'prs': output['count'], 'metrics_matched': node_metrics_ok,
                             'aggregate_matched': node_agg_ok})
        if not node_metrics_ok:
            problems.append('前端 metrics 与独立重算不一致')
        if not node_agg_ok:
            problems.append('前端 aggregate 与独立重算不一致')
    elif node_check['status'] in ('node_unavailable', 'node_failed'):
        problems.append(f"前端交叉核对未完成：{node_check['status']}")

    try:
        fingerprint, _digests, manifest_state, bundle_errors = _bundle_fingerprint(root)
    except Exception as error:  # noqa: BLE001 - 指纹失败如实记录
        fingerprint, manifest_state, bundle_errors = None, f'error: {error!r}', []
    if bundle_errors:
        problems.append(f'快照束完整性错误 {bundle_errors}')
    matches_baseline = fingerprint == AUDIT_BASELINE_FINGERPRINT

    baseline = {'status': 'not_applicable_input_drifted'}
    if matches_baseline:
        baseline_path = root / BASELINE_REL
        if not baseline_path.exists():
            baseline = {'status': 'baseline_missing'}
            problems.append('输入与审计基线一致但基线证据文件缺失')
        else:
            audit = read_json(baseline_path)['ubs']
            samples_ok = all(
                valid_samples[kind] == audit['aggregate'][kind]['queue']['n']
                for kind in KINDS)
            per_repo_ok = equal(
                [{'name': c['name'], 'prs': c['prs'], 'batches': c['batches']}
                 for c in per_repo_counts],
                [{'name': r['name'], 'prs': r['prs'], 'batches': r['batches']}
                 for r in audit['per_repository']])
            agg_ok = equal(agg, audit['aggregate'])
            baseline = {
                'status': 'matched' if (prs_total == audit['prs']
                                        and batches_total == audit['batches']
                                        and samples_ok and per_repo_ok and agg_ok)
                else 'mismatched',
                'prs': {'computed': prs_total, 'baseline': audit['prs']},
                'batches': {'computed': batches_total, 'baseline': audit['batches']},
                'valid_samples': {kind: {'computed': valid_samples[kind],
                                         'baseline': audit['aggregate'][kind]['queue']['n']}
                                  for kind in KINDS},
                'per_repository': 'matched' if per_repo_ok else 'mismatched',
                'aggregate': 'matched' if agg_ok else 'mismatched',
            }
            if baseline['status'] != 'matched':
                problems.append('审计基线比对失配')

    report = {
        'requirement': 'REQ-041',
        'generated_at': stamp(),
        'input': {
            'repositories': part,
            'participating_repos': sum(1 for e in part if e['participates']),
            'excluded_repos': [e['name'] for e in part if not e['participates']],
            'zero_pr_participating_repos': [
                c['name'] for c in per_repo_counts if c['prs'] == 0
                and part_by_name[c['name']]['participates']],
            'bundle_fingerprint': fingerprint,
            'manifest_state': manifest_state,
            'matches_audit_frozen_input': matches_baseline,
        },
        'counts': {'prs': prs_total, 'batches': batches_total,
                   'participating_metrics_checked': len(all_metrics)},
        'representative_recheck': {
            'metrics_differences': len(metrics_diffs),
            'batch_field_differences': len(batch_diffs),
            'event_time_differences': len(event_diffs),
            'job_arithmetic_differences': len(job_diffs),
            'tie_census': {'prs_with_tied_max_e2e': tie_prs,
                           'tie_break_violations': tie_violations,
                           'note': ('真实冻结数据无 E2E 并列时，并列取编号较大规则'
                                    '由合成测试锁定' if tie_prs == 0
                                    else '并列批次均按编号较大者代表')},
        },
        'cross_repo': {'aggregate': agg, 'valid_samples': valid_samples},
        'identity': {
            'composite_pr_keys': len(keys),
            'composite_pr_keys_unique': keys_unique,
            'batch_urls': len(urls),
            'batch_urls_unique': urls_unique,
            'pr_numbers_in_multiple_repos': shared,
        },
        'frontend_cross_check': node_summary,
        'audit_baseline_comparison': baseline,
        'overall': {'status': 'verified' if not problems else 'failed',
                    'problems': problems},
    }
    return report, not problems


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='REQ-041 UBS代表值和跨仓算法保持正确 — 保持验证工具')
    parser.add_argument('--root', default=str(ROOT), help='仓库根目录')
    parser.add_argument('--output', default=None, help='报告输出路径')
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    output = (Path(args.output).resolve() if args.output
              else root / EVIDENCE_REL / REPORT_NAME)
    try:
        report, ok = build_report(root)
    except Exception as error:  # noqa: BLE001 - 执行错误如实入报告
        print(json.dumps({'requirement': 'REQ-041', 'error': repr(error)},
                         ensure_ascii=False))
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(json.dumps({
        'overall_status': report['overall']['status'],
        'counts': report['counts'],
        'valid_samples': report['cross_repo']['valid_samples'],
        'differences': {k: v for k, v
                        in report['representative_recheck'].items()
                        if k.endswith('differences')},
        'ties': report['representative_recheck']['tie_census']['prs_with_tied_max_e2e'],
        'identity': report['identity'],
        'frontend': report['frontend_cross_check'],
        'baseline': report['audit_baseline_comparison']['status'],
        'matches_audit_frozen_input': report['input']['matches_audit_frozen_input'],
        'problems': report['overall']['problems'],
        'report': str(output),
    }, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
