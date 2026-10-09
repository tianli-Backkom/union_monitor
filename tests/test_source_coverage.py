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
from source_coverage import MISSING_LIMIT, SourceCategory, queue_from_raw, source_report

ROOT = Path(__file__).resolve().parents[1]
REPO = 'openeuler/ubs-test'


def trigger_job(number, queue_ms=50):
    return {'url': f'https://ci.example/job/ubs-test/job/trigger/{number}/', 'number': number, 'result': 'SUCCESS',
            'building': False, 'start_ms': 1000, 'end_ms': 1200, 'duration_ms': 200, 'queue_ms': queue_ms,
            'total_ms': queue_ms + 200 if queue_ms is not None else None,
            'scheduled_ms': 1000 - queue_ms if queue_ms is not None else None, 'causes': []}


def child_job(number, queue_ms=100, kind='x86', association_valid=False, causes=None):
    return {'url': f'https://ci.example/job/ubs-test/job/{kind}/{number}/', 'number': number, 'result': 'SUCCESS',
            'building': False, 'start_ms': 1100, 'end_ms': 1400, 'duration_ms': 300, 'queue_ms': queue_ms,
            'total_ms': queue_ms + 300 if queue_ms is not None else None,
            'scheduled_ms': 1100 - queue_ms if queue_ms is not None else None, 'kind': kind,
            'association_valid': association_valid, 'causes': causes if causes is not None else []}


def empty_kind():
    return {'url': None, 'queue_ms': None, 'duration_ms': None, 'total_ms': None}


def pr_with_gate(number, trigger_queue=50, child_queue=100, child_associated=False):
    child = child_job(number, queue_ms=child_queue, association_valid=child_associated,
                      causes=[{'upstreamBuild': number, 'upstreamProject': 'ubs-test/trigger'}] if child_associated else [])
    trigger = trigger_job(number, queue_ms=trigger_queue)
    batch = {'url': trigger['url'], 'number': number, 'status': 'success', 'complete': True, 'eligible': True,
             'request_ms': 1000, 'e2e_ms': 400, 'cancelled': False, 'trigger': trigger, 'children': [child]}
    metrics = {'representative_batch_url': trigger['url'], 'representative_batch_number': number, 'e2e_ms': 400,
               'x86': ({'url': child['url'], 'queue_ms': child['queue_ms'], 'duration_ms': child['duration_ms'],
                        'total_ms': child['total_ms']} if child_associated else empty_kind()),
               'arm': empty_kind(), 'dt': empty_kind()}
    return {'number': number, 'state': 'merged', 'created_ms': 1500, 'repository': REPO,
            'batches': [batch], 'metrics': metrics}


def pr_without_gate():
    return {'number': 8, 'state': 'open', 'created_ms': 1600, 'repository': REPO, 'batches': [],
            'metrics': {'representative_batch_url': None, 'representative_batch_number': None, 'e2e_ms': None,
                        'x86': empty_kind(), 'arm': empty_kind(), 'dt': empty_kind()}}


def raw_files(prs, drop=(), tamper=None, strip_components=(), components_override=None):
    """One cached Jenkins allBuilds response per job; empty input means zero raw evidence.

    Queue components default to a split summing to the job's queue_ms (None →
    no components action); strip_components drops the action for selected URLs,
    tamper is (url, {field: value}), components_override is {url: (w, b, g)}.
    """
    files = {}
    for pr in prs:
        for batch in pr['batches']:
            for job in [batch['trigger']] + batch['children']:
                entry = {'url': job['url'], 'timestamp': job['start_ms'], 'duration': job['duration_ms']}
                if job['url'] not in strip_components:
                    if components_override and job['url'] in components_override:
                        w, b, g = components_override[job['url']]
                    elif job['queue_ms'] is not None:
                        w, b, g = job['queue_ms'] - 10, 6, 4
                    else:
                        w, b, g = None, None, None
                    if w is not None:
                        entry['actions'] = [{'waitingTimeMillis': w, 'blockedTimeMillis': b, 'buildableTimeMillis': g}]
                files[job['url']] = {'url': job['url'], 'body': {'allBuilds': [entry]}}
    for url in drop:
        files.pop(url, None)
    if tamper is not None:
        url, fields = tamper
        entry = files[url]['body']['allBuilds'][0]
        for field, value in fields.items():
            if field in ('waitingTimeMillis', 'blockedTimeMillis', 'buildableTimeMillis'):
                entry.setdefault('actions', [{}])[0][field] = value  # components live inside the queue action
            else:
                entry[field] = value
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

    def test_derived_bucket_keeps_equation_and_partial_status(self):  # REQ-024 AC04
        category = SourceCategory('queue_components')
        for url in ['job/1/', 'job/2/', 'job/3/', 'job/4/']:
            category.record_applicable(url)
        category.record_verified('job/1/')
        category.record_derived('job/2/')
        result = category.result()
        self.assertEqual(result['status'], 'partial')
        self.assertEqual(result['derived_consistent'], 1)
        self.assertEqual(result['applicable'],
                         result['verified_consistent'] + result['derived_consistent'] + result['differences'] + result['missing_evidence'])
        self.assertEqual(result['missing'], ['job/3/', 'job/4/'])

    def test_all_derived_without_raw_verification_is_unverified(self):  # REQ-024 AC04
        category = SourceCategory('queue_components')
        for url in ['job/1/', 'job/2/']:
            category.record_applicable(url)
            category.record_derived(url)
        report = source_report({'queue_components': category})
        self.assertEqual(report['status'], 'unverified')
        self.assertEqual(report['categories']['queue_components']['derived_consistent'], 2)

    def test_verified_absence_counts_as_verified_with_subcount(self):  # REQ-024 AC02
        category = SourceCategory('queue_components')
        category.record_applicable('job/1/')
        category.record_verified_absence('job/1/')
        result = category.result()
        self.assertEqual(result['status'], 'verified')
        self.assertEqual((result['verified_consistent'], result['verified_absent']), (1, 1))
        self.assertEqual(result['derived_consistent'], 0)

    def test_queue_from_raw_mirrors_normalize_job(self):  # REQ-024 AC01/AC02
        queue, parts = queue_from_raw({'actions': [{'waitingTimeMillis': 12, 'blockedTimeMillis': 5, 'buildableTimeMillis': 3}]})
        self.assertEqual(queue, 20)
        self.assertEqual(parts, {'waitingTimeMillis': 12, 'blockedTimeMillis': 5, 'buildableTimeMillis': 3})
        self.assertEqual(queue_from_raw({'actions': [{'waitingTimeMillis': 12}]}), (None, None))
        self.assertEqual(queue_from_raw({'actions': [{'waitingTimeMillis': 'x', 'blockedTimeMillis': 5, 'buildableTimeMillis': 3}]}), (None, None))
        self.assertEqual(queue_from_raw({}), (None, None))


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
        write_multi_tree(self.tmp, prs, raw_files(prs, tamper=(child_job(7)['url'], {'duration': 999})))
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


class QueueComponentAuditTests(unittest.TestCase):
    """REQ-024 — queue/total must trace to raw waiting/blocked/buildable components."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='req024-multi-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def audit(self):
        with patch.object(validate_multi, 'ROOT', self.tmp):
            return validate_multi.audit()

    def test_queue_components_verified_from_raw(self):  # REQ-024 AC01
        prs = [pr_with_gate(7, trigger_queue=20, child_queue=20, child_associated=True)]
        batch = prs[0]['batches'][0]
        override = {batch['trigger']['url']: (12, 5, 3), batch['children'][0]['url']: (12, 5, 3)}
        write_multi_tree(self.tmp, prs, raw_files(prs, components_override=override))
        report = self.audit()
        self.assertTrue(report['checks_passed'])
        self.assertEqual(report['source_audit']['status'], 'verified')
        queue = report['source_audit']['categories']['queue_components']
        self.assertEqual((queue['applicable'], queue['verified_consistent'], queue['derived_consistent'],
                          queue['missing_evidence'], queue['differences']), (2, 2, 0, 0, 0))
        self.assertEqual(report['source_audit']['categories']['job_timing']['status'], 'verified')
        self.assertEqual(report['metrics']['x86']['queue'], {'n': 1, 'mean': 20, 'p90': 20})  # verified value flows into statistics

    def test_missing_component_keeps_queue_unknown(self):  # REQ-024 AC02
        prs = [pr_with_gate(7, child_queue=None)]
        write_multi_tree(self.tmp, prs, raw_files(prs))
        report = self.audit()
        self.assertTrue(report['checks_passed'])
        queue = report['source_audit']['categories']['queue_components']
        self.assertEqual((queue['verified_consistent'], queue['verified_absent'], queue['derived_consistent'],
                          queue['differences'], queue['missing_evidence']), (2, 1, 0, 0, 0))
        child = prs[0]['batches'][0]['children'][0]
        self.assertIsNone(child['queue_ms'])  # unknown stays unknown, known duration retained
        self.assertEqual(report['source_audit']['categories']['job_timing']['verified_consistent'], 2)

    def test_tampered_raw_component_detected_with_url_and_field(self):  # REQ-024 AC03
        prs = [pr_with_gate(7)]
        trigger_url = prs[0]['batches'][0]['trigger']['url']
        write_multi_tree(self.tmp, prs, raw_files(prs, tamper=(trigger_url, {'waitingTimeMillis': 999})))
        with self.assertRaises(SystemExit):
            self.audit()
        report = json.loads((self.tmp / 'data/validation-multi.json').read_text('utf-8'))
        self.assertFalse(report['checks_passed'])
        queue = report['source_audit']['categories']['queue_components']
        self.assertEqual(queue['status'], 'differences_found')
        self.assertEqual(report['source_audit']['categories']['job_timing']['status'], 'verified')
        self.assertEqual(len(queue['difference_details']), 1)
        self.assertIn(trigger_url, queue['difference_details'][0])
        self.assertIn('waiting=999', queue['difference_details'][0])

    def test_queue_report_distinguishes_three_buckets(self):  # REQ-024 AC04
        number = 7
        trigger = trigger_job(number, queue_ms=50)
        child_derived = child_job(number, queue_ms=100, kind='x86')   # raw present, components stripped
        child_missing = child_job(number, queue_ms=100, kind='arm')  # no raw record at all
        batch = {'url': trigger['url'], 'number': number, 'status': 'success', 'complete': True, 'eligible': True,
                 'request_ms': 1000, 'e2e_ms': 400, 'cancelled': False, 'trigger': trigger,
                 'children': [child_derived, child_missing]}
        metrics = {'representative_batch_url': trigger['url'], 'representative_batch_number': number, 'e2e_ms': 400,
                   'x86': empty_kind(), 'arm': empty_kind(), 'dt': empty_kind()}
        prs = [{'number': number, 'state': 'merged', 'created_ms': 1500, 'repository': REPO,
                'batches': [batch], 'metrics': metrics}]
        raw = raw_files(prs, drop=[child_missing['url']], strip_components=[child_derived['url']])
        write_multi_tree(self.tmp, prs, raw)
        with self.assertRaises(SystemExit):
            self.audit()
        report = json.loads((self.tmp / 'data/validation-multi.json').read_text('utf-8'))
        queue = report['source_audit']['categories']['queue_components']
        self.assertEqual(queue['applicable'],
                         queue['verified_consistent'] + queue['derived_consistent'] + queue['differences'] + queue['missing_evidence'])
        self.assertEqual((queue['verified_consistent'], queue['derived_consistent'], queue['missing_evidence']), (1, 1, 1))
        self.assertEqual(queue['status'], 'partial')
        self.assertEqual(queue['missing'], [child_missing['url']])


class AuditStatusSemanticsTests(unittest.TestCase):
    """REQ-025 — per-section statuses, explicit overall, and crash containment."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='req025-multi-'))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def audit(self):
        with patch.object(validate_multi, 'ROOT', self.tmp):
            return validate_multi.audit()

    def test_derived_passed_and_source_unverified_reported_explicitly(self):  # REQ-025 AC01
        prs = [pr_with_gate(7)]
        write_multi_tree(self.tmp, prs, raw_files([]))
        with self.assertRaises(SystemExit):
            self.audit()
        report = json.loads((self.tmp / 'data/validation-multi.json').read_text('utf-8'))
        self.assertEqual(report['sections']['derived_consistency']['status'], 'passed')
        self.assertEqual(report['sections']['source_time']['status'], 'unverified')
        self.assertEqual(report['sections']['queue_components']['status'], 'unverified')
        self.assertEqual(report['overall_status'], 'unverified')
        self.assertFalse(report['checks_passed'])

    def test_partial_coverage_overall_partial(self):  # REQ-025 AC01
        prs = [pr_with_gate(7)]
        write_multi_tree(self.tmp, prs, raw_files(prs, drop=[child_job(7)['url']]))
        with self.assertRaises(SystemExit):
            self.audit()
        report = json.loads((self.tmp / 'data/validation-multi.json').read_text('utf-8'))
        self.assertEqual(report['overall_status'], 'partial')
        self.assertEqual(report['sections']['source_time']['status'], 'partial')
        self.assertFalse(report['checks_passed'])

    def test_difference_is_failed_not_unverified(self):  # REQ-025 AC02
        prs = [pr_with_gate(7)]
        write_multi_tree(self.tmp, prs, raw_files(prs, tamper=(child_job(7)['url'], {'duration': 999})))
        with self.assertRaises(SystemExit):
            self.audit()
        report = json.loads((self.tmp / 'data/validation-multi.json').read_text('utf-8'))
        self.assertEqual(report['sections']['source_time']['status'], 'differences_found')
        self.assertEqual(report['overall_status'], 'differences_found')
        self.assertNotEqual(report['overall_status'], 'unverified')

    def test_not_applicable_sections_explain_reasons(self):  # REQ-025 AC02
        prs = [pr_without_gate()]
        write_multi_tree(self.tmp, prs, raw_files(prs))
        report = self.audit()
        self.assertTrue(report['checks_passed'])
        self.assertEqual(report['overall_status'], 'not_applicable')
        source_time = report['sections']['source_time']
        self.assertEqual(source_time['status'], 'not_applicable')
        self.assertTrue(source_time['reason'])
        publish = report['sections']['publish_consistency']
        self.assertEqual(publish['status'], 'not_applicable')
        self.assertIn('validate_bundle', publish['reason'])

    def test_full_coverage_overall_verified_and_exit_consistent(self):  # REQ-025 AC04
        prs = [pr_with_gate(7)]
        write_multi_tree(self.tmp, prs, raw_files(prs))
        report = self.audit()
        self.assertTrue(report['checks_passed'])
        self.assertEqual(report['overall_status'], 'verified')
        self.assertEqual(report['sections']['derived_consistency']['status'], 'passed')
        self.assertEqual(report['sections']['source_time']['status'], 'verified')
        self.assertEqual(report['sections']['queue_components']['status'], 'verified')

    def test_audit_crash_writes_failure_report_and_preserves_error(self):  # REQ-025 AC03
        prs = [pr_with_gate(7)]
        write_multi_tree(self.tmp, prs, raw_files(prs))
        snapshot_path = self.tmp / 'data/repos/ubs-test.json'
        snapshot = json.loads(snapshot_path.read_text('utf-8'))
        snapshot['prs'][0]['repository'] = 'openeuler/wrong-repo'  # violates the derived identity assert
        snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), 'utf-8')
        (self.tmp / 'web/data/repos/ubs-test.json').write_text(snapshot_path.read_text('utf-8'))  # keep the mirror identical
        with self.assertRaises(AssertionError):
            self.audit()
        report = json.loads((self.tmp / 'data/validation-multi.json').read_text('utf-8'))
        self.assertEqual(report['overall_status'], 'failed')
        self.assertFalse(report['checks_passed'])
        self.assertIn('AssertionError', report['error'])
        self.assertTrue(report['affected_scope'])


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
        self.assertEqual(report['overall_status'], 'verified')
        self.assertEqual(report['sections']['derived_consistency']['status'], 'passed')
        self.assertEqual(report['sections']['queue_components']['status'], 'verified')

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

    def test_queue_tamper_fails_with_url_and_field(self):  # REQ-024 AC03
        prs = [pr_with_gate(7), pr_with_gate(9)]
        trigger_url = prs[0]['batches'][0]['trigger']['url']
        self.write_tree(prs, raw_files(prs, tamper=(trigger_url, {'waitingTimeMillis': 999})))
        proc = self.run_validate()
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads((self.tmp / 'data/validation.json').read_text('utf-8'))
        self.assertFalse(report['checks_passed'])
        queue = report['source_audit']['categories']['queue_components']
        self.assertEqual(queue['status'], 'differences_found')
        self.assertIn(trigger_url, queue['difference_details'][0])
        self.assertIn('waiting=999', queue['difference_details'][0])

    def test_crash_writes_failure_report_and_preserves_error(self):  # REQ-025 AC03
        prs = [pr_with_gate(7), pr_with_gate(9)]
        self.write_tree(prs, raw_files(prs))
        snapshot_path = self.tmp / 'data/snapshot.json'
        snapshot = json.loads(snapshot_path.read_text('utf-8'))
        snapshot['prs'][0]['batches'][0]['e2e_ms'] = 12345  # violates the derived e2e assert
        snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False), 'utf-8')
        (self.tmp / 'web/data/snapshot.json').write_text(snapshot_path.read_text('utf-8'))
        proc = self.run_validate()
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads((self.tmp / 'data/validation.json').read_text('utf-8'))
        self.assertEqual(report['overall_status'], 'failed')
        self.assertFalse(report['checks_passed'])
        self.assertIn('AssertionError', report['error'])
        self.assertTrue(report['affected_scope'])


if __name__ == '__main__':
    unittest.main()
