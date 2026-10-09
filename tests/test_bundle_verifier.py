import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'validate_bundle.py'

SHARED_CACHE_PATHS = (
    'web/data/repositories.json', 'web/data/repos', 'web/data/snapshot.json',
    'web/data/ubs-manifest.json', 'data/repositories.json', 'data/repos', 'data/snapshot.json',
)


def write_bundle(root, repos=('ubs-engine', 'ubs-comm'), *, compat=True, mirrors=True,
                 generated_at='2026-10-08T03:01:57+00:00', pr_count=1):
    web = root / 'web' / 'data'
    (web / 'repos').mkdir(parents=True, exist_ok=True)
    entries = []
    for name in repos:
        repository = 'openeuler/' + name
        snapshot = {
            'meta': {'repository': repository, 'collected_at': '2026-10-08T02:54:55+00:00',
                     'start_ms': 1, 'end_ms': 2, 'expected_prs': pr_count},
            'prs': [{'number': number, 'state': 'merged', 'batches': []}
                    for number in range(1, pr_count + 1)],
        }
        (web / 'repos' / (name + '.json')).write_text(json.dumps(snapshot, ensure_ascii=False), 'utf-8')
        entries.append({'name': name, 'repository': repository, 'status': 'success',
                        'snapshot': 'repos/' + name + '.json'})
    index = {'schema_version': 3, 'start_ms': 1, 'end_ms': 2,
             'generated_at': generated_at, 'repositories': entries}
    (web / 'repositories.json').write_text(json.dumps(index, ensure_ascii=False), 'utf-8')
    if compat:
        (web / 'snapshot.json').write_bytes((web / 'repos' / 'ubs-engine.json').read_bytes())
    if mirrors:
        data = root / 'data'
        (data / 'repos').mkdir(parents=True, exist_ok=True)
        (data / 'repositories.json').write_bytes((web / 'repositories.json').read_bytes())
        for name in repos:
            (data / 'repos' / (name + '.json')).write_bytes((web / 'repos' / (name + '.json')).read_bytes())
        (data / 'snapshot.json').write_bytes((web / 'snapshot.json').read_bytes())


def run_verifier(root, *flags):
    proc = subprocess.run([sys.executable, '-X', 'utf8', str(SCRIPT), '--root', str(root), *flags],
                          capture_output=True, text=True, encoding='utf-8')
    return proc.returncode, proc.stdout + proc.stderr


def fingerprint_of(output):
    match = re.search(r'fingerprint=sha256:[0-9a-f]{64}', output)
    return match.group(0) if match else None


class BundleVerifierTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='ubs-bundle-'))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_consistent_bundle_passes_with_fingerprint(self):
        write_bundle(self.tmp)
        code, out = run_verifier(self.tmp)
        self.assertEqual(code, 0, out)
        self.assertIn('[ubs-bundle] ok', out)
        self.assertTrue(fingerprint_of(out), out)

    def test_write_manifest_then_plain_run_verifies(self):
        write_bundle(self.tmp)
        code, out = run_verifier(self.tmp, '--write-manifest')
        self.assertEqual(code, 0, out)
        self.assertTrue((self.tmp / 'web/data/ubs-manifest.json').exists())
        code, out = run_verifier(self.tmp)
        self.assertEqual(code, 0, out)
        self.assertIn('manifest=verified', out)

    def test_cache_roundtrip_preserves_fingerprint(self):
        # REQ-012 AC02: the daily run produces bundle B and stamps its manifest...
        daily = self.tmp / 'daily'
        write_bundle(daily)
        code, out = run_verifier(daily, '--write-manifest')
        self.assertEqual(code, 0, out)
        daily_fp = fingerprint_of(out)
        # ...the shared Actions cache stores exactly the shared path set...
        cache = self.tmp / 'cache'
        for rel in SHARED_CACHE_PATHS:
            source, target = daily / rel, cache / rel
            if source.is_dir():
                shutil.copytree(source, target)
            elif source.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        # ...and the incremental workflow restores it into a fresh tree.
        incremental = self.tmp / 'incremental'
        for rel in SHARED_CACHE_PATHS:
            source, target = cache / rel, incremental / rel
            if source.is_dir():
                shutil.copytree(source, target)
            elif source.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
        code, out = run_verifier(incremental)
        self.assertEqual(code, 0, out)
        self.assertEqual(fingerprint_of(out), daily_fp)
        self.assertIn('manifest=verified', out)

    def test_missing_referenced_snapshot_fails(self):
        write_bundle(self.tmp)
        (self.tmp / 'web/data/repos/ubs-comm.json').unlink()
        code, out = run_verifier(self.tmp)
        self.assertNotEqual(code, 0)
        self.assertIn('ubs-comm', out)
        self.assertIn('missing', out)

    def test_cross_repo_identity_mismatch_fails(self):
        write_bundle(self.tmp)
        path = self.tmp / 'web/data/repos/ubs-comm.json'
        snapshot = json.loads(path.read_text('utf-8'))
        snapshot['meta']['repository'] = 'openeuler/ubs-virt'
        path.write_text(json.dumps(snapshot, ensure_ascii=False), 'utf-8')
        code, out = run_verifier(self.tmp)
        self.assertNotEqual(code, 0)
        self.assertIn('ubs-comm', out)

    def test_mirror_mismatch_fails_but_missing_mirror_only_warns(self):
        write_bundle(self.tmp)
        (self.tmp / 'data/repositories.json').write_text('{"tampered": true}', 'utf-8')
        code, out = run_verifier(self.tmp)
        self.assertNotEqual(code, 0)
        self.assertIn('mirror', out)
        (self.tmp / 'data/repositories.json').unlink()
        code, out = run_verifier(self.tmp)
        self.assertEqual(code, 0, out)
        self.assertIn('warn', out)

    def test_stale_manifest_blocks_mixed_bundle(self):
        # REQ-012 AC03: a newer snapshot must not ship behind an old index/manifest.
        write_bundle(self.tmp)
        self.assertEqual(run_verifier(self.tmp, '--write-manifest')[0], 0)
        path = self.tmp / 'web/data/repos/ubs-comm.json'
        snapshot = json.loads(path.read_text('utf-8'))
        snapshot['prs'].append({'number': 2, 'state': 'open', 'batches': []})
        path.write_text(json.dumps(snapshot, ensure_ascii=False), 'utf-8')
        code, out = run_verifier(self.tmp)
        self.assertNotEqual(code, 0)
        self.assertIn('manifest fingerprint mismatch', out)
        # --ensure-manifest must not silently bless the mixed bundle.
        code, out = run_verifier(self.tmp, '--ensure-manifest')
        self.assertNotEqual(code, 0)

    def test_invalid_index_fails(self):
        write_bundle(self.tmp)
        (self.tmp / 'web/data/repositories.json').write_text('{bad json', 'utf-8')
        self.assertNotEqual(run_verifier(self.tmp)[0], 0)
        (self.tmp / 'web/data/repositories.json').write_text('{"repositories": []}', 'utf-8')
        self.assertNotEqual(run_verifier(self.tmp)[0], 0)

    def test_fingerprint_tracks_content(self):
        write_bundle(self.tmp)
        _, first = run_verifier(self.tmp)
        # Drop the mirrors so the tampered web copy cannot also trip a mirror
        # error — this test isolates the fingerprint itself.
        shutil.rmtree(self.tmp / 'data')
        path = self.tmp / 'web/data/repos/ubs-comm.json'
        snapshot = json.loads(path.read_text('utf-8'))
        snapshot['prs'][0]['state'] = 'closed'
        path.write_text(json.dumps(snapshot, ensure_ascii=False), 'utf-8')
        code, second = run_verifier(self.tmp)
        self.assertEqual(code, 0, second)
        self.assertIsNotNone(fingerprint_of(second), second)
        self.assertNotEqual(fingerprint_of(first), fingerprint_of(second))

    def test_stale_compat_snapshot_fails(self):
        write_bundle(self.tmp)
        (self.tmp / 'data/snapshot.json').write_text('{"stale": true}', 'utf-8')
        code, out = run_verifier(self.tmp)
        self.assertNotEqual(code, 0)
        self.assertIn('compat', out)

    def test_ensure_manifest_creates_when_absent_and_preserves_when_present(self):
        write_bundle(self.tmp)
        code, out = run_verifier(self.tmp, '--ensure-manifest')
        self.assertEqual(code, 0, out)
        manifest = self.tmp / 'web/data/ubs-manifest.json'
        self.assertTrue(manifest.exists())
        original = json.loads(manifest.read_text('utf-8'))
        original['note'] = 'restored provenance must survive'
        manifest.write_text(json.dumps(original, ensure_ascii=False, indent=2), 'utf-8')
        code, out = run_verifier(self.tmp, '--ensure-manifest')
        self.assertEqual(code, 0, out)
        self.assertIn('note', json.loads(manifest.read_text('utf-8')))  # untouched, not rewritten
        code, out = run_verifier(self.tmp, '--write-manifest')
        self.assertEqual(code, 0, out)
        self.assertNotIn('note', json.loads(manifest.read_text('utf-8')))  # daily stamps fresh

    def test_pending_entry_without_snapshot_is_legal(self):
        write_bundle(self.tmp)
        index_path = self.tmp / 'web/data/repositories.json'
        index = json.loads(index_path.read_text('utf-8'))
        index['repositories'].append({'name': 'ubs-new', 'repository': 'openeuler/ubs-new',
                                      'status': 'pending', 'snapshot': None, 'meta': None})
        updated = json.dumps(index, ensure_ascii=False)
        index_path.write_text(updated, 'utf-8')
        # publish_index writes both copies at once; keep the mirror consistent.
        (self.tmp / 'data/repositories.json').write_text(updated, 'utf-8')
        code, out = run_verifier(self.tmp)
        self.assertEqual(code, 0, out)

    def test_empty_index_and_empty_snapshot_files_fail(self):
        # REQ-020 AC01: an empty file is a restore failure, not "index
        # non-empty" — 0-byte index and 0-byte referenced snapshot both fail.
        empty_index = self.tmp / 'empty-index'
        write_bundle(empty_index)
        (empty_index / 'web/data/repositories.json').write_bytes(b'')
        code, out = run_verifier(empty_index)
        self.assertNotEqual(code, 0)
        self.assertIn('not valid JSON', out)
        empty_snapshot = self.tmp / 'empty-snapshot'
        write_bundle(empty_snapshot)
        (empty_snapshot / 'web/data/repos/ubs-comm.json').write_bytes(b'')
        code, out = run_verifier(empty_snapshot)
        self.assertNotEqual(code, 0)
        self.assertIn('ubs-comm', out)
        self.assertIn('not valid JSON', out)

    def test_index_without_repositories_object_structure_fails(self):
        # REQ-020 AC01: valid JSON that is not an object with a repositories
        # list is a structural failure, never a restore success.
        write_bundle(self.tmp)
        index_path = self.tmp / 'web/data/repositories.json'
        index_path.write_text('[]', 'utf-8')
        self.assertNotEqual(run_verifier(self.tmp)[0], 0)
        index_path.write_text('{"schema_version": 3}', 'utf-8')
        code, out = run_verifier(self.tmp)
        self.assertNotEqual(code, 0)
        self.assertIn('non-empty repositories list', out)

    def test_failed_entry_without_snapshot_is_legal_like_pending(self):
        # REQ-020 AC02: a first-failed repository has no snapshot file; the
        # gate treats it like pending — 未获取, never fabricated success data.
        write_bundle(self.tmp)
        index_path = self.tmp / 'web/data/repositories.json'
        index = json.loads(index_path.read_text('utf-8'))
        index['repositories'].append({'name': 'ubs-new', 'repository': 'openeuler/ubs-new',
                                      'status': 'failed', 'snapshot': None, 'meta': None,
                                      'error': 'collect failed'})
        updated = json.dumps(index, ensure_ascii=False)
        index_path.write_text(updated, 'utf-8')
        # publish_index writes both copies at once; keep the mirror consistent.
        (self.tmp / 'data/repositories.json').write_text(updated, 'utf-8')
        code, out = run_verifier(self.tmp)
        self.assertEqual(code, 0, out)

    def test_current_scope_snapshot_must_match_index_range(self):
        # REQ-021 AC01/AC03: a snapshot shipping a different window would
        # masquerade stale data as current scope — the gate fails and says why.
        write_bundle(self.tmp)
        path = self.tmp / 'web/data/repos/ubs-comm.json'
        snapshot = json.loads(path.read_text('utf-8'))
        snapshot['meta']['start_ms'] = 999
        tampered = json.dumps(snapshot, ensure_ascii=False)
        path.write_text(tampered, 'utf-8')
        (self.tmp / 'data/repos/ubs-comm.json').write_text(tampered, 'utf-8')
        code, out = run_verifier(self.tmp)
        self.assertNotEqual(code, 0)
        self.assertIn('index window', out)
        self.assertIn('ubs-comm', out)
        # partial is current scope too: relabeling the entry must not bypass the gate
        index_path = self.tmp / 'web/data/repositories.json'
        index = json.loads(index_path.read_text('utf-8'))
        index['repositories'][1]['status'] = 'partial'
        updated = json.dumps(index, ensure_ascii=False)
        index_path.write_text(updated, 'utf-8')
        (self.tmp / 'data/repositories.json').write_text(updated, 'utf-8')
        code, out = run_verifier(self.tmp)
        self.assertNotEqual(code, 0)
        self.assertIn('index window', out)

    def test_failed_retained_snapshot_with_old_range_is_legal(self):
        # REQ-021 AC02: a failed repo may keep its last snapshot with an old
        # window, but relabeling the very same bundle as success must fail.
        write_bundle(self.tmp)
        path = self.tmp / 'web/data/repos/ubs-comm.json'
        snapshot = json.loads(path.read_text('utf-8'))
        snapshot['meta']['start_ms'] = 999
        snapshot['meta']['end_ms'] = 1998
        tampered = json.dumps(snapshot, ensure_ascii=False)
        path.write_text(tampered, 'utf-8')
        (self.tmp / 'data/repos/ubs-comm.json').write_text(tampered, 'utf-8')
        index_path = self.tmp / 'web/data/repositories.json'
        index = json.loads(index_path.read_text('utf-8'))
        index['repositories'][1]['status'] = 'failed'
        updated = json.dumps(index, ensure_ascii=False)
        index_path.write_text(updated, 'utf-8')
        (self.tmp / 'data/repositories.json').write_text(updated, 'utf-8')
        code, out = run_verifier(self.tmp)
        self.assertEqual(code, 0, out)
        index['repositories'][1]['status'] = 'success'
        restored = json.dumps(index, ensure_ascii=False)
        index_path.write_text(restored, 'utf-8')
        (self.tmp / 'data/repositories.json').write_text(restored, 'utf-8')
        code, out = run_verifier(self.tmp)
        self.assertNotEqual(code, 0)
        self.assertIn('index window', out)

    def test_current_scope_entry_without_snapshot_fails(self):
        # REQ-021 AC01: success without a snapshot file cannot prove range
        # consistency — it must not slip into cross-repo aggregation.
        write_bundle(self.tmp)
        index_path = self.tmp / 'web/data/repositories.json'
        index = json.loads(index_path.read_text('utf-8'))
        index['repositories'][1]['snapshot'] = None
        updated = json.dumps(index, ensure_ascii=False)
        index_path.write_text(updated, 'utf-8')
        (self.tmp / 'data/repositories.json').write_text(updated, 'utf-8')
        code, out = run_verifier(self.tmp)
        self.assertNotEqual(code, 0)
        self.assertIn('ubs-comm', out)
        self.assertIn('no snapshot', out)


if __name__ == '__main__':
    unittest.main()
