"""REQ-046: keep the audited Triton statistics and data boundaries honest.

The audit (audit/2026-10-09, checks D08/D09/A13-e2e/A13-npu) verified the
derived statistics against a frozen input: 38 PRs / 66 batches / 65 completion
samples / 48 NPU queue points. That exact snapshot is committed as
tests/fixtures/triton-audit-freeze.json so the recomputations stay pinned,
while the live-data checks run against whatever web/data the pipeline just
produced — new data is computed by contract, never by frozen counts.
"""
import json
import math
import unittest
from collections import Counter
from datetime import datetime
from pathlib import Path

from triton.dashboard import build_batches, percentile

ROOT = Path(__file__).resolve().parents[1]
FREEZE = ROOT / 'tests' / 'fixtures' / 'triton-audit-freeze.json'
AUDIT_EVIDENCE = ROOT / 'audit' / '2026-10-09' / 'evidence' / 'data-audit.json'


def stamp(text):
    return datetime.fromisoformat(text.replace('Z', '+00:00')).timestamp() if text else None


def pct(values, q):
    values = sorted(values)
    if not values:
        return None
    position = (len(values) - 1) * q
    lower, upper = math.floor(position), math.ceil(position)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def same(actual, expected):
    if isinstance(actual, (int, float)) and not isinstance(actual, bool) \
            and isinstance(expected, (int, float)) and not isinstance(expected, bool):
        return math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-6)
    return actual == expected


def recompute_summary(batches):
    values = [b['duration_seconds'] for b in batches
              if b['status'] in ('success', 'failure')
              and isinstance(b.get('duration_seconds'), (int, float))
              and b['duration_seconds'] >= 0]
    return {
        'prs': len({b['pr'] for b in batches if b.get('pr')}),
        'batches': len(batches),
        'valid': len(values),
        'median': pct(values, .5),
        'p90': pct(values, .9),
        'approximate': sum(bool(b.get('approximate')) for b in batches),
        'incomplete': sum(bool(b.get('missing')) for b in batches),
    }


class FrozenTritonSnapshotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(FREEZE.read_text(encoding='utf-8'))
        cls.batches = cls.payload['batches']

    def assertSameDict(self, actual, expected):
        for key, value in expected.items():
            self.assertTrue(same(actual[key], value), f'{key}: {actual[key]!r} != {value!r}')

    def test_d08_summary_and_npu_points_independently_recompute(self):
        # REQ-046 AC01: 38 PRs / 66 batches / 65 completion samples / 48 NPU
        # queue points recompute from the frozen input and match the summary.
        recomputed = recompute_summary(self.batches)
        self.assertSameDict(recomputed, {k: self.payload['summary'][k] for k in recomputed})
        self.assertSameDict(recomputed, {'prs': 38, 'batches': 66, 'valid': 65,
                                         'median': 1580.0, 'p90': 3620.2000000000003,
                                         'approximate': 66, 'incomplete': 0})
        self.assertEqual(sum(b.get('npu_queue_seconds') is not None for b in self.batches), 48)

    def test_d09_npu_wait_and_batch_maximum_recompute(self):
        # REQ-046 AC01: every NPU wait = started−created (None when unparseable
        # or inverted) and every batch queue = max of valid waits unless
        # npu_data_missing — the audit's D09 recomputation still holds.
        mismatches = checked = 0
        for batch in self.batches:
            for job in batch.get('npu_jobs', []):
                checked += 1
                created, started = stamp(job.get('created_at')), stamp(job.get('started_at'))
                expected = started - created if created is not None and started is not None and started >= created else None
                if not same(job.get('wait_seconds'), expected):
                    mismatches += 1
            waits = [j['wait_seconds'] for j in batch.get('npu_jobs', []) if j.get('wait_seconds') is not None]
            expected_max = max(waits) if waits and not batch.get('npu_data_missing') else None
            if not same(batch.get('npu_queue_seconds'), expected_max):
                mismatches += 1
        self.assertEqual(mismatches, 0)
        self.assertGreater(checked, 0)

    def test_d09_e2e_recomputes_from_retained_workflows(self):
        # REQ-046 AC01: approximate E2E = wall-clock span from the earliest
        # workflow creation to the last completion (window_end while running).
        mismatches = checked = 0
        for batch in self.batches:
            if not batch.get('approximate'):
                continue
            checked += 1
            workflows = batch['workflows']
            beg = min(stamp(w['created_at']) for w in workflows)
            fin = max(stamp(w['updated_at']) for w in workflows) if batch['status'] != 'running' \
                else stamp(self.payload['window_end'])
            if not same(batch['duration_seconds'], max(0, fin - beg)):
                mismatches += 1
        self.assertEqual(mismatches, 0)
        self.assertEqual(checked, len(self.batches))

    def test_inverted_npu_jobs_stay_excluded_not_deleted(self):
        # REQ-046 AC02: the 9 inverted-timestamp NPU jobs across 5 batches keep
        # wait=None (queue unknown) and stay in the snapshot — boundaries are
        # disclosed, never deleted or zero-filled to hide the defect.
        inverted = [(batch, job) for batch in self.batches for job in batch.get('npu_jobs', [])
                    if stamp(job.get('started_at')) is not None and stamp(job.get('created_at')) is not None
                    and stamp(job['started_at']) < stamp(job['created_at'])]
        self.assertEqual(len(inverted), 9)
        self.assertEqual(len({batch['id'] for batch, _ in inverted}), 5)
        self.assertTrue(all(job.get('wait_seconds') is None for _, job in inverted))
        for batch, _ in inverted:
            waits = [j['wait_seconds'] for j in batch['npu_jobs'] if j.get('wait_seconds') is not None]
            expected_max = max(waits) if waits and not batch.get('npu_data_missing') else None
            self.assertTrue(same(batch.get('npu_queue_seconds'), expected_max))

    def test_all_batches_approximate_visible(self):
        # REQ-046 AC02: all 66 batches keep the approximate-start marker.
        self.assertEqual(sum(1 for b in self.batches if b.get('approximate')), 66)
        self.assertEqual(self.payload['summary']['approximate'], 66)

    def test_cancelled_batch_is_observed_but_not_a_completion_sample(self):
        # REQ-046 AC03: a Triton cancelled batch keeps its observed duration
        # and stays visible, but never enters the completion-sample statistics
        # (65 valid of 66) — unlike UBS where cancelled-but-ended batches are
        # failure-experience data inside E2E.
        cancelled = [b for b in self.batches if b['status'] == 'cancelled']
        self.assertEqual(len(cancelled), 1)
        self.assertEqual(cancelled[0]['duration_seconds'], 37022.0)
        self.assertIsNone(cancelled[0].get('npu_queue_seconds'))
        self.assertEqual(self.payload['summary']['valid'], 65)
        npu_points = [b for b in self.batches if b.get('npu_queue_seconds') is not None]
        self.assertEqual(len(npu_points), 48)
        self.assertTrue(all(b['status'] in ('success', 'failure') for b in npu_points))


class FrozenUbsBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.evidence = json.loads(AUDIT_EVIDENCE.read_text(encoding='utf-8'))

    def test_audit_evidence_pins_the_frozen_boundaries(self):
        # REQ-046 AC03: the audit recorded the UBS boundaries — 12 requests
        # without trigger, 6 batches without a unique request, 17 incomplete,
        # 2 running, 16 cancelled — with D03/D08/D09 all passed.
        gaps = self.evidence['ubs']['known_gaps']
        self.assertEqual((gaps['unlinked_events'], gaps['missing_request'],
                          gaps['status_incomplete'], gaps['status_running'], gaps['cancelled']),
                         (12, 6, 17, 2, 16))
        self.assertEqual({c['id']: c['state'] for c in self.evidence['checks']
                          if c['id'] in ('D03', 'D08', 'D09')},
                         {'D03': 'passed', 'D08': 'passed', 'D09': 'passed'})
        triton = self.evidence['triton']
        self.assertEqual((triton['npu_points'], len(triton['warnings']),
                          len({w['batch'] for w in triton['warnings']})), (48, 9, 5))

    def test_local_ubs_boundaries_stay_traceable(self):
        # REQ-046 AC03: whatever snapshot is on disk keeps every boundary
        # category countable; while the disk still carries the audit freeze
        # (203 PRs / 826 batches) the boundaries must match the audit exactly.
        index_path = ROOT / 'web' / 'data' / 'repositories.json'
        if not index_path.exists():
            self.skipTest('no local UBS snapshot (collect or restore first)')
        index = json.loads(index_path.read_text(encoding='utf-8'))
        counters = Counter()
        prs = batches = 0
        for entry in index['repositories']:
            snapshot = json.loads((ROOT / 'web' / 'data' / entry['snapshot']).read_text(encoding='utf-8'))
            prs += len(snapshot['prs'])
            for pr in snapshot['prs']:
                ids = {e['id'] for e in pr['events']}
                linked = {b.get('event_id') for b in pr['batches']}
                counters['unlinked_events'] += sum(e['id'] not in linked for e in pr['events'])
                for b in pr['batches']:
                    batches += 1
                    counters['status_' + b['status']] += 1
                    counters['cancelled'] += bool(b.get('cancelled'))
                    counters['missing_request'] += b.get('request_ms') is None
                    counters['orphan_nonempty_event'] += bool(b.get('event_id')) and b['event_id'] not in ids
        self.assertEqual(sum(v for k, v in counters.items() if k.startswith('status_')), batches)
        self.assertNotIn('status_cancelled', counters)  # UBS cancelled is an orthogonal flag, not a status
        if (prs, batches) == (203, 826):
            frozen = self.evidence['ubs']['known_gaps']
            self.assertEqual({k: counters[k] for k in frozen}, dict(frozen))


class ContractShapeTests(unittest.TestCase):
    def test_zero_npu_batch_is_legal_with_null_queue(self):
        # REQ-046 AC04: a batch with no NPU jobs is legal — the queue stays
        # None and npu_data_missing stays False (zero NPU ≠ missing NPU).
        job = {'id': 7, 'name': 'integration-tests (linux-amd64, py3.12)', 'status': 'completed',
               'conclusion': 'success', 'created_at': '2026-09-28T01:00:00Z',
               'started_at': '2026-09-28T01:00:14Z', 'completed_at': '2026-09-28T02:00:00Z'}
        row = {'id': 1, 'name': 'Example', 'head_sha': 'abc', 'created_at': '2026-09-28T01:00:00Z',
               'updated_at': '2026-09-28T02:00:00Z', 'status': 'completed', 'conclusion': 'success',
               'run_attempt': 1, 'html_url': 'https://github.com/example/actions/runs/1', 'jobs': [job],
               'jobs_complete': True, 'pr': 42, 'pr_title': 'synthetic',
               'pr_url': 'https://github.com/example/pull/42', 'base_branch': 'main', 'trigger_exact': False}
        batch = build_batches([row], '2026-09-28T03:00:00Z')[0]
        self.assertEqual(batch['npu_jobs'], [])
        self.assertIsNone(batch['npu_queue_seconds'])
        self.assertFalse(batch['npu_data_missing'])

    def test_single_sample_percentiles_equal_the_value(self):
        # REQ-046 AC04: a single sample expresses itself — mean=P50=P90=value.
        self.assertEqual(percentile([2122.0], .5), 2122.0)
        self.assertEqual(percentile([2122.0], .9), 2122.0)

    def test_live_data_self_consistent_by_contract(self):
        # REQ-046 AC04: whatever the pipeline just produced recomputes to its
        # own summary and the duration=start→end contract — new data follows
        # the contract, never the old snapshot's frozen counts.
        live = ROOT / 'web' / 'data' / 'triton.json'
        if not live.exists():
            self.skipTest('no local Triton snapshot (collect first)')
        payload = json.loads(live.read_text(encoding='utf-8'))
        recomputed = recompute_summary(payload['batches'])
        for key, value in recomputed.items():
            self.assertTrue(same(value, payload['summary'][key]),
                            f'{key}: {value!r} != {payload["summary"][key]!r}')
        for batch in payload['batches']:
            if batch.get('duration_seconds') is None:
                continue
            start, end = stamp(batch.get('start_at')), stamp(batch.get('end_at'))
            self.assertIsNotNone(start, batch['id'])
            self.assertIsNotNone(end, batch['id'])
            self.assertAlmostEqual(end - start, batch['duration_seconds'], delta=0.5, msg=batch['id'])


if __name__ == '__main__':
    unittest.main()
