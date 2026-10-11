"""Exercise default collectors at their transport boundary, without live APIs."""
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from monitor.adapters import collect_repositories, github_actions, gitcode_jenkins
from monitor.catalog import Catalog
from monitor.collect import collect_project
from monitor.context import RunContext
from triton import dashboard

ROOT = Path(__file__).resolve().parents[1]
CATALOG = Catalog.load(ROOT / 'catalog.json')


def context():
    return RunContext(run_id='run-boundary-1', code_sha='e'*40, cutoff_at='2026-10-10T00:00:00Z')


class EmptyGitHub:
    """Only the empty Actions REST responses; real collect/quality code runs."""
    def __init__(self):
        self.calls = 0

    def get(self, path):
        if '/actions/runs?' not in path or 'per_page=1' not in path:
            raise AssertionError('unexpected transport request: ' + path)
        self.calls += 1
        return {'total_count': 0}, {}

    def pages(self, path, field=None):
        if '/actions/runs?' not in path or field != 'workflow_runs':
            raise AssertionError('unexpected transport page: ' + path)
        self.calls += 1
        return []


class DefaultGithubBoundaryTests(unittest.TestCase):
    def test_empty_real_collect_keeps_source_time_and_passes_actual_quality_gate(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence = Path(folder) / 'evidence'
            with patch.object(dashboard, 'GitHub', EmptyGitHub), patch.object(dashboard, 'EVIDENCE', evidence):
                report = collect_project(CATALOG, context(), 'triton', folder)
            self.assertEqual(report['collection_status'], 'success', report)
            self.assertEqual(report['validation_status'], 'passed', report)
            stored = json.loads((Path(folder)/'triton'/'snapshot.json').read_text('utf-8'))
            source = stored['repositories']['github:triton-lang/triton-ascend']
            self.assertEqual(source['window_end'], '2026-10-10T00:00:00Z')
            self.assertEqual(source['batches'], [])
            self.assertEqual(report['collected_at'], source['collected_at'])
            self.assertNotEqual(source['collected_at'], '2026-10-10T00:00:00Z')

    def test_invalid_real_quality_evidence_is_failed_not_default_passed(self):
        with tempfile.TemporaryDirectory() as folder:
            evidence = Path(folder)/'evidence'
            evidence.mkdir()
            (evidence/'enriched-runs.json').write_text(json.dumps([{
                'id': 1, 'status': 'completed', 'jobs_complete': False, 'jobs': [],
                'created_at': '2026-10-09T23:00:00Z', 'updated_at': '2026-10-10T01:00:00Z'
            }]), encoding='utf-8')
            payload = dashboard.build_payload([], '2026-10-07T00:00:00Z', '2026-10-10T00:00:00Z', '2026-10-10T00:10:00Z')
            with patch.object(dashboard, 'collect', return_value=payload), patch.object(dashboard, 'EVIDENCE', evidence):
                report = collect_project(CATALOG, context(), 'triton', folder)
            self.assertEqual(report['collection_status'], 'failed', report)
            self.assertEqual(report['validation_status'], 'failed', report)
            self.assertTrue(any('incomplete job list' in x for x in report['errors']), report)

    def test_requested_other_repository_cannot_acquire_triton_identity(self):
        project = copy.deepcopy(CATALOG.project('triton'))
        project['repositories'][0]['repository_id'] = 'github:acme/ci'
        with tempfile.TemporaryDirectory() as folder, patch.object(dashboard, 'GitHub', EmptyGitHub):
            report = github_actions.collect(project, context(), folder)
        self.assertEqual(report['collection_status'], 'failed')
        self.assertTrue(any('repository' in error for error in report['errors']), report)


class AdapterQualityPropagationTests(unittest.TestCase):
    def test_ubs_source_errors_do_not_become_success(self):
        project = copy.deepcopy(CATALOG.project('ubs'))
        project['repositories'] = project['repositories'][:1]
        payload = {'meta': {'repository': 'openeuler/ubs-engine', 'branch': 'master',
                           'start_ms': 1788998400000, 'end_ms': 1791590400000,
                           'collected_at': '2026-10-10T00:10:00Z',
                           'errors': [{'source': 'PR comments', 'reason': 'unavailable'}]}, 'prs': []}
        with tempfile.TemporaryDirectory() as folder:
            result = gitcode_jenkins.collect(project, context(), folder,
                                            runner=lambda r,p,c: payload)
        self.assertEqual(result['collection_status'], 'failed', result)
        self.assertEqual(result['validation_status'], 'failed', result)
        self.assertTrue(any('unavailable' in x for x in result['errors']), result)
        self.assertIn('unavailable', result.get('error', ''))

    def test_shared_runner_without_validator_never_claims_quality_passed(self):
        with tempfile.TemporaryDirectory() as folder:
            result = collect_repositories(CATALOG.project('triton'), context(), folder,
                                          runner=lambda r,p,c: {'repo': 'triton-lang/triton-ascend', 'batches': []})
        self.assertEqual(result.get('validation_status'), 'failed', result)
        self.assertEqual(result['collection_status'], 'failed', result)


if __name__ == '__main__':
    unittest.main()
