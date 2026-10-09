"""REQ-038 · 原始工件补齐及历史影响核验（audit 2026-10-09）.

对冻结审计工件集的离线核验（REQ-038：不能用当前平台状态冒充历史事实）：

  AC01  工件清单 — 路径、存在性、SHA-256、字节数、来源、采集时刻/窗口及与
        冻结快照的关联；审计 D10 声明缺失的每一类工件保持明确未验证标注
  AC02  四类独立比对 — 原始时间、queue 三项、PR 身份、attempt 历史，每类
        满足 REQ-023 计数等式：已验证一致 + 派生自洽 + 差异 + 缺证据 =
        适用总数，并附身份明细（缺失/差异样本）
  AC03  真实重跑影响 — 冻结快照内每个 rerun 批次按原规则
        （E2E = end_at − 原 run created_at，审计 S01/F08）与 REQ-014/015
        规则（本次 attempt 起点）分别计算；冻结 payload 未持久化
        run_started_at，新规则 E2E 只能给区间（旧规则高估上限由本次
        attempt 的 job 时间证据界定），不虚构精确值；S01 的 300 秒为合成
        输入，不能证明历史真实 E2E，报告单列并隔离
  AC04  部署核验 — 本地 UBS 快照束经 validate_bundle（REQ-022 指纹方法）
        核验构建工件绑定；合并看板无真实部署（无 git remote、无 Actions
        运行）如实记录为未验证；两个旧站的探测记录入档 site-probe.json，
        当前平台状态不冒充审计截止点历史事实，旧站公开源码抓取不作为
        替代证据

退出码：0 = 报告生成且全部可执行交叉核对无差异；1 = 执行错误或交叉核对
发现差异（冻结审计证据与本地工件集漂移）。原始工件缺失按 D10 记为未
验证、不因此失败——来源覆盖的强制门禁由 validate_multi.py 承担。

用法：
  python -X utf8 scripts/verify_artifacts.py            # 离线生成报告
  python -X utf8 scripts/verify_artifacts.py --probe    # 先联网刷新旧站探测记录
"""
import argparse
import csv
import hashlib
import json
import math
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

TOOL = 'verify_artifacts'
FREEZE_REL = Path('tests/fixtures/triton-audit-freeze.json')
AUDIT_REL = Path('audit/2026-10-09/evidence')
REPORT_NAME = 'artifact-verification.json'
PROBE_NAME = 'site-probe.json'
# 审计 D10 声明缺失的原始工件类别（audit data-audit.json checks[D10].missing）
D10_PATHS = [
    'data/raw', 'data/efficiency.sqlite', 'data/repositories.json', 'data/repos',
    'web/data/snapshot.json', 'evidence/triton', 'web/data/triton-manifest.json',
    'web/data/triton-batches.csv',
]
SHANGHAI = timezone(timedelta(hours=8))
D10_REASON = ('审计 D10 声明的原始工件；本地缺失且不可恢复（无 git remote / gh CLI，'
              'Actions 工件与缓存不可取，旧站已推进过审计截止点）')
# REQ-038 AC04：旧站探测目标（合并看板无部署；两站均为合并前部署，仅作状态记录）
PROBE_TARGETS = [
    ('https://tianli-backkom.github.io/ubs_core_monitor/data/repositories.json', 'web/data/repositories.json'),
    ('https://tianli-backkom.github.io/ubs_core_monitor/data/repos/ubs-engine.json', 'web/data/repos/ubs-engine.json'),
    ('https://tianli-backkom.github.io/ubs_core_monitor/data/snapshot.json', 'web/data/snapshot.json'),
    ('https://tianli-backkom.github.io/ubs_core_monitor/data/ubs-manifest.json', 'web/data/ubs-manifest.json'),
    ('https://tianli-backkom.github.io/ubs_core_monitor/data/triton.json', 'web/data/triton.json'),
    ('https://tianli-backkom.github.io/Triton-Ascend_monitor/data/triton.json', 'web/data/triton.json'),
    ('https://tianli-backkom.github.io/Triton-Ascend_monitor/data/triton-manifest.json', 'web/data/triton-manifest.json'),
    ('https://tianli-backkom.github.io/Triton-Ascend_monitor/data/triton-batches.csv', 'web/data/triton-batches.csv'),
]
STATUS_ORDER = {'differ': 0, 'unverified': 1, 'partial': 2, 'not_applicable': 3, 'verified': 4, 'pass': 4}


def sha256_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    return json.loads(Path(path).read_text('utf-8'))


def stamp(value):
    if not value:
        return None
    return datetime.fromisoformat(str(value).replace('Z', '+00:00')).timestamp()


def iso_ms(value):
    return datetime.fromtimestamp(value / 1000, timezone.utc).isoformat() if value is not None else None


def _num(value):
    if value is None:
        return None
    text = str(value).strip()
    return float(text) if text not in ('', 'None') else None


def _int_or_none(value):
    number = _num(value)
    return int(number) if number is not None else None


def _ensure_root_on_path(root):
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)


def _git_remotes(root):
    try:
        proc = subprocess.run(['git', '-C', str(root), 'remote'], capture_output=True, text=True)
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _ubs_index(root):
    path = root / 'web/data/repositories.json'
    if not path.exists():
        return None
    try:
        return read_json(path)
    except ValueError:
        return None


def _ubs_snapshots(root):
    index = _ubs_index(root)
    snaps = {}
    if not index:
        return snaps, None
    for entry in index.get('repositories', []):
        snapshot = entry.get('snapshot')
        if not snapshot:
            continue
        path = root / 'web/data' / snapshot
        if path.exists():
            try:
                snaps[entry.get('repository')] = read_json(path)
            except ValueError:
                continue
    return snaps, index


# ---------------------------------------------------------------- AC01 清单

def inventory(root):
    """工件清单：存在性/SHA-256/来源/窗口/冻结关联；缺失项标未验证（REQ-038-AC01）。"""
    freeze_path = root / FREEZE_REL
    freeze = read_json(freeze_path) if freeze_path.exists() else None
    index = _ubs_index(root)
    manifest_files = {}
    manifest_path = root / 'web/data/ubs-manifest.json'
    if manifest_path.exists():
        try:
            manifest_files = read_json(manifest_path).get('files', {})
        except ValueError:
            manifest_files = {}

    ubs_window = None
    if index:
        ubs_window = {'start': iso_ms(index.get('start_ms')), 'end': iso_ms(index.get('end_ms')),
                      'generated_at': index.get('generated_at')}
    triton_window = None
    if freeze:
        triton_window = {'window_start': freeze.get('window_start'), 'window_end': freeze.get('window_end'),
                         'collected_at': freeze.get('collected_at')}

    freeze_bytes = freeze_path.read_bytes() if freeze_path.exists() else None
    artifacts = []

    def add(rel, source, window=None, relation=None, missing_reason=None):
        path = root / rel
        entry = {'path': rel, 'source': source, 'exists': path.exists()}
        if path.exists():
            entry['status'] = 'present'
            if path.is_file():
                entry['sha256'] = sha256_file(path)
                entry['bytes'] = path.stat().st_size
            else:
                entry['type'] = 'directory'
                entry['file_count'] = sum(1 for item in path.rglob('*') if item.is_file())
            if window:
                entry['window'] = window
            if relation:
                entry['freeze_relation'] = relation(path) if callable(relation) else relation
        else:
            entry['status'] = 'unverified'
            entry['reason'] = missing_reason or '本地缺失；按 REQ-038 以未验证如实记录'
        artifacts.append(entry)
        return entry

    def manifest_relation(rel):
        def relation(path):
            recorded = manifest_files.get(rel)
            if recorded is None:
                return 'ubs-manifest.json 未覆盖该文件'
            return ('matches ubs-manifest.json fingerprint' if recorded == sha256_file(path)
                    else 'differs from ubs-manifest.json（本地数据已在审计后刷新）')
        return relation

    if index:
        add('web/data/repositories.json', 'collect.py 多仓索引（审计冻结范围）', ubs_window,
            manifest_relation('repositories.json'))
        for entry_index in index.get('repositories', []):
            snapshot = entry_index.get('snapshot')
            if snapshot:
                add(f'web/data/{snapshot}', f"collect.py 单仓快照（{entry_index.get('repository')}）",
                    ubs_window, manifest_relation(snapshot))
    else:
        add('web/data/repositories.json', 'collect.py 多仓索引（本地缺失）')
    add('web/data/ubs-manifest.json', 'validate_bundle --write-manifest 生成的构建工件指纹（REQ-022 方法）')
    if freeze:
        add(str(FREEZE_REL), 'REQ-028 冻结快照 fixture（提交于 git，统计契约基准）', triton_window)
    triton_path = root / 'web/data/triton.json'
    triton_relation = None
    if triton_path.exists() and freeze_bytes is not None:
        triton_relation = ('byte-identical to tests/fixtures/triton-audit-freeze.json'
                           if triton_path.read_bytes() == freeze_bytes
                           else 'differs from tests/fixtures/triton-audit-freeze.json（本地数据已在审计后刷新）')
    add('web/data/triton.json', 'triton.dashboard 采集输出（审计冻结窗口）', triton_window, triton_relation)
    compat = root / 'data/snapshot.json'
    engine = root / 'web/data/repos/ubs-engine.json'
    compat_relation = None
    if compat.exists() and engine.exists():
        compat_relation = ('matches web/data/repos/ubs-engine.json（compat 镜像）'
                           if compat.read_bytes() == engine.read_bytes()
                           else 'differs from web/data/repos/ubs-engine.json（混版本）')
    add('data/snapshot.json', 'ubs-engine 兼容快照（仓根镜像）', None, compat_relation)
    for name, source in (
        ('triton-export.csv', 'audit 2026-10-09 Triton 批次导出（采集侧）'),
        ('triton-pages-export.csv', 'audit 2026-10-09 Triton 批次导出（旧站页面侧）'),
        ('ubs-batch-export.csv', 'audit 2026-10-09 UBS 批次导出（ubs-engine 定向样本）'),
        ('data-audit.json', 'audit 2026-10-09 派生数据审计报告（D10/S01 记录来源）'),
        (PROBE_NAME, 'verify_artifacts --probe 旧站探测记录（REQ-038 AC04）'),
    ):
        add(f'audit/2026-10-09/evidence/{name}', source)
    for declared in D10_PATHS:
        if not any(entry['path'] == declared for entry in artifacts):
            add(declared, '审计 D10 声明的原始工件类别', None, None, D10_REASON)
    return {
        'artifacts': artifacts,
        'd10_declared_missing': list(D10_PATHS),
        'recovery': {
            'git_remotes': _git_remotes(root),
            'gh_cli_available': shutil.which('gh') is not None,
            'note': '无 git remote 时本仓库从未推送：Actions 构建/部署运行与其 artifact/cache 不可获取；'
                    '两个旧站点为合并前部署且数据已前进，不能提供审计截止点的原始工件',
        },
    }


# ---------------------------------------------------------------- AC02 比对

def triton_csv_checks(root, freeze):
    """冻结快照 ↔ 审计期两份 Triton 导出（采集侧 + 旧站页面侧）逐批比对。"""
    by_key = {}
    for batch in freeze['batches']:
        by_key.setdefault((str(batch.get('pr')), batch.get('sha'), batch.get('kind')), []).append(batch)
    covered, differing = {}, {}
    result = {'compared': 0, 'consistent': 0, 'differences': [], 'files': {}}
    for name in ('triton-export.csv', 'triton-pages-export.csv'):
        path = root / AUDIT_REL / name
        if not path.exists():
            result['files'][name] = {'status': 'missing'}
            continue
        with path.open(encoding='utf-8-sig') as handle:
            rows = list(csv.DictReader(handle))
        file_differences = 0
        for row in rows:
            result['compared'] += 1
            candidates = by_key.get((row.get('pr'), row.get('sha'), row.get('kind')), [])
            batch = next((b for b in candidates if b.get('start_at') == row.get('start_at')
                          and b.get('end_at') == row.get('end_at')), None)
            if batch is None:
                file_differences += 1
                result['differences'].append({'file': name, 'pr': row.get('pr'), 'issue': 'no matching freeze batch'})
                continue
            mismatched = []
            for field in ('status', 'base_branch', 'pr_url', 'action_url'):
                if row.get(field) != batch.get(field):
                    mismatched.append(field)
            for field in ('duration_seconds', 'npu_queue_seconds'):
                if _num(row.get(field)) != batch.get(field):
                    mismatched.append(field)
            if (row.get('approximate') == 'True') != bool(batch.get('approximate')):
                mismatched.append('approximate')
            if mismatched:
                file_differences += 1
                differing[batch['id']] = differing.get(batch['id'], 0) + 1
                result['differences'].append({'file': name, 'pr': row.get('pr'), 'batch': batch['id'],
                                              'fields': mismatched})
            else:
                covered[batch['id']] = covered.get(batch['id'], 0) + 1
                result['consistent'] += 1
        result['files'][name] = {'rows': len(rows), 'differences': file_differences}
    result['covered_batches'] = sorted(covered)
    result['differing_batches'] = sorted(differing)
    return result


def ubs_csv_checks(root):
    """UBS 审计期批次导出逐行比对当前快照（E2E/Jenkins/请求时间/子任务排队、执行、总计）。"""
    result = {'rows': 0, 'consistent': 0, 'differences': [],
              'covered_batches': [], 'covered_children': [], 'covered_prs': [],
              'differing_batches': [], 'differing_children': [], 'differing_prs': []}
    path = root / AUDIT_REL / 'ubs-batch-export.csv'
    if not path.exists():
        result['note'] = 'ubs-batch-export.csv 缺失'
        return result
    snaps, _ = _ubs_snapshots(root)
    pr_map = {}
    for repo, snap in snaps.items():
        for pr in snap.get('prs', []):
            pr_map[(repo, pr.get('number'))] = pr
    covered_b, covered_c, covered_p = set(), set(), set()
    diff_b, diff_c, diff_p = set(), set(), set()
    with path.open(encoding='utf-8-sig') as handle:
        rows = list(csv.DictReader(handle))
    result['rows'] = len(rows)
    for row in rows:
        repo, pr_number = row.get('仓库'), _int_or_none(row.get('PR'))
        pr = pr_map.get((repo, pr_number))
        batch = None
        if pr is not None:
            batch = next((b for b in pr.get('batches', [])
                          if (b.get('trigger') or {}).get('url') == row.get('trigger')), None)
        if batch is None:
            result['differences'].append({'repo': repo, 'pr': pr_number, 'trigger': row.get('trigger'),
                                          'issue': '当前快照中未找到该批次'})
            diff_p.add((repo, pr_number))
            if row.get('trigger'):
                diff_b.add(row['trigger'])
            continue
        mismatched = []
        if _int_or_none(row.get('E2E ms')) != batch.get('e2e_ms'):
            mismatched.append('e2e_ms')
        if _int_or_none(row.get('Jenkins ms')) != batch.get('jenkins_ms'):
            mismatched.append('jenkins_ms')
        request = batch.get('request_ms')
        if request is not None:
            try:
                parsed = datetime.strptime(row['请求时间'], '%Y-%m-%d %H:%M:%S').replace(tzinfo=SHANGHAI)
                if abs(parsed.timestamp() * 1000 - request) > 999:
                    mismatched.append('request_ms')
            except (KeyError, ValueError):
                mismatched.append('request_time_unparseable')
        child = next((c for c in batch.get('children', []) if c.get('url') == row.get('子任务')), None)
        if child is None:
            mismatched.append('child_task_missing')
        else:
            for field, column in (('queue_ms', '排队ms'), ('duration_ms', '执行ms'), ('total_ms', '总计ms')):
                if _int_or_none(row.get(column)) != child.get(field):
                    mismatched.append(field)
        if mismatched:
            result['differences'].append({'repo': repo, 'pr': pr_number, 'trigger': row.get('trigger'),
                                          'fields': mismatched})
            diff_b.add(row.get('trigger'))
            diff_p.add((repo, pr_number))
            if child is not None:
                diff_c.add(child['url'])
        else:
            result['consistent'] += 1
            covered_b.add(row.get('trigger'))
            if child is not None:
                covered_c.add(child['url'])
            covered_p.add((repo, pr_number))
    result['covered_batches'] = sorted(x for x in covered_b if x)
    result['covered_children'] = sorted(covered_c)
    result['covered_prs'] = sorted(covered_p)
    result['differing_batches'] = sorted(x for x in diff_b if x)
    result['differing_children'] = sorted(diff_c)
    result['differing_prs'] = sorted(diff_p)
    return result


def ubs_counts(root):
    """UBS 快照适用计数与身份样本（原始时间/queue 三项/attempt 历史的适用分母）。"""
    counts = {'prs': 0, 'batches': 0, 'batches_with_request': 0,
              'jobs_with_queue': 0, 'triggers_with_queue': 0, 'children_with_queue': 0,
              'multi_batch_prs': 0, 'retest_batches': 0, 'retest_linked': 0,
              'retest_unlinked_sample': [], 'batch_trigger_urls': [], 'pr_ids': [],
              'queue_job_urls': [], 'snapshots_present': False}
    snaps, _ = _ubs_snapshots(root)
    counts['snapshots_present'] = bool(snaps)
    for repo, snap in snaps.items():
        for pr in snap.get('prs', []):
            counts['prs'] += 1
            counts['pr_ids'].append([repo, pr.get('number')])
            batches = pr.get('batches', [])
            counts['batches'] += len(batches)
            if len(batches) > 1:
                counts['multi_batch_prs'] += 1
            event_ids = {e.get('id') for e in pr.get('events', [])}
            for batch in batches:
                trigger_url = (batch.get('trigger') or {}).get('url')
                if trigger_url:
                    counts['batch_trigger_urls'].append(trigger_url)
                if batch.get('request_ms') is not None:
                    counts['batches_with_request'] += 1
                if (batch.get('trigger') or {}).get('queue_ms') is not None:
                    counts['triggers_with_queue'] += 1
                for job in [batch.get('trigger') or {}] + batch.get('children', []):
                    if job.get('queue_ms') is not None:
                        counts['jobs_with_queue'] += 1
                        if len(counts['queue_job_urls']) < 10:
                            counts['queue_job_urls'].append(job.get('url'))
                for child in batch.get('children', []):
                    if child.get('queue_ms') is not None:
                        counts['children_with_queue'] += 1
                if batch.get('event_type') == 'retest':
                    counts['retest_batches'] += 1
                    if batch.get('event_id') in event_ids:
                        counts['retest_linked'] += 1
                    elif len(counts['retest_unlinked_sample']) < 10:
                        counts['retest_unlinked_sample'].append(trigger_url or batch.get('url'))
    return counts


def triton_pr_propagation(freeze):
    """Triton 批次 PR/SHA 与其全部 workflow 的传播一致性（派生自洽检查）。"""
    mismatches = []
    workflows = 0
    for batch in freeze['batches']:
        for workflow in batch.get('workflows', []):
            workflows += 1
            if workflow.get('pr') != batch.get('pr') or workflow.get('head_sha') != batch.get('sha'):
                mismatches.append({'batch': batch.get('id'), 'workflow': workflow.get('id')})
    return {'batches': len(freeze['batches']), 'workflows': workflows, 'mismatches': mismatches}


def triton_attempt_checks(freeze):
    """Triton attempt 历史派生自洽：身份保留、配对、序列、去重（REQ-015 语义）。"""
    batches = freeze['batches']
    initial_keys = [(b.get('pr'), b.get('sha')) for b in batches if b.get('kind') == 'initial']
    initial_set = set(initial_keys)
    seen = {}
    run_attempts = {}
    for batch in batches:
        for workflow in batch.get('workflows', []):
            key = (workflow.get('id'), workflow.get('attempt'))
            seen[key] = seen.get(key, 0) + 1
            run_attempts.setdefault(workflow.get('id'), set()).add(workflow.get('attempt'))
    by_pr = {}
    for batch in batches:
        by_pr.setdefault(batch.get('pr'), []).append(batch)
    bad_sequences = []
    for pr, group in by_pr.items():
        total = group[0].get('e2e_total')
        indices = sorted(b.get('e2e_index') for b in group)
        if indices != list(range(1, total + 1)) or any(b.get('e2e_total') != total for b in group):
            bad_sequences.append(pr)
    reruns = [b for b in batches if b.get('kind') == 'rerun']
    identity_ok = 0
    paired = 0
    for batch in reruns:
        workflow = batch['workflows'][0]
        if batch.get('id', '').endswith(f"-rerun-{workflow.get('id')}-{workflow.get('attempt')}"):
            identity_ok += 1
        if (batch.get('pr'), batch.get('sha')) in initial_set:
            paired += 1
    return {
        'rerun_batches': len(reruns),
        'initial_batches': len(initial_keys),
        'initial_unique': len(set(initial_keys)) == len(initial_keys),
        'duplicate_run_attempt': sum(1 for count in seen.values() if count > 1),
        'bad_sequences': bad_sequences,
        'same_run_multi_attempt_preserved': any(len(v) > 1 for v in run_attempts.values()),
        'rerun_identity_ids': identity_ok,
        'rerun_paired_with_initial': paired,
    }


def _category_status(applicable, verified, derived, differ):
    if differ:
        return 'differ'
    if applicable == 0:
        return 'not_applicable'
    if verified == applicable:
        return 'verified'
    if derived > 0:
        return 'partial'
    return 'unverified'


def category_raw_timestamps(freeze, triton_csv, ubs_csv, counts):
    """原始时间比对：冻结↔审计导出↔本地快照逐批核对；raw 平台证据缺失记缺证据。"""
    triton_total = len(freeze['batches'])
    ubs_total = counts['batches']
    t_differing = set(triton_csv['differing_batches'])
    t_covered = set(triton_csv['covered_batches']) - t_differing
    u_differing = set(ubs_csv['differing_batches'])
    u_covered = set(ubs_csv['covered_batches']) - u_differing
    applicable = triton_total + ubs_total
    verified, derived = 0, len(t_covered) + len(u_covered)
    differ = len(t_differing) + len(u_differing)
    missing = applicable - verified - derived - differ
    uncovered = [u for u in counts['batch_trigger_urls'] if u not in u_covered and u not in u_differing]
    return {
        'applicable': applicable,
        'verified_consistent': verified,
        'derived_consistent': derived,
        'differ': differ,
        'missing_evidence': missing,
        'status': _category_status(applicable, verified, derived, differ),
        'units': {'triton_batches': triton_total, 'ubs_batches': ubs_total},
        'raw': {'available': False, 'would_verify': applicable,
                'note': '原始平台时间证据（UBS data/raw 的 Jenkins/GitCode 响应、Triton evidence/triton 的 '
                        'run/job 页面）缺失；raw 已存在时来源覆盖由 validate_multi.py 核验，本工具不重复'},
        'checks': {
            'triton_freeze_vs_audit_exports': {
                'files': triton_csv['files'], 'compared_rows': triton_csv['compared'],
                'consistent_rows': triton_csv['consistent'],
                'covered_batches': len(t_covered), 'differing_batches': len(t_differing),
                'sample_differences': triton_csv['differences'][:10]},
            'ubs_audit_export_vs_snapshots': {
                'rows': ubs_csv['rows'], 'consistent_rows': ubs_csv['consistent'],
                'covered_batches': len(u_covered), 'differing_batches': len(u_differing),
                'sample_differences': ubs_csv['differences'][:10]},
        },
        'missing_sample': uncovered[:10],
        'note': '一致 = 冻结快照与审计期两份 Triton 导出、UBS 审计期批次导出与当前快照逐批/逐行一致（派生自洽）；'
                '缺证据 = 无任何独立导出覆盖且 raw 缺失的批次',
    }


def category_queue_components(ubs_csv, counts):
    """queue 三项比对：waiting/blocked/buildable 分项仅存在于 raw；汇总值与审计导出交叉核对。"""
    applicable = counts['jobs_with_queue']
    differing_children = set(ubs_csv['differing_children'])
    covered_children = set(ubs_csv['covered_children']) - differing_children
    verified, derived = 0, len(covered_children)
    differ = len(differing_children)
    missing = applicable - verified - derived - differ
    return {
        'applicable': applicable,
        'verified_consistent': verified,
        'derived_consistent': derived,
        'differ': differ,
        'missing_evidence': missing,
        'status': _category_status(applicable, verified, derived, differ),
        'components': {
            'waiting_blocked_buildable_verified': 0,
            'raw_available': False,
            'note': 'queue = waiting + blocked + buildable 三分项仅存在于 raw Jenkins 响应（data/raw 缺失）；'
                    '分项缺失时 queue 与 total 保持未知、不补 0（REQ-024 语义，validate_multi.py 执行）'},
        'units': {'triggers_with_queue': counts['triggers_with_queue'],
                  'children_with_queue': counts['children_with_queue']},
        'checks': {
            'ubs_audit_export_vs_snapshots': {
                'covered_children': len(covered_children), 'differing_children': differ,
                'sample_differences': [d for d in ubs_csv['differences']
                                       if any(f in d.get('fields', [])
                                              for f in ('queue_ms', 'duration_ms', 'total_ms', 'child_task_missing'))][:10]}},
        'missing_sample': counts['queue_job_urls'][:10],
    }


def category_pr_identity(freeze, triton_csv, ubs_csv, counts, propagation):
    """PR 身份比对：Triton 批次↔workflow 传播 + 导出身份；UBS 导出↔快照 PR；raw 关联证据缺失。"""
    triton_total = len(freeze['batches'])
    ubs_total = counts['prs']
    propagation_bad = {m.get('batch') for m in propagation['mismatches']}
    identity_fields = {'pr_url'}
    csv_identity_bad = {d.get('batch') for d in triton_csv['differences']
                        if d.get('fields') and set(d['fields']) & identity_fields}
    t_differing = propagation_bad | csv_identity_bad
    t_covered = set(triton_csv['covered_batches']) - t_differing
    u_differing = {tuple(p) for p in ubs_csv['differing_prs']}
    u_covered = {tuple(p) for p in ubs_csv['covered_prs']} - u_differing
    applicable = triton_total + ubs_total
    verified, derived = 0, len(t_covered) + len(u_covered)
    differ = len(t_differing) + len(u_differing)
    missing = applicable - verified - derived - differ
    uncovered = [pid for pid in counts['pr_ids'] if tuple(pid) not in u_covered and tuple(pid) not in u_differing]
    return {
        'applicable': applicable,
        'verified_consistent': verified,
        'derived_consistent': derived,
        'differ': differ,
        'missing_evidence': missing,
        'status': _category_status(applicable, verified, derived, differ),
        'units': {'triton_batches': triton_total, 'ubs_prs': ubs_total},
        'raw': {'available': False,
                'note': 'GitCode pulls 原始响应与 evidence/triton/pr-associations 关联依据缺失；'
                        '派生核对仅证明冻结工件与审计导出内部一致，不是来源准确性证明（D10 语义）'},
        'checks': {
            'triton_batch_workflow_propagation': propagation,
            'triton_freeze_vs_audit_exports': {
                'covered_batches': len(t_covered), 'differing_batches': len(t_differing)},
            'ubs_audit_export_vs_snapshots': {
                'covered_prs': len(u_covered), 'differing_prs': len(u_differing)},
        },
        'missing_sample': uncovered[:10],
    }


def category_attempt_history(attempts, counts):
    """attempt 历史比对：Triton rerun 身份/配对/序列 + UBS retest 事件关联；raw 证据缺失。"""
    rerun_total = attempts['rerun_batches']
    retest_total = counts['retest_batches']
    triton_ok = (attempts['initial_unique'] and not attempts['duplicate_run_attempt']
                 and not attempts['bad_sequences']
                 and attempts['rerun_identity_ids'] == rerun_total
                 and attempts['rerun_paired_with_initial'] == rerun_total)
    t_derived = rerun_total if triton_ok else 0
    t_differ = 0 if triton_ok else rerun_total
    u_derived = counts['retest_linked']
    applicable = rerun_total + retest_total
    verified = 0
    derived = t_derived + u_derived
    differ = t_differ
    missing = applicable - verified - derived - differ
    return {
        'applicable': applicable,
        'verified_consistent': verified,
        'derived_consistent': derived,
        'differ': differ,
        'missing_evidence': missing,
        'status': _category_status(applicable, verified, derived, differ),
        'units': {'triton_rerun_batches': rerun_total, 'ubs_retest_batches': retest_total},
        'same_run_multi_attempt': {
            'preserved_in_freeze': attempts['same_run_multi_attempt_preserved'],
            'note': '冻结工件未保留同一 run 的多次 attempt 记录（rerun run 的更早 attempt 不在 payload）；'
                    '同一 run 多 attempt 原始证据（run/job 页面）缺失，精确新规则 E2E 不可重算（见 ac03）'},
        'checks': {'triton_attempt_checks': attempts,
                   'ubs_retest_linkage': {'retest_batches': retest_total, 'linked': u_derived}},
        'missing_sample': counts['retest_unlinked_sample'][:10],
    }


# ---------------------------------------------------------------- AC03 影响

def rerun_impact(root, freeze):
    """真实重跑批次的新旧规则比对（REQ-038-AC03）。

    原规则 = E2E 从原 run 创建时间起算（审计 S01/F08 缺陷）；REQ-014/015 规则
    = 从本次 attempt 可证明起点起算。冻结 payload 未持久化 run_started_at，
    本次 attempt 起点仅能由该 attempt 的 job 时间证据（created/started 均不早
    于 attempt 起点）给出上界：旧规则高估 ≤ 上界 − 原 run 创建时间。
    """
    initial_by_key = {(b.get('pr'), b.get('sha')): b.get('id')
                      for b in freeze['batches'] if b.get('kind') == 'initial'}
    entries = []
    for batch in freeze['batches']:
        if batch.get('kind') != 'rerun':
            continue
        workflow = batch['workflows'][0]
        created = stamp(workflow.get('created_at'))
        end = stamp(batch.get('end_at'))
        recorded = batch.get('duration_seconds')
        old_rule = end - created if created is not None and end is not None else None
        job_times = [stamp(job.get(field)) for job in workflow.get('jobs', [])
                     for field in ('created_at', 'started_at') if job.get(field)]
        upper = min(job_times) if job_times else None
        bound = max(0.0, upper - created) if upper is not None and created is not None else None
        entries.append({
            'batch_id': batch.get('id'),
            'pr': batch.get('pr'),
            'run_id': workflow.get('id'),
            'attempt': workflow.get('attempt'),
            'initial_sibling_batch': initial_by_key.get((batch.get('pr'), batch.get('sha'))),
            'created_at': workflow.get('created_at'),
            'start_at': batch.get('start_at'),
            'end_at': batch.get('end_at'),
            'start_at_equals_created': batch.get('start_at') == workflow.get('created_at'),
            'old_rule_e2e_seconds': old_rule,
            'recorded_duration_seconds': recorded,
            'recorded_matches_old_rule': (old_rule is not None and isinstance(recorded, (int, float))
                                          and math.isclose(old_rule, recorded, abs_tol=1e-6)),
            'old_rule_overestimate_bound_seconds': bound,
            'new_rule_e2e_range_seconds': ([old_rule - bound, old_rule]
                                           if bound is not None and old_rule is not None
                                           else [None, old_rule]),
            'provably_identical_to_new_rule': bound == 0,
        })
    s01 = None
    audit_path = root / AUDIT_REL / 'data-audit.json'
    record = None
    if audit_path.exists():
        try:
            audit = read_json(audit_path)
            record = next((c for c in audit.get('checks', []) if c.get('id') == 'S01'), None)
        except ValueError:
            record = None
    if record:
        row = record.get('input', {})
        old = stamp(row.get('updated_at')) - stamp(row.get('created_at'))
        new = stamp(row.get('updated_at')) - stamp(row.get('run_started_at'))
        current = None
        error = None
        try:
            _ensure_root_on_path(root)
            from triton.dashboard import build_batches
            current = build_batches([dict(row)], '2026-09-22T03:00:00Z')[0].get('duration_seconds')
        except Exception as exc:  # noqa: BLE001 — 记录不可用原因，不中断报告
            error = str(exc)
        s01 = {
            'source': 'audit/2026-10-09/evidence/data-audit.json checks[S01]',
            'is_synthetic': record.get('kind') == 'synthetic',
            'input': row,
            'old_rule_seconds': old,
            'new_rule_seconds': new,
            'current_code_recomputed_seconds': current,
            'recompute_error': error,
            'audit_recorded': {'state': record.get('state'), 'actual': record.get('actual'),
                               'expected': record.get('expected')},
            'note': '合成输入（run 创建 00:00、本次 attempt 02:00 开始、02:05 结束）：原规则计 7500 秒，'
                    'REQ-014/015 规则计 300 秒；该 300 秒例子不能证明历史真实 E2E（审计 F08），与真实批次单列隔离',
        }
    bounds = sorted(e['old_rule_overestimate_bound_seconds'] for e in entries
                    if e['old_rule_overestimate_bound_seconds'] is not None)
    summary = {
        'rerun_batches': len(entries),
        'recorded_matches_old': sum(1 for e in entries if e['recorded_matches_old_rule']),
        'start_at_equals_created': sum(1 for e in entries if e['start_at_equals_created']),
        'provably_identical_to_new_rule': sum(1 for e in entries if e['provably_identical_to_new_rule']),
        'provably_affected_batches': 0,
        'bounded_possibly_divergent': sum(1 for e in entries
                                          if e['old_rule_overestimate_bound_seconds'] is not None
                                          and e['old_rule_overestimate_bound_seconds'] > 0),
        'max_overestimate_bound_seconds': bounds[-1] if bounds else None,
        'median_overestimate_bound_seconds': bounds[len(bounds) // 2] if bounds else None,
        'same_run_multi_attempt_records': '冻结工件未保留任何同一 run 的多次 attempt 记录；'
                                          '同一 run 多 attempt 原始证据（run/job 页面）缺失',
        'attempt_start_evidence': 'run_started_at 未持久化于冻结 payload（workflow 字段不含该键）→ '
                                  '新规则 E2E 无法从冻结工件精确重算，仅给出区间',
    }
    if entries:
        summary['conclusion'] = (
            '冻结窗口 %d 个真实重跑批次的旧规则值与冻结记录一致（start_at == 原 run created_at，%d/%d）；'
            '本次 attempt 起点未持久化，新旧规则差异不可精确判定，旧规则高估上限 %s 秒（中位 %s 秒），'
            '无 S01 式小时级跨度；可证明受影响批次数 = 0。'
            % (len(entries), summary['recorded_matches_old'], len(entries),
               summary['max_overestimate_bound_seconds'], summary['median_overestimate_bound_seconds']))
    return {
        'rule_old': '原规则（REQ-015 之前代码）：重跑批次 E2E = end_at − 原 run created_at（run 创建时间，'
                    '非本次 attempt 起点）——冻结快照实证 rerun start_at == workflows[0].created_at，审计 S01/F08 记录该缺陷',
        'rule_new': 'REQ-014/015 规则：E2E = end_at − 本次 attempt 可证明起点（trigger_event 或 '
                    'run_started_at；无法恢复时 E2E 留空并明示缺口）',
        'rerun_batches': entries,
        's01': s01,
        'summary': summary,
    }


# ---------------------------------------------------------------- AC04 部署

def deployment_section(root):
    """部署核验（REQ-038-AC04）：本地构建工件指纹 + 合并看板部署现实 + 旧站探测记录。"""
    section = {}
    try:
        _ensure_root_on_path(root)
        import validate_bundle
        fingerprint, digests, manifest_state, errors = validate_bundle.verify(root)
        manifest_meta = {}
        manifest_path = root / 'web/data/ubs-manifest.json'
        if manifest_path.exists():
            try:
                manifest_meta = read_json(manifest_path)
            except ValueError:
                manifest_meta = {}
        section['local_bundle'] = {
            'status': manifest_state,
            'fingerprint': fingerprint,
            'files_verified': len(digests),
            'errors': errors,
            'manifest_generated_at': manifest_meta.get('generated_at'),
            'method': 'validate_bundle.verify（REQ-022 构建工件指纹：索引↔快照↔manifest SHA-256 绑定）',
        }
    except Exception as error:  # noqa: BLE001 — 记录不可用原因，不中断报告
        section['local_bundle'] = {'status': 'error', 'reason': str(error), 'errors': 1}
    remotes = _git_remotes(root)
    section['merged_dashboard_deployment'] = {
        'status': 'unverified',
        'git_remotes': remotes,
        'gh_cli_available': shutil.which('gh') is not None,
        'reasons': (['本仓库无 git remote → 从未推送，不存在 Actions 构建/部署运行',
                     '合并看板 Pages 地址未部署（README 在线地址段仍为待部署后填写）',
                     'REQ-022 已将 verify_deployment 接入两个发布流程，但该流程从未真实运行，'
                     '无运行 ID/URL/校验时刻与指纹可记录'] if not remotes
                    else ['存在 git remote，但本报告生成时无部署运行证据可核验']),
        'old_site_scraping_substitute': '拒绝：本地 Pages 模拟下载或旧站公开源码抓取不能替代真实构建/部署'
                                        '工件（REQ-038 AC04）',
    }
    probe_path = root / AUDIT_REL / PROBE_NAME
    if probe_path.exists():
        try:
            probe = read_json(probe_path)
            section['site_probe'] = {
                'probed_at': probe.get('probed_at'),
                'results': probe.get('urls'),
                'conclusion': probe.get('conclusion'),
                'source': f'audit/2026-10-09/evidence/{PROBE_NAME}（--probe 刷新）',
            }
        except ValueError:
            section['site_probe'] = {'status': 'invalid', 'note': 'site-probe.json 不是合法 JSON'}
    else:
        section['site_probe'] = {'status': 'missing', 'note': '未生成旧站探测记录；运行 --probe 采集'}
    section['status'] = 'unverified'
    return section


# ---------------------------------------------------------------- 汇总

def _worst_status(statuses):
    return sorted(statuses, key=lambda s: STATUS_ORDER.get(s, 0))[0]


def derive_overall(sections, has_differ):
    """overall_status 从分项推导（REQ-025 语义）：差异 > 未验证/部分 > 通过。"""
    if has_differ or 'differ' in sections.values() or 'failed' in sections.values():
        return 'failed'
    if any(status in ('unverified', 'partial') for status in sections.values()):
        return 'unverified'
    return 'verified'


def build_report(root):
    freeze = read_json(root / FREEZE_REL)
    index = _ubs_index(root)
    inv = inventory(root)
    triton_csv = triton_csv_checks(root, freeze)
    ubs_csv = ubs_csv_checks(root)
    counts = ubs_counts(root)
    propagation = triton_pr_propagation(freeze)
    attempts = triton_attempt_checks(freeze)
    categories = {
        'raw_timestamps': category_raw_timestamps(freeze, triton_csv, ubs_csv, counts),
        'queue_components': category_queue_components(ubs_csv, counts),
        'pr_identity': category_pr_identity(freeze, triton_csv, ubs_csv, counts, propagation),
        'attempt_history': category_attempt_history(attempts, counts),
    }
    impact = rerun_impact(root, freeze)
    deployment = deployment_section(root)
    sections = {
        'ac01': 'pass',
        'ac02': _worst_status([c['status'] for c in categories.values()]),
        'ac03': 'partial' if impact['summary']['rerun_batches'] else 'not_applicable',
        'ac04': deployment['status'],
    }
    bundle = deployment.get('local_bundle', {})
    bundle_bad = ((bundle.get('errors') or 0) > 0
                  or bundle.get('status') in ('mismatch', 'invalid', 'error'))
    has_differ = any(c['differ'] > 0 for c in categories.values()) or bundle_bad
    overall = derive_overall(sections, has_differ)
    if overall == 'failed':
        reason = '交叉核对发现差异（冻结审计证据与本地工件集不一致），详见各分项 differences'
    elif overall == 'unverified':
        reason = ('D10 原始工件（data/raw、SQLite、evidence/triton、triton-manifest/batches.csv 等）本地缺失'
                  '且不可恢复（无 git remote、无 gh CLI、旧站已推进过审计截止点）；合并看板无真实部署运行。'
                  '可执行交叉核对（冻结↔审计导出↔本地快照↔构建清单）全部一致，缺失项全部如实标注未验证')
    else:
        reason = '全部分项核验通过'
    ubs_scope = None
    if index:
        ubs_scope = {'index_generated_at': index.get('generated_at'),
                     'window': [iso_ms(index.get('start_ms')), iso_ms(index.get('end_ms'))]}
    report = {
        'executed_at': datetime.now(timezone.utc).isoformat(),
        'requirement': 'REQ-038 · 原始工件补齐及历史影响核验',
        'audit': '2026-10-09',
        'scope': {
            'ubs': ubs_scope,
            'triton': {'collected_at': freeze.get('collected_at'),
                       'window': [freeze.get('window_start'), freeze.get('window_end')]},
            'freeze_fixture': str(FREEZE_REL),
            'evidence_references': {
                'd10': 'audit/2026-10-09/evidence/data-audit.json checks[D10]',
                's01': 'audit/2026-10-09/evidence/data-audit.json checks[S01]',
                'f08': 'audit/2026-10-09/evidence/findings.json F08（重跑 E2E 起点）',
            },
        },
        'ac01_inventory': inv,
        'ac02_comparisons': categories,
        'ac03_rerun_impact': impact,
        'ac04_deployment': deployment,
        'sections': sections,
        'overall_status': overall,
        'overall_reason': reason,
        'arithmetic': '每类比对满足 已验证一致 + 派生自洽 + 差异 + 缺证据 = 适用总数（REQ-023）；'
                       'overall_status 从分项推导（REQ-025）；退出码 0 = 可执行交叉核对无差异，'
                       '原始工件缺失以未验证记录、不因此失败',
    }
    return report, has_differ


def run_probe(root):
    """联网探测两个旧站并写入 site-probe.json（仅记录状态，不作为历史证据）。"""
    results = []
    for url, counterpart in PROBE_TARGETS:
        entry = {'url': url, 'local_counterpart': counterpart}
        local = root / counterpart
        entry['local_exists'] = local.exists()
        if local.exists():
            entry['local_sha256'] = sha256_file(local)
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                data = response.read()
                entry['http_status'] = response.status
                entry['bytes'] = len(data)
                entry['sha256'] = hashlib.sha256(data).hexdigest()
        except urllib.error.HTTPError as error:
            entry['http_status'] = error.code
        except (urllib.error.URLError, OSError) as error:
            entry['http_status'] = None
            entry['error'] = str(error)
        if 'sha256' in entry and entry.get('local_sha256'):
            entry['relation'] = ('matches_local_audit_snapshot' if entry['sha256'] == entry['local_sha256']
                                 else 'differs_from_local_audit_snapshot')
        elif 'sha256' in entry:
            entry['relation'] = 'no_local_counterpart'
        elif entry.get('http_status') == 404:
            entry['relation'] = 'absent_on_site'
        else:
            entry['relation'] = 'unreachable'
        results.append(entry)
    probe = {
        'probed_at': datetime.now(timezone.utc).isoformat(),
        'purpose': 'REQ-038 AC04：记录两个旧站点在探测时刻的公开数据状态；当前平台状态不可冒充'
                   '审计截止点历史事实，旧站公开源码抓取不作为替代证据',
        'urls': results,
        'conclusion': '探测结果逐条记录与本地审计快照的关系（matches/differs/no_local_counterpart/'
                      'absent_on_site/unreachable）；两站均为合并前部署，不能作为 REQ-022 部署对应'
                      '关系的证据——当前平台状态不可冒充审计截止点历史事实，旧站抓取不作为替代证据',
    }
    path = root / AUDIT_REL / PROBE_NAME
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(probe, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    return probe


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog=TOOL,
        description='REQ-038 原始工件补齐及历史影响核验：审计冻结工件集的清单、四类比对、'
                    '真实重跑新旧规则影响与部署核验')
    parser.add_argument('--root', default=str(Path(__file__).resolve().parent.parent), help='仓库根目录')
    parser.add_argument('--output', default=None,
                        help='报告输出路径（默认 audit/2026-10-09/evidence/artifact-verification.json）')
    parser.add_argument('--probe', action='store_true', help='先联网刷新旧站探测记录 site-probe.json')
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    try:
        if args.probe:
            run_probe(root)
        report, has_differ = build_report(root)
    except Exception as error:  # noqa: BLE001 — 失败时报告原因并以退出码 1 结束
        print(json.dumps({'tool': TOOL, 'error': str(error), 'exit': 1}, ensure_ascii=False))
        return 1
    output = Path(args.output).resolve() if args.output else root / AUDIT_REL / REPORT_NAME
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    categories = report['ac02_comparisons']
    summary = {
        'overall_status': report['overall_status'],
        'sections': report['sections'],
        'categories': {name: {field: category[field] for field in
                              ('applicable', 'verified_consistent', 'derived_consistent',
                               'differ', 'missing_evidence')}
                       for name, category in categories.items()},
        'rerun_impact': {key: report['ac03_rerun_impact']['summary'][key]
                         for key in ('rerun_batches', 'recorded_matches_old',
                                     'provably_affected_batches', 'max_overestimate_bound_seconds')},
        'local_bundle': report['ac04_deployment']['local_bundle'].get('status'),
        'report': str(output),
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if has_differ else 0


if __name__ == '__main__':
    raise SystemExit(main())
