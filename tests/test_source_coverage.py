"""REQ-023 — raw-source coverage accounting and missing-evidence manifests.

Source audits must declare a denominator per verifiable category, count
verified/differing/missing objects with traceable identities, and refuse to
claim all-pass when raw evidence is absent or partial (F13, P05, D10).
"""
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import validate_multi
from source_coverage import MISSING_LIMIT, SourceCategory, source_report

ROOT = Path(__file__).resolve().parents[1]
REPO = 'openeuler/ubs-test'


def trigger_job(number):
    return {'url': f'https://ci.example/job/ubs-test/job/trigger/{number}/', 'number': number, 'result': 'SUCCESS',
            'building': False, 'start_ms': 1000, 'end_ms': 1200, 'duration_ms': 200, 'queue_ms': 50,
            'total_ms': 250, 'scheduled_ms': 990, 'causes': []}


def child_job(number):
    return {'url': f'https://ci.example/job/ubs-test/job/x86/{number}/', 'number': number, 'result': 'SUCCESS',
            'building': False, 'start_ms': 1100, 'end_ms': 1400, 'duration_ms': 300, 'queue_ms': 100,
            'total_ms': 400, 'scheduled_ms': 1050, 'kind': 'x86', 'association_valid': False, 'causes': []}


def empty_kind():
    return {'url': None, 'queue_ms': None, 'duration_ms': None, 'total_ms': None}


def pr_with_gate(number):
    trigger, child = trigger_job(number), child_job(number)
    batch = {'url': trigger['url'], 'number': number, 'status': 'success', 'complete': True, 'eligible': True,
             'request_ms': 1000, 'e2e_ms': 400, 'cancelled': False, 'trigger': trigger, 'children': [child]}
    metrics = {'representative_batch_url': trigger['url'], 'representative_batch_number': number, 'e2e_ms': 400,
               'x86': empty_kind(), 'arm': empty_kind(), 'dt': empty_kind()}
    return {'number': number, 'state': 'merged', 'created_ms': 1500, 'repository': REPO,
            'batches': [batch], 'metrics': metrics}


def pr_without_gate():
    return {'number': 8, 'state': 'open', 'created_ms': 1600, 'repository': REPO, 'batches': [],
            'metrics': {'representative_batch_url': None, 'representative_batch_number': None, 'e2e_ms': None,
                        'x86': empty_kind(), 'arm': empty_kind(), 'dt': empty_kind()}}


def raw_files(prs, drop=(), tamper=None):
    """One cached Jenkins allBuilds response per job; empty input means zero raw evidence."""
    files = {}
    for pr in prs:
        for batch in pr['batches']:
            for job in [batch['trigger']] + batch['children']:
                files[job['url']] = {'url': job['url'], 'body': {'allBuilds': [
                    {'url': job['url'], 'timestamp': job['start_ms'], 'duration': job['duration_ms']}]}}
    for url in drop:
        files.pop(url, None)
    if tamper is not None:
        url, duration = tamper
        files[url]['body']['allBuilds'][0]['duration'] = duration
    return list(files.values())


def write_sqlite(path, prs):
    db = sqlite3.connect(path)
    with db:
        db.execute('create table prs(number integer, repository text, payload text)')
        db.execute('create table batches(url text, repository text, pr integer, payload text)')
        for pr in prs:
            db.execute('insert into prs values(?,?,?)', (pr['number'], REPO, json.dumps(pr, ensure_ascii=False)))
            for batch in pr['batches']:
                db.execute('insert into batches values(?,?,?,?)',
                           (batch['url'], REPO, pr['number'], json.dumps(batch, ensure_ascii=False)))
    db.close()


def write_multi_tree(tmp, prs, raw):
    (tmp / 'data/repos').mkdir(parents=True)
    (tmp / 'data/raw').mkdir(parents=True)
    (tmp / 'web/data/repos').mkdir(parents=True)
    names = ['ubs-test'] + [f'ubs-other-{i}' for i in range(8)]  # audit asserts exactly nine repositories
    (tmp / 'repositories.json').write_text(
        json.dumps([{'name': n, 'repository': f'openeuler/{n}'} for n in names]), 'utf-8')
    entries = [{'name': 'ubs-test', 'repository': REPO, 'status': 'success', 'snapshot': 'repos/ubs-test.json'}]
    entries += [{'name': n, 'repository': f'openeuler/{n}', 'status': 'pending'} for n in names[1:]]
    index = {'schema_version': 3, 'start_ms': 1000, 'end_ms': 2000, 'generated_at': '2026-10-09T00:00:00+08:00',
             'repositories': entries}
    (tmp / 'data/repositories.json').write_text(json.dumps(index, ensure_ascii=False), 'utf-8')
    snapshot = {'meta': {'repository': REPO, 'collected_at': '2026-10-09T00:00:00+08:00', 'start_ms': 1000,
                         'end_ms': 2000, 'expected_prs': len(prs), 'schema_version': 3}, 'prs': prs}
    (tmp / 'data/repos/ubs-test.json').write_text(json.dumps(snapshot, ensure_ascii=False), 'utf-8')
    for relative in ('repositories.json', 'repos/ubs-test.json'):
        (tmp / 'web/data' / relative).write_bytes((tmp / 'data' / relative).read_bytes())
    shutil.copyfile(ROOT / 'web/core.js', tmp / 'web/core.js')
    for i, entry in enumerate(raw):
        (tmp / 'data/raw' / f'raw-{i}.json').write_text(json.dumps(entry), 'utf-8')
    write_sqlite(tmp / 'data/efficiency.sqlite', prs)
    return tmp


class SourceCoverageTests(unittest.TestCase):
    def test_zero_coverage_with_applicable_objects_is_unverified(self):  # REQ-023 AC01
        category = SourceCategory('job_timing')
        for url in ['job/1/', 'job/2/']:
            category.record_applicable(url)
        report = source_report({'job_timing': category})
        job = report['categories']['job_timing']
        self.assertEqual(report['status'], 'unverified')
        self.assertEqual(job['status'], 'unverified')
        self.assertEqual((job['applicable'], job['verified_consistent'], job['differences'],
                          job['missing_evidence']), (2, 0, 0, 2))
        self.assertEqual(job['missing'], ['job/1/', 'job/2/'])

    def test_counts_add_up_and_identities_stay_traceable(self):  # REQ-023 AC02
        category = SourceCategory('job_timing')
        for url in ['job/1/', 'job/2/', 'job/3/', 'job/4/', 'job/5/']:
            category.record_applicable(url)
        for url in ['job/1/', 'job/2/', 'job/3/']:
            category.record_verified(url)
        category.record_difference('job/4/', 'raw(9, 9) != snapshot(1, 2)')
        result = category.result()
        self.assertEqual(result['applicable'],
                         result['verified_consistent'] + result['differences'] + result['missing_evidence'])
        self.assertEqual(result['status'], 'differences_found')
        self.assertEqual(result['missing'], ['job/5/'])
        self.assertEqual(result['difference_details'], ['job/4/: raw(9, 9) != snapshot(1, 2)'])

    def test_partial_coverage_keeps_missing_identities(self):  # REQ-023 AC03
        category = SourceCategory('job_timing')
        for url in ['job/1/', 'job/2/', 'job/3/']:
            category.record_applicable(url)
        category.record_verified('job/1/')
        report = source_report({'job_timing': category})
        job = report['categories']['job_timing']
        self.assertEqual(report['status'], 'partial')
        self.assertEqual(job['status'], 'partial')
        self.assertEqual((job['verified_consistent'], job['missing_evidence']), (1, 2))
        self.assertEqual(job['missing'], ['job/2/', 'job/3/'])

    def test_no_applicable_objects_is_not_applicable_with_reason(self):  # REQ-023 AC04
        report = source_report({'job_timing': SourceCategory('job_timing')})
        job = report['categories']['job_timing']
        self.assertEqual(report['status'], 'not_applicable')
        self.assertEqual(job['status'], 'not_applicable')
        self.assertEqual((job['applicable'], job['verified_consistent'], job['missing_evidence']), (0, 0, 0))
        self.assertEqual(job['missing'], [])
        self.assertTrue(job['reason'])

    def test_full_coverage_is_verified_without_reason(self):
        category = SourceCategory('job_timing')
        category.record_applicable('job/1/')
        category.record_verified('job/1/')
        report = source_report({'job_timing': category})
        job = report['categories']['job_timing']
        self.assertEqual(report['status'], 'verified')
        self.assertEqual(job['status'], 'verified')
        self.assertEqual(job['missing'], [])
        self.assertNotIn('reason', job)

    def test_difference_dominates_partial_coverage(self):
        category = SourceCategory('job_timing')
        for url in ['job/1/', 'job/2/', 'job/3/']:
            category.record_applicable(url)
        category.record_verified('job/1/')
        category.record_difference('job/2/', 'mismatch')
        report = source_report({'job_timing': category})
        self.assertEqual(report['status'], 'differences_found')
        self.assertEqual(report['categories']['job_timing']['status'], 'differences_found')

    def test_missing_list_is_capped_with_truncation_flag(self):
        category = SourceCategory('job_timing')
        for i in range(MISSING_LIMIT + 10):
            category.record_applicable(f'job/{i}/')
        result = category.result()
        self.assertEqual(result['missing_evidence'], MISSING_LIMIT + 10)
        self.assertEqual(len(result['missing']), MISSING_LIMIT)
        self.assertTrue(result['missing_truncated'])


class MultiAuditSourceCoverageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='req023-multi-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def audit(self):
        with patch.object(validate_multi, 'ROOT', self.tmp):
            return validate_multi.audit()

    def test_full_raw_coverage_passes_as_verified(self):
        prs = [pr_with_gate(7)]
        write_multi_tree(self.tmp, prs, raw_files(prs))
        report = self.audit()
        self.assertTrue(report['checks_passed'])
        self.assertEqual(report['source_audit']['status'], 'verified')
        job = report['source_audit']['categories']['job_timing']
        self.assertEqual((job['applicable'], job['verified_consistent'], job['missing_evidence'],
                          job['differences']), (2, 2, 0, 0))
        self.assertNotIn('raw_timing_records_checked', report)

    def test_zero_raw_coverage_fails_without_claiming_sources_passed(self):  # REQ-023 AC01
        prs = [pr_with_gate(7)]
        write_multi_tree(self.tmp, prs, raw_files([]))
        with self.assertRaises(SystemExit) as ctx:
            self.audit()
        self.assertIn('0/2', str(ctx.exception))
        report = json.loads((self.tmp / 'data/validation-multi.json').read_text('utf-8'))
        self.assertFalse(report['checks_passed'])
        self.assertEqual(report['source_audit']['status'], 'unverified')
        job = report['source_audit']['categories']['job_timing']
        self.assertEqual((job['verified_consistent'], job['missing_evidence']), (0, 2))
        self.assertEqual(sorted(job['missing']), sorted([trigger_job(7)['url'], child_job(7)['url']]))

    def test_partial_raw_coverage_fails_with_missing_identities(self):  # REQ-023 AC03
        prs = [pr_with_gate(7)]
        write_multi_tree(self.tmp, prs, raw_files(prs, drop=[child_job(7)['url']]))
        with self.assertRaises(SystemExit):
            self.audit()
        report = json.loads((self.tmp / 'data/validation-multi.json').read_text('utf-8'))
        self.assertFalse(report['checks_passed'])
        job = report['source_audit']['categories']['job_timing']
        self.assertEqual(report['source_audit']['status'], 'partial')
        self.assertEqual((job['applicable'], job['verified_consistent'], job['missing_evidence']), (2, 1, 1))
        self.assertEqual(job['missing'], [child_job(7)['url']])

    def test_raw_difference_is_reported_and_fails(self):  # REQ-023 AC02
        prs = [pr_with_gate(7)]
        write_multi_tree(self.tmp, prs, raw_files(prs, tamper=(child_job(7)['url'], 999)))
        with self.assertRaises(SystemExit) as ctx:
            self.audit()
        self.assertIn('differences', str(ctx.exception))
        report = json.loads((self.tmp / 'data/validation-multi.json').read_text('utf-8'))
        self.assertFalse(report['checks_passed'])
        job = report['source_audit']['categories']['job_timing']
        self.assertEqual(report['source_audit']['status'], 'differences_found')
        self.assertEqual((job['verified_consistent'], job['differences'], job['missing_evidence']), (1, 1, 0))
        self.assertEqual(len(job['difference_details']), 1)
        self.assertIn(child_job(7)['url'], job['difference_details'][0])

    def test_no_applicable_jobs_is_not_applicable_and_passes(self):  # REQ-023 AC04
        prs = [pr_without_gate()]
        write_multi_tree(self.tmp, prs, raw_files(prs))
        report = self.audit()
        self.assertTrue(report['checks_passed'])
        job = report['source_audit']['categories']['job_timing']
        self.assertEqual(job['status'], 'not_applicable')
        self.assertEqual(job['applicable'], 0)
        self.assertTrue(job['reason'])


class SingleRepoValidateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='req023-single-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def write_tree(self, prs, raw):
        shutil.copyfile(ROOT / 'validate.py', self.tmp / 'validate.py')
        shutil.copyfile(ROOT / 'source_coverage.py', self.tmp / 'source_coverage.py')
        (self.tmp / 'data/raw').mkdir(parents=True)
        (self.tmp / 'web/data').mkdir(parents=True)
        snapshot = {'meta': {'repository': REPO, 'collected_at': '2026-10-09T00:00:00+08:00', 'start_ms': 1000,
                             'end_ms': 2000, 'expected_prs': len(prs)}, 'prs': prs}
        (self.tmp / 'data/snapshot.json').write_text(json.dumps(snapshot, ensure_ascii=False), 'utf-8')
        (self.tmp / 'web/data/snapshot.json').write_bytes((self.tmp / 'data/snapshot.json').read_bytes())
        for i, entry in enumerate(raw):
            (self.tmp / 'data/raw' / f'raw-{i}.json').write_text(json.dumps(entry), 'utf-8')
        write_sqlite(self.tmp / 'data/efficiency.sqlite', prs)

    def run_validate(self):
        return subprocess.run([sys.executable, '-X', 'utf8', str(self.tmp / 'validate.py')],
                              capture_output=True, text=True, encoding='utf-8', check=False)

    def test_full_coverage_passes(self):
        prs = [pr_with_gate(7), pr_with_gate(9)]  # two PRs: p90 needs more than one representative
        self.write_tree(prs, raw_files(prs))
        proc = self.run_validate()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads((self.tmp / 'data/validation.json').read_text('utf-8'))
        self.assertTrue(report['checks_passed'])
        self.assertEqual(report['source_audit']['status'], 'verified')
        job = report['source_audit']['categories']['job_timing']
        self.assertEqual((job['applicable'], job['verified_consistent']), (4, 4))

    def test_zero_coverage_fails_unverified(self):  # REQ-023 AC01
        prs = [pr_with_gate(7), pr_with_gate(9)]
        self.write_tree(prs, raw_files([]))
        proc = self.run_validate()
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn('0/4', proc.stderr)
        report = json.loads((self.tmp / 'data/validation.json').read_text('utf-8'))
        self.assertFalse(report['checks_passed'])
        self.assertEqual(report['source_audit']['status'], 'unverified')
        self.assertEqual(report['source_audit']['categories']['job_timing']['missing_evidence'], 4)


if __name__ == '__main__':
    unittest.main()
