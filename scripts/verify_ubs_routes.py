#!/usr/bin/env python3
"""REQ-047：UBS 全部视图与旧链接可达性保持验证。

独立镜像 web/router.js 契约（DEFAULT_HASH/LEGACY 别名表、partsOf 安全
解码、parseHash/toHash/resolve/keepPRPage）；枚举主要视图（九单仓 + 九
质量页 + 跨仓总览 + Triton + 口径 = 2N+3）；对旧链接规范化
（#repositories→#ubs、#overview/#prs→ubs-engine 单仓、#quality→
ubs-engine 质量、#method）、既有 #repo/NAME 与 method 别名、未知路由
默认回退与编码边界构造完整哈希矩阵，与 router.js 单次 node 调用逐项
核对 resolve/parseHash/toHash/keepPRPage；锁定 app.js 视图接线契约
（路由回退、视图名/导航高亮/标题/面包屑派生、视图容器与主区切换、
快照按仓隔离、未知仓库「未找到仓库」提示与主区隐藏、hashchange 启动
链）；逐仓核验单仓与质量深链接的规范哈希恒等（直接打开走 pushState
不替换）、往返一致与数据归属（快照 meta.repository 与索引一致）；指纹
匹配审计冻结输入时回放 U01（九仓完整显示）/U10-repositories/
U10-overview/U10-prs（旧链接目标）/U11（未知仓库提示，契约锁定）；
输入更新后基线比对记 not_applicable，矩阵与契约检查照常执行。
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
from urllib.parse import unquote

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_ubs_semantics as vsm  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_REL = Path('audit/2026-10-09/evidence')
REPORT_NAME = 'ubs-routes-evidence.json'

AUDIT_BASELINE_FINGERPRINT = vsm.AUDIT_BASELINE_FINGERPRINT
SHANGHAI = timezone(timedelta(hours=8))

DEFAULT_HASH = '#ubs'
LEGACY = {'repositories': '#ubs',
          'overview': '#ubs/repo/ubs-engine',
          'prs': '#ubs/repo/ubs-engine',
          'quality': '#ubs/repo/ubs-engine/quality',
          'method': '#method'}

_JS_UNESCAPED = frozenset(
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'
    "-_.!~*'()")


def stamp():
    return datetime.now(tz=SHANGHAI).isoformat(timespec='seconds')


def _decode(part):
    """镜像 router.js decode：解码失败回退原文（JS try/catch 语义）。"""
    try:
        return unquote(part, errors='strict')
    except UnicodeDecodeError:
        return part


def _encode_component(value):
    """镜像 JS encodeURIComponent 的未转义集合与 UTF-8 十六进制。"""
    out = []
    for ch in value:
        if ch in _JS_UNESCAPED:
            out.append(ch)
        else:
            out.append(''.join(f'%{b:02X}' for b in ch.encode('utf-8')))
    return ''.join(out)


def _strip_hash(hash_value):
    """镜像 String(hash==null?'':hash).replace(/^#/,'')。"""
    raw = '' if hash_value is None else str(hash_value)
    return raw[1:] if raw.startswith('#') else raw


def own_parts_of(hash_value):
    """镜像 partsOf：去 #、按 / 拆分、过滤空段并安全解码。"""
    return [_decode(p) for p in _strip_hash(hash_value).split('/') if p]


def own_parse_hash(hash_value):
    """镜像 parseHash：triton/method/ubs 三域，repo 段带 quality 子视图。"""
    parts = own_parts_of(hash_value)
    if parts[:1] == ['triton']:
        return {'domain': 'triton'}
    if parts[:1] == ['method']:
        return {'domain': 'method'}
    if parts[:1] == ['ubs']:
        if len(parts) > 2 and parts[1] == 'repo':
            if len(parts) > 3 and parts[3] == 'quality':
                return {'domain': 'ubs', 'repo': parts[2], 'sub': 'quality'}
            return {'domain': 'ubs', 'repo': parts[2]}
        return {'domain': 'ubs'}
    return None


def own_to_hash(route):
    """镜像 toHash：无路由/无仓标识回默认，quality 子视图追加后缀。"""
    if not route:
        return DEFAULT_HASH
    domain = route.get('domain')
    if domain in ('triton', 'method'):
        return '#' + domain
    if domain == 'ubs' and route.get('repo'):
        suffix = '/quality' if route.get('sub') == 'quality' else ''
        return '#ubs/repo/' + _encode_component(route['repo']) + suffix
    return DEFAULT_HASH


def own_resolve(hash_value):
    """镜像 resolve：空→默认；#repo/NAME 与 method 别名；LEGACY 表回退。"""
    raw = _strip_hash(hash_value)
    parts = [p for p in raw.split('/') if p]
    if not parts:
        return DEFAULT_HASH
    head = _decode(parts[0])
    if head == 'repo' and len(parts) > 1:
        if len(parts) > 2 and parts[2] == 'method':
            return '#method'
        sub = 'quality' if len(parts) > 2 and parts[2] == 'quality' else None
        return own_to_hash({'domain': 'ubs', 'repo': _decode(parts[1]),
                            'sub': sub})
    if head in ('ubs', 'triton', 'method'):
        route = own_parse_hash(raw)
        return own_to_hash(route) if route is not None else DEFAULT_HASH
    return LEGACY.get(head, DEFAULT_HASH)


def own_keep_pr_page(prev_repo, view, repo):
    """镜像 keepPRPage：仅仓库视图跨仓切换时重置分页。"""
    return view not in ('ubs-repo', 'ubs-quality') or repo == prev_repo


def own_view_name(route):
    """镜像 applyRoute 视图名派生：ubs-repo/ubs-quality/ubs/域。"""
    if not route:
        return None
    domain = route.get('domain')
    if domain == 'ubs':
        if route.get('repo'):
            return ('ubs-quality' if route.get('sub') == 'quality'
                    else 'ubs-repo')
        return 'ubs'
    return domain


def own_nav_target(route):
    """镜像侧栏导航高亮目标：ubs 跨仓对应 ubs-overview。"""
    name = own_view_name(route)
    return 'ubs-overview' if name == 'ubs' else name


def own_views(index, snapshots):
    """枚举主要视图：每仓单仓+质量两页，加跨仓总览/Triton/口径。"""
    views = []
    for entry in index['repositories']:
        name = entry['name']
        snap = snapshots.get(name)
        attribution = bool(
            snap and snap['meta']['repository'] == entry['repository'])
        for kind, route in (
                ('repo', {'domain': 'ubs', 'repo': name}),
                ('quality', {'domain': 'ubs', 'repo': name,
                             'sub': 'quality'})):
            view_hash = own_to_hash(route)
            views.append({
                'repo': name, 'kind': kind, 'hash': view_hash,
                'view_name': own_view_name(route),
                'nav_target': own_nav_target(route),
                'roundtrip_ok':
                    own_parse_hash(view_hash) == route,
                'canonical_ok': own_resolve(view_hash) == view_hash,
                'snapshot_attribution_ok': attribution,
                'prs': len(snap['prs']) if snap else None})
    for domain in ('ubs', 'triton', 'method'):
        route = {'domain': domain}
        view_hash = own_to_hash(route)
        views.append({
            'repo': None, 'kind': f'global-{domain}', 'hash': view_hash,
            'view_name': own_view_name(route),
            'nav_target': own_nav_target(route),
            'roundtrip_ok': own_parse_hash(view_hash) == route,
            'canonical_ok': own_resolve(view_hash) == view_hash,
            'snapshot_attribution_ok': True, 'prs': None})
    return views


def build_hash_matrix(view_hashes):
    """旧链接/别名/未知路由/编码边界完整矩阵（视图哈希之外补充）。"""
    matrix = list(view_hashes)
    matrix += ['#repositories', '#overview', '#prs', '#quality', '#method']
    matrix += ['#repo/ubs-engine', '#repo/ubs-comm/quality',
               '#repo/ubs-engine/method', '#repo/NoSuchRepo', '#repo',
               '#repo/ubs-engine/extra']
    matrix += ['#xyz', '#UBS', '#ubs/repo', '#ubs/unknown',
               '#ubs/repo/unknown-repo',
               '#ubs/repo/ubs-engine/quality/extra',
               '#ubs/repo/ubs-engine/xyz',
               '#ubs/repo/ubs-engine/QUALITY',
               '#ubs//repo//ubs-engine', '#ubs/repo//',
               '#triton/extra', '#method/extra', '#triton/', '#method/',
               '#', '#/', '##ubs', '', None,
               '#ubs/repo/%E4%B8%AD%E6%96%87', '#ubs/repo/%zz',
               '#ubs/repo/%E4%B8', '#repo/%E4%B8%AD%E6%96%87/quality',
               '#%E4%B8%AD%E6%96%87']
    return list(dict.fromkeys(matrix))


TO_HASH_MATRIX = [
    None, {}, {'domain': 'ubs'}, {'domain': 'ubs', 'repo': 'ubs-engine'},
    {'domain': 'ubs', 'repo': 'ubs-engine', 'sub': 'quality'},
    {'domain': 'ubs', 'repo': 'ubs-engine', 'sub': 'xyz'},
    {'domain': 'ubs', 'repo': '中文'},
    {'domain': 'ubs', 'sub': 'quality'},
    {'domain': 'triton'}, {'domain': 'method'}, {'domain': 'other'},
    {'domain': 'ubs', 'repo': 'a b'}, {'domain': 'ubs', 'repo': 'a*b'},
]

KEEP_PR_PAGE_MATRIX = [
    ['ubs-engine', 'ubs-repo', 'ubs-engine'],
    ['ubs-engine', 'ubs-repo', 'ubs-comm'],
    ['ubs-engine', 'ubs-quality', 'ubs-engine'],
    ['ubs-engine', 'ubs-quality', 'ubs-comm'],
    ['ubs-engine', 'ubs', 'ubs-comm'],
    ['ubs-engine', 'triton', 'ubs-comm'],
    ['ubs-engine', 'method', 'ubs-engine'],
    [None, 'ubs-repo', 'ubs-engine'],
]

# ------------------------------------------------------------- node 交叉核对

_NODE_SCRIPT = r"""'use strict';
const fs = require('fs');
const Router = require(process.argv[2]);
const payload = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const out = {
  resolve: payload.hash_matrix.map(h => Router.resolve(h)),
  parse: payload.hash_matrix.map(h => Router.parseHash(h)),
  to_hash: payload.to_hash_matrix.map(r => Router.toHash(r)),
  keep_pr_page: payload.keep_matrix.map(
    x => Router.keepPRPage(x[0], x[1], x[2])),
};
fs.writeFileSync(process.argv[4], JSON.stringify(out));
"""


def _node_check(root, hash_matrix, to_hash_matrix, keep_matrix):
    """单次 node 调用：resolve/parseHash/toHash/keepPRPage 全矩阵核对。"""
    payload = {'hash_matrix': hash_matrix,
               'to_hash_matrix': to_hash_matrix,
               'keep_matrix': keep_matrix}
    with tempfile.TemporaryDirectory() as tmp:
        payload_path = os.path.join(tmp, 'payload.json')
        script_path = os.path.join(tmp, 'check.cjs')
        result_path = os.path.join(tmp, 'result.json')
        with open(payload_path, 'w', encoding='utf-8') as fh:
            json.dump(payload, fh, ensure_ascii=False)
        with open(script_path, 'w', encoding='utf-8') as fh:
            fh.write(_NODE_SCRIPT)
        proc = subprocess.run(
            ['node', script_path, str(root / 'web/router.js'),
             payload_path, result_path],
            capture_output=True, text=True, timeout=300)
        if proc.returncode != 0:
            return {'status': 'error', 'stderr': proc.stderr[-2000:]}
        with open(result_path, encoding='utf-8') as fh:
            return json.load(fh)


# --------------------------------------------------------------- 源码契约

ROUTER_CONTRACTS = [
    ('default_hash', "const DEFAULT_HASH='#ubs';"),
    ('legacy_map',
     "const LEGACY={repositories:'#ubs',overview:'#ubs/repo/ubs-engine',"
     "prs:'#ubs/repo/ubs-engine',quality:'#ubs/repo/ubs-engine/quality',"
     "method:'#method'};"),
    ('decode_safe',
     'function decode(part){try{return decodeURIComponent(part)}'
     'catch{return part}}'),
    ('parts_of',
     "String(hash==null?'':hash).replace(/^#/,'').split('/')"
     '.filter(Boolean).map(decode)'),
    ('parse_triton', "if(parts[0]==='triton')return {domain:'triton'};"),
    ('parse_method', "if(parts[0]==='method')return {domain:'method'};"),
    ('parse_repo_quality',
     "if(parts[1]==='repo'&&parts[2])return parts[3]==='quality'"
     "?{domain:'ubs',repo:parts[2],sub:'quality'}"
     ":{domain:'ubs',repo:parts[2]};"),
    ('parse_ubs_cross', "return {domain:'ubs'};"),
    ('to_hash_null', 'if(!route)return DEFAULT_HASH;'),
    ('to_hash_domains',
     "if(route.domain==='triton'||route.domain==='method')"
     "return '#'+route.domain;"),
    ('to_hash_repo',
     "'#ubs/repo/'+encodeURIComponent(route.repo)"
     "+(route.sub==='quality'?'/quality':'')"),
    ('resolve_empty', 'if(!parts.length)return DEFAULT_HASH;'),
    ('resolve_repo_alias',
     "if(head==='repo'&&parts[1])return parts[2]==='method'?'#method':"
     "toHash({domain:'ubs',repo:decode(parts[1]),"
     "sub:parts[2]==='quality'?'quality':null});"),
    ('resolve_known_heads',
     "if(head==='ubs'||head==='triton'||head==='method')"
     '{const route=parseHash(raw);return route?toHash(route):DEFAULT_HASH}'),
    ('resolve_legacy_default', 'return LEGACY[head]||DEFAULT_HASH;'),
    ('keep_pr_page',
     "function keepPRPage(prevRepo,view,repo){return !(view==='ubs-repo'"
     "||view==='ubs-quality')||repo===prevRepo}"),
    ('router_export', 'const api={parseHash,toHash,resolve,keepPRPage};'),
]

APP_CONTRACTS = [
    ('navigate_resolve', 'const canonical=Router.resolve(hash);'),
    ('navigate_push_replace',
     "if(hash===canonical)history.pushState(null,'',canonical);"
     "else history.replaceState(null,'',canonical);"),
    ('navigate_apply', 'applyRoute(Router.parseHash(canonical));'),
    ('apply_route_fallback',
     "const r=route&&route.domain?route:{domain:'ubs'};"),
    ('apply_route_view',
     "view=ubs?(repo?(quality?'ubs-quality':'ubs-repo'):'ubs'):domain;"),
    ('apply_route_current_repo', 'if(repo)currentRepository=r.repo;'),
    ('apply_route_snapshot_isolated',
     "snapshot=repositorySnapshots[currentRepository]||null;"),
    ('view_containers',
     "for(const id of ['ubs-view','ubs-repo-view','triton-view',"
     "'method-view'])$(id).hidden=id!==(ubs?(repo?'ubs-repo-view':"
     "'ubs-view'):domain+'-view');"),
    ('nav_highlight',
     "a.dataset.nav===(ubs?(repo?(quality?'ubs-quality':'ubs-repo')"
     ":'ubs-overview'):domain)"),
    ('repo_quality_toggle',
     "if(repo){$('repoMain').hidden=quality;$('quality').hidden=!quality;}"),
    ('title_repo',
     "(cross?'九仓 PR 工程效率':currentRepository)+' · PR 工程效率'"),
    ('crumb_repo',
     "['监控中心','openEuler UBS',currentRepository,"
     "...(quality?['数据质量']:[])]"),
    ('unknown_repo_notice', ":'未找到仓库'):''"),
    ('unknown_repo_loading',
     "'该仓库尚未获取数据，请查看采集状态后运行采集命令。'"),
    ('unknown_repo_hide_main',
     "for(const id of ['repoMain','quality'])$(id).hidden=true"),
    ('unknown_repo_footer',
     "currentRepository+(entry?.status==='failed'?' · 快照读取失败'"
     ":' · 未获取数据')"),
    ('hashchange_boot',
     "window.addEventListener('hashchange',()=>navigate(location.hash));"
     'navigate(location.hash);load();'),
]


def _check_source_contracts(root):
    router = (root / 'web/router.js').read_text(encoding='utf-8')
    app = (root / 'web/app.js').read_text(encoding='utf-8')
    missing = []
    for name, needle in ROUTER_CONTRACTS:
        if needle not in router:
            missing.append(f'router.js:{name}')
    for name, needle in APP_CONTRACTS:
        if needle not in app:
            missing.append(f'app.js:{name}')
    return {'checked': len(ROUTER_CONTRACTS) + len(APP_CONTRACTS),
            'missing': missing}


# ------------------------------------------------------------- 基线回放

def _replay_baseline(index, snapshots, contracts):
    """指纹匹配审计冻结输入时回放 U01/U10-*/U11 与 AC02 别名。"""
    missing = set(contracts['missing'])
    repos = index['repositories']
    with_snapshot = [e for e in repos if e.get('snapshot')]
    u11_locks = {'app.js:unknown_repo_notice',
                 'app.js:unknown_repo_loading',
                 'app.js:unknown_repo_hide_main',
                 'app.js:unknown_repo_footer',
                 'app.js:apply_route_snapshot_isolated'}
    checks = {
        'U01_nine_repos_all_views': {
            'repos': len(repos), 'snapshots': len(with_snapshot),
            'views': 2 * len(repos) + 3,
            'expected': {'repos': 9, 'snapshots': 9, 'views': 21},
            'passed': (len(repos) == 9 and len(with_snapshot) == 9
                       and 2 * len(repos) + 3 == 21)},
        'U10-repositories_legacy': {
            'resolved': own_resolve('#repositories'), 'expected': '#ubs',
            'passed': own_resolve('#repositories') == '#ubs'},
        'U10-overview_legacy': {
            'resolved': own_resolve('#overview'),
            'expected': '#ubs/repo/ubs-engine',
            'passed':
                own_resolve('#overview') == '#ubs/repo/ubs-engine'},
        'U10-prs_legacy': {
            'resolved': own_resolve('#prs'),
            'expected': '#ubs/repo/ubs-engine',
            'passed': own_resolve('#prs') == '#ubs/repo/ubs-engine'},
        'AC02_quality_legacy': {
            'resolved': own_resolve('#quality'),
            'expected': '#ubs/repo/ubs-engine/quality',
            'passed':
                own_resolve('#quality') == '#ubs/repo/ubs-engine/quality'},
        'AC02_repo_alias': {
            'resolved': own_resolve('#repo/ubs-engine'),
            'expected': '#ubs/repo/ubs-engine',
            'passed':
                own_resolve('#repo/ubs-engine') == '#ubs/repo/ubs-engine'},
        'AC02_method_alias': {
            'resolved': own_resolve('#repo/ubs-engine/method'),
            'expected': '#method',
            'passed': own_resolve('#repo/ubs-engine/method') == '#method'},
        'U11_unknown_repo_notice': {
            'expected': '未知仓库显示未找到仓库提示且不借用其他仓数据',
            'locked_by': 'app.js:unknown_repo_notice+unknown_repo_loading'
                         '+unknown_repo_hide_main+unknown_repo_footer'
                         '+apply_route_snapshot_isolated 源码契约',
            'passed': not (missing & u11_locks)},
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

    views = own_views(index, snapshots)
    view_hashes = [v['hash'] for v in views]
    hash_matrix = build_hash_matrix(view_hashes)

    node = _node_check(root, hash_matrix, TO_HASH_MATRIX,
                       KEEP_PR_PAGE_MATRIX)
    problems = []
    resolve_mismatch, parse_mismatch = {}, {}
    to_hash_mismatch, keep_mismatch = {}, {}
    if node.get('status') == 'error':
        problems.append('node 交叉核对执行失败')
    else:
        for i, h in enumerate(hash_matrix):
            if own_resolve(h) != node['resolve'][i]:
                resolve_mismatch[str(i)] = {
                    'hash': h, 'own': own_resolve(h),
                    'node': node['resolve'][i]}
        if resolve_mismatch:
            problems.append('resolve 与 router.js 不一致')
        for i, h in enumerate(hash_matrix):
            if own_parse_hash(h) != node['parse'][i]:
                parse_mismatch[str(i)] = {
                    'hash': h, 'own': own_parse_hash(h),
                    'node': node['parse'][i]}
        if parse_mismatch:
            problems.append('parseHash 与 router.js 不一致')
        for i, route in enumerate(TO_HASH_MATRIX):
            if own_to_hash(route) != node['to_hash'][i]:
                to_hash_mismatch[str(i)] = {
                    'route': route, 'own': own_to_hash(route),
                    'node': node['to_hash'][i]}
        if to_hash_mismatch:
            problems.append('toHash 与 router.js 不一致')
        for i, triple in enumerate(KEEP_PR_PAGE_MATRIX):
            if own_keep_pr_page(*triple) != node['keep_pr_page'][i]:
                keep_mismatch[str(i)] = {
                    'triple': triple,
                    'own': own_keep_pr_page(*triple),
                    'node': node['keep_pr_page'][i]}
        if keep_mismatch:
            problems.append('keepPRPage 与 router.js 不一致')

    for view in views:
        if not view['roundtrip_ok']:
            problems.append(
                f"视图往返不一致: {view['repo']}/{view['kind']}")
            break
    for view in views:
        if not view['canonical_ok']:
            problems.append(
                f"视图哈希非规范（直接打开会被替换）: "
                f"{view['repo']}/{view['kind']}")
            break
    for view in views:
        if not view['snapshot_attribution_ok']:
            problems.append(
                f"视图数据归属不一致: {view['repo']}/{view['kind']}")
            break

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
                      '矩阵与契约检查照常执行'}

    per_repo = {}
    for view in views:
        if view['repo']:
            per_repo.setdefault(view['repo'], {})[view['kind']] = {
                'hash': view['hash'], 'view_name': view['view_name'],
                'nav_target': view['nav_target'],
                'roundtrip_ok': view['roundtrip_ok'],
                'canonical_ok': view['canonical_ok'],
                'snapshot_attribution_ok':
                    view['snapshot_attribution_ok'],
                'prs': view['prs']}
    ok = not problems
    report = {
        'requirement': 'REQ-047',
        'tool': 'scripts/verify_ubs_routes.py',
        'executed_at': stamp(),
        'input': {
            'bundle_fingerprint': fingerprint,
            'matches_audit_frozen_input': matches_baseline,
            'manifest_state': manifest_state,
            'bundle_errors': bundle_errors,
        },
        'views': {
            'total': len(views),
            'expected_total': 2 * len(index['repositories']) + 3,
            'repos': len(index['repositories']),
            'per_repo': per_repo,
            'global': [{'hash': v['hash'], 'kind': v['kind'],
                        'view_name': v['view_name'],
                        'nav_target': v['nav_target'],
                        'canonical_ok': v['canonical_ok']}
                       for v in views if v['repo'] is None],
        },
        'router_matrix': {
            'hash_cases': len(hash_matrix),
            'to_hash_cases': len(TO_HASH_MATRIX),
            'keep_pr_page_cases': len(KEEP_PR_PAGE_MATRIX),
            'resolve_mismatches': resolve_mismatch,
            'parse_mismatches': parse_mismatch,
            'to_hash_mismatches': to_hash_mismatch,
            'keep_pr_page_mismatches': keep_mismatch,
        },
        'legacy_aliases': {h: own_resolve(h) for h in (
            '#repositories', '#overview', '#prs', '#quality', '#method',
            '#repo/ubs-engine', '#repo/ubs-comm/quality',
            '#repo/ubs-engine/method')},
        'unknown_routes': {
            ('(empty)' if h in (None, '') else str(h)): own_resolve(h)
            for h in ('', None, '#xyz', '#UBS', '#ubs/repo', '#ubs/unknown',
                      '#ubs/repo/unknown-repo')},
        'source_contracts': contracts,
        'baseline': baseline,
        'node_cross_check': {
            'status': 'error' if node.get('status') == 'error' else 'ok',
            'compared': ['resolve', 'parseHash', 'toHash', 'keepPRPage'],
        },
        'overall': {'status': 'verified' if ok else 'failed',
                    'problems': problems},
    }
    return report, ok


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='REQ-047 UBS全部视图与旧链接可达性保持 — 保持验证工具')
    parser.add_argument('--root', default=str(ROOT), help='仓库根目录')
    parser.add_argument('--output', default=None, help='报告输出路径')
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    output = (Path(args.output).resolve() if args.output
              else root / EVIDENCE_REL / REPORT_NAME)
    try:
        report, ok = build_report(root)
    except Exception as error:  # noqa: BLE001 - 执行错误如实入报告
        print(json.dumps({'requirement': 'REQ-047', 'error': repr(error)},
                         ensure_ascii=False))
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n',
                      'utf-8')
    print(json.dumps({
        'overall_status': report['overall']['status'],
        'views': report['views']['total'],
        'expected_views': report['views']['expected_total'],
        'repos': report['views']['repos'],
        'hash_cases': report['router_matrix']['hash_cases'],
        'matrix_mismatches': (
            len(report['router_matrix']['resolve_mismatches'])
            + len(report['router_matrix']['parse_mismatches'])
            + len(report['router_matrix']['to_hash_mismatches'])
            + len(report['router_matrix']['keep_pr_page_mismatches'])),
        'view_checks_ok': all(
            v[k] for v in report['views']['per_repo'].values()
            for v in v.values() for k in ('roundtrip_ok', 'canonical_ok',
                                          'snapshot_attribution_ok')),
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
