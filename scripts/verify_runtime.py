"""REQ-040 · CI目标运行时兼容性验证 — 补证工具。

在 CI 声明的目标运行时（Python 3.12 / Node 22）执行测试套件、数据门禁与
原始审计的适用部分，生成 audit/2026-10-09/evidence/runtime-evidence.json：

- 精确版本（Python sys.version、node --version）与命令、退出码、失败数、
  完整日志（REQ-040-AC01）
- 审计期基线 Python 79/79、Node 34/34 仅为原环境记录，不替代目标运行时
  结果；新增测试数量不受原数量限制（REQ-040-AC02）
- 原始审计（validate.py / validate_multi.py）在目标运行时运行并如实分类；
  工件缺失或报告未验证时绝不因 wrapper 退出 0 报审计通过（REQ-040-AC03）
- CI 工作流声明版本、README 支持版本与交付运行结果三方一致（REQ-040-AC04）

退出码：测试与门禁在目标运行时全部通过且三方一致为 0；任一失败、版本
不匹配或文档缺失为 1。原始审计未通过（如 D10 工件缺失）不影响退出码，
但其在 raw_audit_summary 中如实记录，绝不冒充通过。
"""
import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_REL = Path('audit/2026-10-09/evidence')
REPORT_NAME = 'runtime-evidence.json'
WORKFLOW_DIR = Path('.github/workflows')
WORKFLOWS = ('pages.yml', 'triton-refresh.yml')
README_FILE = Path('README.md')
README_PY_MARKER = 'Python 3.12'
README_NODE_MARKER = 'Node 22'
BASELINE_NOTE = ('审计期基线 Python 79/79 与 Node 34/34 仅为原环境记录，不替代'
                 ' 3.12/22 目标运行时结果；新增测试数量不受原数量限制'
                 '（REQ-040-AC02）')
AUDIT_NOTE = ('原始审计在目标运行时运行并如实分类；工件缺失（D10）时审计'
              '失败，wrapper 不因自身退出 0 报审计通过（REQ-040-AC03）；'
              '审计状态不影响本工具退出码，退出码只由测试/门禁与版本一致性决定')
TIMEOUT_SECONDS = 900


def stamp():
    return datetime.now(timezone.utc).isoformat()


def node_major(version):
    """'v22.23.3' → '22'。"""
    match = re.match(r'v?(\d+)\.', version or '')
    return match.group(1) if match else None


def parse_workflow_declarations(root):
    """从两份工作流提取 python-version / node-version 声明。"""
    declared = {'python': set(), 'node': set()}
    for name in WORKFLOWS:
        path = root / WORKFLOW_DIR / name
        if not path.exists():
            continue
        text = path.read_text('utf-8')
        declared['python'].update(
            re.findall(r"python-version:\s*['\"]([^'\"]+)['\"]", text))
        declared['node'].update(
            re.findall(r"node-version:\s*['\"]([^'\"]+)['\"]", text))
    return {key: sorted(values) for key, values in declared.items()}


def parse_unittest_summary(output):
    """解析 unittest 输出的测试数、跳过数与失败/错误数。"""
    summary = {'tests': None, 'skipped': 0, 'failures': 0, 'errors': 0,
               'result': 'unknown'}
    ran = re.search(r'^Ran (\d+) tests?', output, re.M)
    if ran:
        summary['tests'] = int(ran.group(1))
    skipped = re.search(r'OK \(skipped=(\d+)\)', output)
    if skipped:
        summary['skipped'] = int(skipped.group(1))
    if re.search(r'^OK', output, re.M):
        summary['result'] = 'OK'
    failed = re.search(r'^FAILED \((.*)\)', output, re.M)
    if failed:
        summary['result'] = 'FAILED'
        for kind, number in re.findall(r'(\w+)=(\d+)', failed.group(1)):
            if kind in ('failures', 'errors', 'skipped'):
                summary[kind] = int(number)
    return summary


def parse_node_summary(output):
    """解析 node --test 摘要（Node 22 '#' 与 Node 24 'ℹ' 两种前缀）。"""
    summary = {'tests': None, 'pass': None, 'fail': None, 'skipped': None,
               'result': 'unknown'}
    for key in ('tests', 'pass', 'fail', 'skipped'):
        match = re.search(rf'^[ℹ#] {key} (\d+)$', output, re.M)
        if match:
            summary[key] = int(match.group(1))
    if summary['fail'] == 0 and summary['tests'] is not None:
        summary['result'] = 'OK'
    elif summary['fail'] is not None:
        summary['result'] = 'FAILED'
    return summary


def classify_audit(exit_code, log_text, report_path=None):
    """原始审计如实分类：报告未达 verified 或工件缺失时绝不返回 passed。"""
    if exit_code == 0:
        if report_path is not None and Path(report_path).exists():
            try:
                data = json.loads(Path(report_path).read_text('utf-8'))
            except (OSError, ValueError):
                return 'inconclusive_bad_report', None
            status = data.get('overall_status')
            if status == 'verified':
                return 'passed', status
            return f'not_passed_{status}', status
        return 'inconclusive_exit0_no_report', None
    if 'FileNotFoundError' in (log_text or ''):
        return 'failed_missing_artifacts', None
    return f'failed_exit_{exit_code}', None


def run_command(label, cmd, root, log_dir):
    """执行命令，保存完整日志并返回记录。"""
    log_path = log_dir / f'{label}.txt'
    try:
        proc = subprocess.run([str(part) for part in cmd], cwd=str(root),
                              capture_output=True, text=True,
                              timeout=TIMEOUT_SECONDS)
        output = (proc.stdout or '') + (proc.stderr or '')
        entry = {'label': label,
                 'command': ' '.join(str(part) for part in cmd),
                 'exit_code': proc.returncode}
    except subprocess.TimeoutExpired as error:
        output = f'TIMEOUT after {TIMEOUT_SECONDS}s: {error}'
        entry = {'label': label,
                 'command': ' '.join(str(part) for part in cmd),
                 'exit_code': None, 'timeout': True}
    log_path.write_text(output, 'utf-8')
    entry['log'] = str(log_path.relative_to(root)
                       if str(log_path).startswith(str(root)) else log_path)
    entry['log_tail'] = '\n'.join(output.strip().splitlines()[-5:])
    return entry, output


def _rel(path, root):
    try:
        return str(Path(path).relative_to(root))
    except ValueError:
        return str(path)


def build_report(root, node_bin):
    log_dir = root / '.omo/evidence/req-040/logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    problems = []

    python_version = '.'.join(str(part) for part in sys.version_info[:3])
    node_version = None
    try:
        proc = subprocess.run([str(node_bin), '--version'], capture_output=True,
                              text=True, timeout=30)
        if proc.returncode == 0:
            node_version = proc.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        node_version = None
    runtimes = {
        'python': {'version': f'{python_version} ({sys.implementation.name})',
                   'major_minor': f'{sys.version_info.major}.{sys.version_info.minor}',
                   'executable': _rel(sys.executable, root)},
        'node': {'version': node_version, 'major': node_major(node_version),
                 'binary': _rel(node_bin, root)},
    }
    if node_version is None:
        problems.append('无法获取 Node 版本')

    declared = parse_workflow_declarations(root)
    readme_text = (root / README_FILE).read_text('utf-8') \
        if (root / README_FILE).exists() else ''

    test_files = [str(path.relative_to(root))
                  for path in sorted(root.glob('tests/*.test.cjs'))]
    commands = [
        ('python_tests',
         [sys.executable, '-X', 'utf8', '-m', 'unittest', 'discover', '-s', 'tests'],
         'unittest'),
        ('node_tests', [node_bin, '--test'] + test_files, 'node'),
        ('validate_bundle', [sys.executable, '-X', 'utf8', 'validate_bundle.py'], 'gate'),
        ('verify_artifacts',
         [sys.executable, '-X', 'utf8', 'scripts/verify_artifacts.py'], 'gate'),
        ('verify_concurrency',
         [sys.executable, '-X', 'utf8', 'scripts/verify_concurrency.py'], 'gate'),
        ('raw_audit_multi', [sys.executable, '-X', 'utf8', 'validate_multi.py'],
         'audit'),
        ('raw_audit_ubs', [sys.executable, '-X', 'utf8', 'validate.py'], 'audit'),
    ]
    runs = []
    audits = {}
    for label, cmd, kind in commands:
        entry, output = run_command(label, cmd, root, log_dir)
        entry['kind'] = kind
        if kind == 'unittest':
            entry['summary'] = parse_unittest_summary(output)
            if entry['exit_code'] != 0 or entry['summary']['result'] != 'OK':
                problems.append(f"{label}: 退出码 {entry['exit_code']}，"
                                f"结果 {entry['summary']['result']}")
        elif kind == 'node':
            entry['summary'] = parse_node_summary(output)
            if (entry['exit_code'] != 0 or entry['summary']['result'] != 'OK'
                    or entry['summary']['fail'] != 0):
                problems.append(f"{label}: 退出码 {entry['exit_code']}，"
                                f"失败 {entry['summary']['fail']}")
        elif kind == 'gate':
            if entry['exit_code'] != 0:
                problems.append(f"{label}: 退出码 {entry['exit_code']}")
        else:
            report_path = (root / 'data/validation-multi.json'
                           if label == 'raw_audit_multi'
                           else root / 'data/validation.json')
            classification, report_status = classify_audit(
                entry['exit_code'], output, report_path)
            entry['audit_classification'] = classification
            entry['audit_report_status'] = report_status
            audits[label] = classification
        runs.append(entry)

    audit_passed = all(state == 'passed' for state in audits.values()) and audits
    consistency = {
        'python_runtime_matches_ci':
            runtimes['python']['major_minor'] in declared.get('python', []),
        'node_runtime_matches_ci':
            runtimes['node']['major'] in declared.get('node', []),
        'readme_states_python': README_PY_MARKER in readme_text,
        'readme_states_node': README_NODE_MARKER in readme_text,
    }
    labels = {'python_runtime_matches_ci': 'Python 运行时与 CI 声明不一致',
              'node_runtime_matches_ci': 'Node 运行时与 CI 声明不一致',
              'readme_states_python': 'README 未声明 Python 支持版本',
              'readme_states_node': 'README 未声明 Node 支持版本'}
    for key, ok in consistency.items():
        if not ok:
            problems.append(labels[key])

    report = {
        'requirement': 'REQ-040',
        'generated_at': stamp(),
        'runtimes': runtimes,
        'ci_declarations': {
            'python': declared.get('python'),
            'node': declared.get('node'),
            'sources': list(WORKFLOWS),
        },
        'baseline_note': BASELINE_NOTE,
        'runs': runs,
        'raw_audit_summary': {
            'status': 'passed' if audit_passed else 'not_passed',
            'classifications': audits,
            'note': AUDIT_NOTE,
        },
        'version_consistency': {**consistency, 'problems': []},
        'overall': {
            'status': 'verified' if not problems else 'failed',
            'problems': problems,
        },
    }
    report['version_consistency']['problems'] = [
        labels[key] for key, ok in consistency.items() if not ok]
    return report, not problems


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='REQ-040 CI目标运行时兼容性验证 — 补证工具')
    parser.add_argument('--root', default=str(ROOT), help='仓库根目录')
    parser.add_argument('--node-bin', default='node',
                        help='Node 可执行文件（须为 CI 声明的 Node 22）')
    parser.add_argument('--output', default=None, help='报告输出路径')
    args = parser.parse_args(argv)
    root = Path(args.root).resolve()
    output = (Path(args.output).resolve() if args.output
              else root / EVIDENCE_REL / REPORT_NAME)
    try:
        report, ok = build_report(root, args.node_bin)
    except Exception as error:  # noqa: BLE001 - 执行错误如实入报告
        print(json.dumps({'requirement': 'REQ-040', 'error': repr(error)},
                         ensure_ascii=False))
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    summary = {run['label']: {'exit': run['exit_code']} for run in report['runs']}
    print(json.dumps({
        'overall_status': report['overall']['status'],
        'runtimes': {key: value['version']
                     for key, value in report['runtimes'].items()},
        'runs': summary,
        'raw_audit': report['raw_audit_summary']['status'],
        'raw_audit_classifications': report['raw_audit_summary']['classifications'],
        'consistency': {key: value for key, value
                        in report['version_consistency'].items()
                        if key != 'problems'},
        'problems': report['overall']['problems'],
        'report': str(output),
    }, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
