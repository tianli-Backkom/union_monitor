"""REQ-037: the minimal dev/acceptance fixtures follow the current statistics contract.

The audit (S05, F19) found the hand-crafted minimal Triton fixture drifting from
the live contract: kind "push" instead of initial/rerun, a summary P90 of 900 for
[600,600,900] (linear interpolation gives 840), and no loadable zero-data /
single-sample / missing-value / rerun scenarios. These tests recompute every
derived value from the fixture inputs themselves — not just field presence.
"""
import json
import math
import unittest
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MINIMAL = ROOT / 'tests' / 'fixtures' / 'minimal'


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


def load(name):
    return json.loads((MINIMAL / name).read_text(encoding='utf-8'))


class MinimalTritonContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = load('triton.json')
        cls.batches = cls.payload['batches']

    def test_ac01_p90_is_interpolated_not_the_max_sample(self):
        # REQ-037 AC01: [600,600,900] linearly interpolates to 840, never 900.
        samples = sorted(b['duration_seconds'] for b in self.batches
                         if b['status'] in ('success', 'failure')
                         and isinstance(b.get('duration_seconds'), (int, float))
                         and b['duration_seconds'] >= 0)
        self.assertEqual(samples, [600, 600, 900])
        self.assertTrue(same(self.payload['summary']['p90'], 840))
        self.assertNotEqual(self.payload['summary']['p90'], 900)

    def test_ac02_summary_recomputes_from_same_input(self):
        # REQ-037 AC02: every summary field recomputes from the batches alone.
        recomputed = recompute_summary(self.batches)
        for key, value in recomputed.items():
            self.assertTrue(same(value, self.payload['summary'][key]),
                            f'{key}: {value!r} != {self.payload["summary"][key]!r}')
        self.assertEqual(self.payload['summary']['api_calls'], 0)

    def test_ac02_kind_follows_initial_rerun_semantics(self):
        # REQ-037 AC02: kind is initial/rerun; a rerun shares the PR+head SHA of
        # its initial batch but keeps its own attempt identity (no "push" kind).
        kinds = {b['kind'] for b in self.batches}
        self.assertTrue(kinds <= {'initial', 'rerun'}, kinds)
        reruns = [b for b in self.batches if b['kind'] == 'rerun']
        self.assertEqual(len(reruns), 1)
        rerun = reruns[0]
        sibling = next(b for b in self.batches
                       if b['kind'] == 'initial' and b['pr'] == rerun['pr'] and b['sha'] == rerun['sha'])
        self.assertEqual(sibling['e2e_index'], 1)
        self.assertEqual(rerun['start_source'], 'attempt_start')
        self.assertEqual(rerun['workflows'][0]['attempt'], 2)
        self.assertTrue(all(b['start_source'] == 'workflow_created'
                            for b in self.batches if b['kind'] == 'initial'))

    def test_ac03_missing_value_batch_stays_out_of_completion_samples(self):
        # REQ-037 AC03 (缺值): a completed batch without end evidence keeps
        # duration None, discloses the gap in missing[], never joins valid.
        gap = next(b for b in self.batches if b['duration_seconds'] is None)
        self.assertEqual(gap['status'], 'success')
        self.assertEqual(gap['missing'], ['无完成时间证据，E2E 留空'])
        self.assertFalse(gap['complete'])
        self.assertEqual(gap['npu_jobs'], [])
        self.assertIsNone(gap['npu_queue_seconds'])
        self.assertFalse(gap['npu_data_missing'])  # zero NPU ≠ missing NPU
        self.assertEqual(self.payload['summary']['incomplete'], 1)

    def test_ac03_running_batch_observes_to_window_end(self):
        # REQ-037 AC03 (最小数据含运行中): running keeps observed duration to
        # window_end and never enters the completed-sample statistics.
        running = next(b for b in self.batches if b['status'] == 'running')
        self.assertIsNone(running['end_at'])
        expected = stamp(self.payload['window_end']) - stamp(running['start_at'])
        self.assertTrue(same(running['duration_seconds'], expected))
        self.assertEqual(self.payload['summary']['valid'], 3)

    def test_ac03_durations_and_npu_queue_recompute(self):
        # REQ-037 AC03: direct results, not field presence — durations equal
        # end−start, NPU waits equal started−created, queue is the batch max.
        for batch in self.batches:
            if batch['duration_seconds'] is not None and batch['end_at']:
                span = stamp(batch['end_at']) - stamp(batch['start_at'])
                self.assertTrue(same(batch['duration_seconds'], span), batch['id'])
            for job in batch['npu_jobs']:
                wait = stamp(job['started_at']) - stamp(job['created_at'])
                self.assertTrue(same(job['wait_seconds'], wait), job['url'])
            waits = [j['wait_seconds'] for j in batch['npu_jobs'] if j.get('wait_seconds') is not None]
            expected = max(waits) if waits and not batch['npu_data_missing'] else None
            self.assertTrue(same(batch['npu_queue_seconds'], expected), batch['id'])
        by_pr = {}
        for batch in sorted(self.batches, key=lambda b: b['start_at']):
            by_pr.setdefault(batch['pr'], []).append(batch)
        for rows in by_pr.values():
            self.assertEqual([r['e2e_index'] for r in rows], list(range(1, len(rows) + 1)))
            self.assertTrue(all(r['e2e_total'] == len(rows) for r in rows))


class ScenarioFixtureTests(unittest.TestCase):
    def test_ac03_zero_data_fixture_is_legal_and_recomputes(self):
        # REQ-037 AC03 (合法零数据): empty batches are legal zero data.
        payload = load('triton-zero.json')
        self.assertEqual(payload['batches'], [])
        recomputed = recompute_summary(payload['batches'])
        for key, value in recomputed.items():
            self.assertTrue(same(value, payload['summary'][key]), key)
        self.assertEqual(payload['summary']['valid'], 0)
        self.assertIsNone(payload['summary']['median'])
        self.assertIsNone(payload['summary']['p90'])

    def test_ac03_single_sample_fixture_percentiles_equal_the_value(self):
        # REQ-037 AC03 (单样本): one sample expresses itself.
        payload = load('triton-single.json')
        recomputed = recompute_summary(payload['batches'])
        for key, value in recomputed.items():
            self.assertTrue(same(value, payload['summary'][key]), key)
        self.assertEqual(payload['summary']['valid'], 1)
        self.assertTrue(same(payload['summary']['median'], 720))
        self.assertTrue(same(payload['summary']['p90'], 720))
        self.assertTrue(same(payload['batches'][0]['duration_seconds'], 720))


class MinimalUbsContractTests(unittest.TestCase):
    def test_ac02_ubs_metrics_recompute_representative_batch(self):
        # REQ-037 AC02: the UBS minimal snapshots keep the representative-batch
        # contract — longest measurable terminal batch (tie: larger number),
        # task values from that batch only, missing tasks stay null.
        for name in ('snapshot.json', 'repos/ubs-engine.json'):
            payload = json.loads((MINIMAL / name).read_text(encoding='utf-8'))
            for pr in payload['prs']:
                candidates = [b for b in pr['batches']
                              if b.get('eligible') and b.get('e2e_ms') is not None
                              and b.get('status') in ('success', 'failure')]
                rep = max(candidates, key=lambda b: (b['e2e_ms'], b['number']))
                self.assertEqual(pr['metrics']['representative_batch_number'], rep['number'], name)
                self.assertEqual(pr['metrics']['e2e_ms'], rep['e2e_ms'], name)
                for kind in ('x86', 'arm', 'dt'):
                    tasks = [c for c in rep['children']
                             if c.get('kind') == kind and c.get('association_valid') and not c.get('building')]
                    if len(tasks) == 1:
                        for field in ('queue_ms', 'duration_ms', 'total_ms'):
                            self.assertEqual(pr['metrics'][kind][field], tasks[0][field],
                                             f'{name} #{pr["number"]} {kind}')
                        self.assertEqual(pr['metrics'][kind]['url'], tasks[0]['url'])
                    else:
                        for field in ('queue_ms', 'duration_ms', 'total_ms'):
                            self.assertIsNone(pr['metrics'][kind][field], f'{name} #{pr["number"]} {kind}')


if __name__ == '__main__':
    unittest.main()
