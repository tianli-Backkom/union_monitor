"""Validate relocated project artifacts before the shadow manifest is assembled.

This validates current-run files; it does not implement production publishing,
trusted fallback, deployment verification or rollback.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath

from .context import utc_time
from .report import validate_report


class ArtifactError(ValueError):
    """Downloaded artifacts cannot safely be used as this round's inputs."""


def _read(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict):
            raise ValueError('expected a JSON object')
        return value
    except (OSError, ValueError) as exc:
        raise ArtifactError(f'{path.name}: {exc}') from exc


def _snapshot_path(report_file, declared, pid):
    if not isinstance(declared, str) or not declared:
        raise ArtifactError('snapshot_path is missing')
    old = PurePosixPath(declared.replace('\\', '/'))
    if '..' in old.parts or old.name != 'snapshot.json':
        raise ArtifactError('unsafe snapshot_path')
    # Support old producer paths after download, but only their known project
    # suffix. Never follow the producer's absolute path or a sibling's path.
    if len(old.parts) > 1 and old.parts[-2] != pid:
        raise ArtifactError('snapshot_path belongs to another project')
    directory = report_file.parent.resolve()
    target = (directory/'snapshot.json').resolve()
    if not target.is_relative_to(directory) or not target.is_file():
        raise ArtifactError('snapshot file is missing or escapes its project directory')
    return target


def _check_snapshot(report_file, report, project, context):
    for key in ('snapshot_version', 'snapshot_sha256', 'collected_at', 'window'):
        if not report.get(key):
            raise ArtifactError(f'successful report is missing {key}')
    window = report['window']
    if not isinstance(window, dict) or any(not window.get(key) for key in ('time_basis', 'start_at', 'end_at')):
        raise ArtifactError('successful report has an incomplete window')
    expected_window = context.window_for(project)
    if window['time_basis'] != expected_window['time_basis'] or any(
        utc_time(window[key]) != utc_time(expected_window[key]) for key in ('start_at', 'end_at')
    ):
        raise ArtifactError('snapshot window does not match the frozen project window')
    if not re.fullmatch(r'[0-9a-f]{64}', report['snapshot_sha256']):
        raise ArtifactError('snapshot_sha256 is invalid')
    try:
        utc_time(report['collected_at'])
    except (ValueError, TypeError, AttributeError) as exc:
        raise ArtifactError('collected_at is invalid') from exc
    path = _snapshot_path(report_file, report.get('snapshot_path'), project['project_id'])
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != report['snapshot_sha256']:
        raise ArtifactError('snapshot hash mismatch')
    snapshot = _read(path)
    for key, expected in (('project_id', project['project_id']), ('run_id', context.run_id),
                          ('code_sha', context.code_sha), ('collector', project['collector']),
                          ('window', report['window']), ('collected_at', report['collected_at'])):
        if snapshot.get(key) != expected:
            raise ArtifactError(f'snapshot {key} mismatch')
    repositories = snapshot.get('repositories')
    expected_repositories = {r['repository_id'] for r in project['repositories']}
    if not isinstance(repositories, dict) or set(repositories) != expected_repositories:
        raise ArtifactError('snapshot repository set mismatch')
    for rid, payload in repositories.items():
        if not isinstance(payload, dict):
            raise ArtifactError('repository payload is not an object')
        source = payload.get('repo') or (payload.get('meta') or {}).get('repository')
        if source != rid.split(':', 1)[1]:
            raise ArtifactError('repository payload ownership mismatch')
    return path


def load_project_reports(root, catalog, context):
    """Read distinct downloaded bundles, rejecting integrity/identity errors.

    Missing jobs receive explicit failed reports so other projects can finish.
    Corrupt, duplicate or misattributed artifacts block assembly.
    """
    root = Path(root).resolve()
    projects = {p['project_id']: p for p in catalog.enabled_projects()}
    reports = {}
    for report_file in sorted(root.rglob('collection-report.json')):
        if not report_file.resolve().is_relative_to(root):
            raise ArtifactError('report escapes the artifact root')
        report = _read(report_file)
        pid = report.get('project_id')
        if pid not in projects:
            raise ArtifactError(f'report references an unknown or disabled project: {pid!r}')
        if pid in reports:
            raise ArtifactError(f'duplicate reports for project {pid!r}')
        errors = validate_report(report, context, catalog)
        if type(report.get('exit_code')) is not int:
            errors.append('report exit_code is missing or invalid')
        if errors:
            raise ArtifactError(f'{pid}: ' + '; '.join(errors))
        if report.get('collection_status') == 'failed' and (report.get('validation_status') != 'failed' or report.get('task_status') == 'success' or report['exit_code'] == 0):
            raise ArtifactError('failed collection has inconsistent task/validation/exit status')
        if report.get('collection_status') == 'success':
            if report.get('validation_status') != 'passed' or report['exit_code'] != 0 or report.get('task_status') not in ('success', 'partial'):
                raise ArtifactError('successful collection has inconsistent task/validation/exit status')
            path = _check_snapshot(report_file, report, projects[pid], context)
            report = {**report, 'snapshot_path': str(path), 'artifact': str(path)}
        reports[pid] = report
    for pid, project in projects.items():
        if pid not in reports:
            error = 'no collection report produced for this project'
            reports[pid] = {'schema_version': 1, 'run_id': context.run_id, 'code_sha': context.code_sha,
                            'project_id': pid, 'collector': project['collector'], 'metric_profile': project['metric_profile'],
                            'task_status': 'failed', 'collection_status': 'failed', 'validation_status': 'failed',
                            'exit_code': 1, 'error': error, 'errors': [error]}
    return reports
