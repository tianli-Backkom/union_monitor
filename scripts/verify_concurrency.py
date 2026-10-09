"""REQ-039 · 并发调度策略与运行证据一致 — 补证工具。

审计发现 P04：两工作流共用 concurrency group `pages` 且 `cancel-in-progress:
false`，仅保护正在运行的构建；排队运行遵循平台默认替换规则（queue: single，
同组仅保留最新一个 pending，较早排队者被取消替换）。旧测试名
queued_runs_never_cancel_the_daily_build 兑现不了该承诺，真实取消事件与
受控序列均未读取。

本工具生成 audit/2026-10-09/evidence/concurrency-evidence.json：
- 从两份工作流提取并发声明（组名、cancel-in-progress、是否显式 queue），
  核对与文档化策略一致（group=pages、cancel-in-progress=false、默认 single）
- 记录平台文档语义（running/pending 规则，含官方引文与参考链接）
- 记录业务影响场景（含计划重叠分析；不推断已线上发生）
- AC01 受控序列协议与 AC03 运行历史读取：无 remote/gh/凭证，如实标
  unverified 并给出可执行协议
- AC04 queue:max 缓期决策与未来策略草案（与 cancel-in-progress:true 互斥）
- 核对测试名与 README 措辞已与平台语义对齐（AC02）

退出码：策略与对齐全部满足为 0；配置漂移、对齐缺失或执行错误为 1；
unverified 状态本身不导致失败（如实记录，不伪造证据）。
"""
import argparse
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = Path('.github/workflows')
WORKFLOWS = ('pages.yml', 'triton-refresh.yml')
EVIDENCE_REL = Path('audit/2026-10-09/evidence')
REPORT_NAME = 'concurrency-evidence.json'
REFERENCE = ('https://docs.github.com/en/actions/how-tos/write-workflows/'
             'choose-when-workflows-run/control-workflow-concurrency')
TEST_FILE = Path('tests/test_triton_workflow.py')
OLD_TEST_NAME = 'test_queued_runs_never_cancel_the_daily_build'
NEW_TEST_NAME = ('test_concurrency_protects_running_pending_replaced_'
                 'by_platform_default')
README_FILE = Path('README.md')
README_MARKER = '排队中的运行遵循平台默认替换规则'

DOCUMENTED_QUOTES = [
    'there can be at most one running job or workflow in a concurrency '
    'group at any time',
    'By default, any existing `pending` job or workflow in the same '
    'concurrency group will be canceled and the new queued job or workflow '
    'will take its place.',
    'single (default): At most one job or workflow run can be `pending` in '
    'the concurrency group. When a new job or workflow run is queued, any '
    'existing `pending` job or workflow run in the same group is canceled '
    'and replaced.',
    'The combination of `queue: max` and `cancel-in-progress: true` is not '
    'allowed and will result in a workflow validation error.',
]


def stamp():
    return datetime.now(timezone.utc).isoformat()


def extract_concurrency(text):
    """提取工作流顶层 concurrency 声明的键值（组名/取消开关/是否显式 queue）。"""
    match = re.search(r'(?ms)^concurrency:\s*\n((?:[ \t]+[^\n]*\n)+)', text)
    if not match:
        return None
    info = {}
    for line in match.group(1).splitlines():
        field = re.match(r'\s+(group|cancel-in-progress|queue):\s*(.+?)\s*$', line)
        if field:
            info[field.group(1)] = field.group(2)
    return info


def _git_remotes(root):
    try:
        result = subprocess.run(['git', '-C', str(root), 'remote'],
                                capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return []
        return [line for line in result.stdout.splitlines() if line.strip()]
    except (OSError, subprocess.SubprocessError):
        return []


def config_facts(root):
    """核对两份工作流的并发声明与文档化策略一致。"""
    facts, problems = {}, []
    for name in WORKFLOWS:
        path = root / WORKFLOW_DIR / name
        if not path.exists():
            facts[name] = {'status': 'missing'}
            problems.append(f'{name}: 工作流文件缺失')
            continue
        info = extract_concurrency(path.read_text('utf-8'))
        if not info:
            facts[name] = {'status': 'absent_decl'}
            problems.append(f'{name}: 无顶层 concurrency 声明')
            continue
        entry = {
            'group': info.get('group'),
            'cancel_in_progress': info.get('cancel-in-progress'),
            'queue': info.get('queue', 'single (platform default)'),
        }
        facts[name] = entry
        if entry['group'] != 'pages':
            problems.append(f"{name}: 并发组为 {entry['group']}，策略要求 pages")
        if entry['cancel_in_progress'] != 'false':
            problems.append(f"{name}: cancel-in-progress 为 "
                            f"{entry['cancel_in_progress']}，策略要求 false")
        if 'queue' in info:
            problems.append(f"{name}: 显式声明 queue: {info['queue']}，"
                            '当前策略沿用平台默认 single，新策略需同步本工具与 README')
    return facts, problems


def alignment(root):
    """AC02：测试名与 README 措辞与平台语义对齐。"""
    checks, problems = {}, []
    test_path = root / TEST_FILE
    if not test_path.exists():
        checks['test_file_present'] = False
        problems.append(f'{TEST_FILE} 缺失')
    else:
        text = test_path.read_text('utf-8')
        checks['old_test_name_removed'] = OLD_TEST_NAME not in text
        checks['new_test_name_present'] = NEW_TEST_NAME in text
        if not checks['old_test_name_removed']:
            problems.append(f'测试仍使用失实名 {OLD_TEST_NAME}')
        if not checks['new_test_name_present']:
            problems.append(f'缺少语义正确的测试名 {NEW_TEST_NAME}')
    readme_path = root / README_FILE
    if not readme_path.exists():
        checks['readme_present'] = False
        problems.append(f'{README_FILE} 缺失')
    else:
        checks['readme_states_pending_replacement'] = (
            README_MARKER in readme_path.read_text('utf-8'))
        if not checks['readme_states_pending_replacement']:
            problems.append('README 未声明排队运行的平台默认替换规则')
    return checks, problems


def documented_semantics():
    return {
        'running': '同一并发组任一时刻最多一个运行中的任务；cancel-in-progress 为 '
                   'false 时新触发不取消正在运行的任务，只能进入 pending',
        'pending_default_single': '默认 queue: single——同一并发组最多保留一个 '
                                  'pending；新的排队运行会取消并替换已有的 pending 运行',
        'queue_max': 'queue: max 时同一并发组最多 100 个 pending，队列满后新运行被'
                     '取消；queue: max 与 cancel-in-progress: true 组合为非法配置',
        'fifo': '同组运行按开始等待并发组的时间 FIFO 处理，实际开始时间不定，顺序不保证',
        'quotes': DOCUMENTED_QUOTES,
        'reference': REFERENCE,
        'source_note': '官方文档引文，随 REQ-039 于 2026-10-10 人工核对抓取',
    }


def business_impact():
    return {
        'schedule_facts': {
            'daily': 'pages.yml 每日北京时间 07:30（UTC 23:30）触发，build timeout 180 分钟',
            'incremental': 'triton-refresh.yml 北京时间 08:00/13:00/18:00/20:00 触发，'
                           'build timeout 60 分钟',
        },
        'scenarios': [
            {'id': 'S-a', 'sequence': '每日全量运行中，增量触发',
             'platform': '增量进入 pending，全量完成后执行',
             'business': '无丢失：运行中构建受 cancel-in-progress:false 保护'},
            {'id': 'S-b', 'sequence': '增量运行中，每日全量排队，随后新增量触发',
             'platform': '排队的每日全量被新增量取消替换（queue: single 默认）',
             'business': '当日全量更新（含九仓 UBS 采集）丢失，等待次日 07:30 计划恢复，'
                         'UBS 数据陈旧最长约 24 小时'},
            {'id': 'S-c', 'sequence': '计划重叠可能性',
             'platform': '07:30 全量启动后 30 分钟即 08:00 增量触发',
             'business': '计划内的重叠均落在 S-a 安全场景；S-b 需要增量跨越次日 07:30 '
                         '仍在运行（增量 timeout 60 分钟、末班 20:00 远早于 07:30），'
                         '仅手动 workflow_dispatch 或平台异常延迟才可能构成'},
        ],
        'conclusion': '按计划表重叠走安全场景 S-a；S-b 存在但需手动/异常触发，'
                      '平台运行历史未读取（见 ac03_run_history），不推断已线上发生',
    }


def ac01_controlled_sequence(reasons):
    return {
        'status': 'unverified',
        'reasons': reasons,
        'requirement': '运行中任务 A、随后 pending B 及 C 的受控序列，记录 A 是否被'
                       '取消及 B/C 实际排队/替换结果，并提供隔离工作流运行 ID/事件记录',
        'protocol': {
            'isolation': '使用独立并发组（如 concurrency-probe-${{ github.run_id }} '
                         '派生组）或隔离仓库，不影响生产 pages 组',
            'steps': [
                'A：workflow_dispatch 触发长任务（如 sleep 600），进入 running',
                'B：再次触发短任务（sleep 60），进入 pending',
                'C：第三次触发短任务（sleep 60），观察 B 被取消替换、C 保持 pending',
                'A 自然结束后 C 启动执行',
                '记录三个 run ID、每次运行的状态事件时间线'
                '（queued/in_progress/cancelled）与 conclusion',
            ],
            'expected': 'A 不被取消（cancel-in-progress:false）；B 被 C 取代'
                        '（平台默认 pending 替换）；C 在 A 结束后运行',
            'evidence_to_record': ['隔离工作流运行 ID', '每次运行的状态事件与时间戳',
                                   'B 的取消/替换事件记录'],
        },
    }


def ac03_run_history(reasons):
    return {
        'status': 'unverified',
        'reasons': reasons,
        'requirement': '读取可取得的真实运行历史并记录是否影响每日全量更新',
        'procedure': [
            'gh run list --workflow pages.yml --limit 100 '
            '--json databaseId,status,conclusion,event,createdAt,updatedAt',
            'REST: GET /repos/{owner}/{repo}/actions/runs?per_page=100'
            '（公开仓库无凭证亦可读取）',
            '筛选 conclusion 含 cancelled 的运行与同日 07:30 全量/08:00 增量触发对，'
            '核对排队替换是否实际发生并影响每日全量更新',
        ],
        'recorded': '本仓库无 git remote 且无 gh CLI，无可取得的运行历史；'
                    '保持未验证，不推断已线上发生',
    }


def ac04_queue_max():
    return {
        'decision': 'deferred',
        'rationale': '沿用当前策略：cancel-in-progress:false 保护运行中构建，接受平台'
                     '默认排队替换；缺少 queue:max 本身不是新增必改功能',
        'p04_resolution': '审计期 P04 期望两工作流声明 queue:max；REQ-039 采纳'
                          '"缺 queue:max 非新增必改功能"，决策缓期并记录于此',
        'future_policy': '如未来要求保留全部排队任务：需制定明确新运行策略（如 '
                         'queue: max——与 cancel-in-progress:true 互斥、按工作流拆分'
                         '并发组、或错峰计划），并附受控序列记录与真实历史核对的'
                         '对应验收，另行立项',
    }


def build_report(root):
    facts, config_problems = config_facts(root)
    checks, align_problems = alignment(root)
    remotes = _git_remotes(root)
    gh = shutil.which('gh') is not None
    reasons = []
    if not remotes:
        reasons.append('无 git remote')
    if not gh:
        reasons.append('无 gh CLI')
    if not reasons:
        reasons.append('有访问途径但尚未执行，等待部署后运行')
    problems = config_problems + align_problems
    report = {
        'requirement': 'REQ-039',
        'check_id': 'P04',
        'generated_at': stamp(),
        'config_facts': facts,
        'documented_platform_semantics': documented_semantics(),
        'business_impact': business_impact(),
        'ac01_controlled_sequence': ac01_controlled_sequence(reasons),
        'ac03_run_history': ac03_run_history(reasons),
        'ac04_queue_max': ac04_queue_max(),
        'test_and_doc_alignment': checks,
        'overall': {
            'status': 'aligned' if not problems else 'drift',
            'problems': problems,
            'note': 'unverified 的受控序列与运行历史如实记录，不影响退出码；'
                    '退出码只由策略一致性与文档/测试对齐决定',
        },
    }
    return report, not problems


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='REQ-039 并发调度策略与运行证据一致 — 补证工具')
    parser.add_argument('--root', default=str(ROOT), help='仓库根目录')
    parser.add_argument('--output', default=None, help='报告输出路径')
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    output = Path(args.output).resolve() if args.output else root / EVIDENCE_REL / REPORT_NAME
    try:
        report, ok = build_report(root)
    except Exception as error:  # noqa: BLE001 - 执行错误如实入报告
        print(json.dumps({'requirement': 'REQ-039', 'error': repr(error)},
                         ensure_ascii=False))
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    print(json.dumps({
        'overall_status': report['overall']['status'],
        'config': {name: entry.get('group', entry.get('status'))
                   for name, entry in report['config_facts'].items()},
        'ac01': report['ac01_controlled_sequence']['status'],
        'ac03': report['ac03_run_history']['status'],
        'ac04': report['ac04_queue_max']['decision'],
        'alignment': all(report['test_and_doc_alignment'].values()),
        'problems': report['overall']['problems'],
        'report': str(output),
    }, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
