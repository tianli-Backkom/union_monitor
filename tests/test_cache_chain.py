"""REQ-013: cold/warm cache and daily→incremental chain acceptance.

These tests replay the production sequence against the real artifacts: the
'Ensure UBS data' step is extracted verbatim from triton-refresh.yml and
executed by bash, and every bundle gate runs validate_bundle.py itself.

  warm cache A → daily update B → incremental publish ends at B (AC01)
  cold cache → fallback-site restore → complete bundle only (AC02)
  cache hit carrying an invalid artifact → publish blocked (AC03)

Every step logs its restore source (cache hit / fallback / mirror) and the
bundle fingerprint, so a verbose run doubles as the AC04 chain evidence.
"""
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_bundle_verifier import (SHARED_CACHE_PATHS, fingerprint_of, run_verifier,
                                  write_bundle)

ROOT = Path(__file__).resolve().parents[1]

A_GENERATED_AT = '2026-10-08T03:01:57+00:00'
B_GENERATED_AT = '2026-10-09T03:01:57+00:00'


def ensure_script():
    """Extract the production 'Ensure UBS data' script from the workflow."""
    text = (ROOT / '.github' / 'workflows' / 'triton-refresh.yml').read_text(encoding='utf-8')
    block = text[text.index('- name: Ensure UBS data'):]
    body = block[block.index('run: |') + len('run: |'):]
    end = len(body)
    for marker in ('\n      - name: ', '\n  deploy:'):
        pos = body.find(marker)
        if pos != -1:
            end = min(end, pos)
    lines = []
    for line in body[:end].splitlines():
        if not line.strip():
            lines.append('')
        elif line.startswith(' ' * 10):
            lines.append(line[10:])
        else:
            raise AssertionError(f'unexpected indentation in the ensure script: {line!r}')
    return '\n'.join(lines) + '\n'


def run_ensure(workspace, fallback_url, shim_dir):
    """Run the extracted script with `python` resolved through a python3 shim."""
    env = dict(os.environ, SITE_FALLBACK_URL=str(fallback_url),
               PATH=f'{shim_dir}{os.pathsep}{os.environ["PATH"]}')
    proc = subprocess.run(['bash', '-c', ensure_script()], cwd=str(workspace), env=env,
                          capture_output=True, text=True, encoding='utf-8')
    return proc.returncode, proc.stdout + proc.stderr


def copy_shared(source, target):
    """Move exactly the workflow's shared-cache path set between trees."""
    for rel in SHARED_CACHE_PATHS:
        src, dst = source / rel, target / rel
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        elif src.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)


def publish_site(bundle, site):
    """Lay out a bundle's web/data as the fallback site (<site>/data/...)."""
    (site / 'data').mkdir(parents=True, exist_ok=True)
    shutil.copytree(bundle / 'web' / 'data', site / 'data', dirs_exist_ok=True)


class CacheChainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='ubs-chain-'))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.shim = self.tmp / 'shim'
        self.shim.mkdir()
        (self.shim / 'python').write_text('#!/bin/sh\nexec python3 "$@"\n')
        (self.shim / 'python').chmod(0o755)

    def site_url(self, site):
        return site.resolve().as_uri()

    def test_warm_cache_daily_update_publishes_b_not_a(self):
        # REQ-013 AC01: warm cache A → daily update B → incremental publishes B.
        bundle_a, bundle_b = self.tmp / 'A', self.tmp / 'B'
        write_bundle(bundle_a, generated_at=A_GENERATED_AT)
        write_bundle(bundle_b, generated_at=B_GENERATED_AT, pr_count=2)
        _, out = run_verifier(bundle_a, '--write-manifest')
        fp_a = fingerprint_of(out)
        _, out = run_verifier(bundle_b, '--write-manifest')
        fp_b = fingerprint_of(out)
        self.assertNotEqual(fp_a, fp_b)

        cache = self.tmp / 'cache'
        copy_shared(bundle_a, cache)          # yesterday's daily saved A
        copy_shared(bundle_b, cache)          # today's daily saved B over it
        site = self.tmp / 'site'
        publish_site(bundle_a, site)          # the live site still serves A

        workspace = self.tmp / 'incremental'
        copy_shared(cache, workspace)         # the incremental restores the cache
        code, log = run_ensure(workspace, self.site_url(site), self.shim)
        self.assertEqual(code, 0, log)
        self.assertIn('summary: cache=4 fallback=0 mirrored=0 missing=0', log)
        code, out = run_verifier(workspace, '--ensure-manifest')
        self.assertEqual(code, 0, out)
        self.assertIn('manifest=verified', out)
        self.assertEqual(fingerprint_of(out), fp_b)
        print(f'[chain] AC01 warm-cache: A={fp_a} B={fp_b} published={fingerprint_of(out)}')
        self.assertEqual((workspace / 'web/data/repositories.json').read_bytes(),
                         (bundle_b / 'web/data/repositories.json').read_bytes())
        self.assertNotEqual((workspace / 'web/data/repositories.json').read_bytes(),
                            (bundle_a / 'web/data/repositories.json').read_bytes())
        for name in ('ubs-engine', 'ubs-comm'):
            self.assertEqual((workspace / f'web/data/repos/{name}.json').read_bytes(),
                             (bundle_b / f'web/data/repos/{name}.json').read_bytes())

    def test_cold_start_restores_complete_bundle_from_fallback_site(self):
        # REQ-013 AC02: cold cache → the fallback restore must pass the bundle
        # gate before anything publishes.
        bundle = self.tmp / 'B'
        write_bundle(bundle, generated_at=B_GENERATED_AT, pr_count=2)
        _, out = run_verifier(bundle, '--write-manifest')
        fp = fingerprint_of(out)
        site = self.tmp / 'site'
        publish_site(bundle, site)
        workspace = self.tmp / 'incremental'
        workspace.mkdir()                     # cold: nothing restored from cache
        code, log = run_ensure(workspace, self.site_url(site), self.shim)
        self.assertEqual(code, 0, log)
        self.assertIn('summary: cache=0 fallback=4 mirrored=4 missing=0', log)
        code, out = run_verifier(workspace, '--ensure-manifest')
        self.assertEqual(code, 0, out)
        self.assertIn('manifest=verified', out)
        self.assertEqual(fingerprint_of(out), fp)
        print(f'[chain] AC02 cold-start: site={fp} published={fingerprint_of(out)}')

    def test_cold_start_missing_snapshot_blocks_deploy_beyond_non_empty_index(self):
        # REQ-013 AC02: a non-empty index alone must not count as success when
        # a referenced snapshot is unavailable.
        bundle = self.tmp / 'B'
        write_bundle(bundle, generated_at=B_GENERATED_AT)
        run_verifier(bundle, '--write-manifest')
        site = self.tmp / 'site'
        publish_site(bundle, site)
        (site / 'data/repos/ubs-comm.json').unlink()
        workspace = self.tmp / 'incremental'
        workspace.mkdir()
        code, log = run_ensure(workspace, self.site_url(site), self.shim)
        self.assertEqual(code, 0, log)        # ensure logs the gap; only the index is fatal there
        self.assertIn('missing=1', log)
        self.assertIn('NOT complete', log)
        # REQ-020 AC03: the error report names the specific missing reference
        # and its restore source (fallback site URL + remote path).
        self.assertIn('download failed', log)
        self.assertIn('/data/repos/ubs-comm.json', log)
        code, out = run_verifier(workspace, '--ensure-manifest')
        self.assertNotEqual(code, 0)          # ...but the bundle gate blocks the deploy
        self.assertIn('ubs-comm', out)
        print('[chain] AC02 negative: missing snapshot → deploy blocked despite non-empty index')

    def test_missing_index_after_fallback_refuses_to_deploy(self):
        # REQ-013 AC02: with no index from cache or fallback the run fails loud.
        bundle = self.tmp / 'B'
        write_bundle(bundle)
        workspace = self.tmp / 'incremental'
        copy_shared(bundle, workspace)
        (workspace / 'web/data/repositories.json').unlink()
        (workspace / 'data/repositories.json').unlink()
        code, log = run_ensure(workspace, self.site_url(self.tmp / 'void'), self.shim)
        self.assertEqual(code, 1, log)
        self.assertIn('refusing to deploy', log)
        print('[chain] AC02 guard: index missing everywhere → exit 1')

    def test_cache_hit_with_invalid_artifact_blocks_publish(self):
        # REQ-013 AC03: a cache hit carrying a mixed-version artifact (B index +
        # stale A-vintage snapshot pair) must not publish — the fingerprint gate
        # blocks it even though every file parses and the mirrors agree.
        bundle_a, bundle_b = self.tmp / 'A', self.tmp / 'B'
        write_bundle(bundle_a, generated_at=A_GENERATED_AT)
        write_bundle(bundle_b, generated_at=B_GENERATED_AT, pr_count=2)
        run_verifier(bundle_a, '--write-manifest')
        _, out = run_verifier(bundle_b, '--write-manifest')
        fp_b = fingerprint_of(out)
        cache = self.tmp / 'cache'
        copy_shared(bundle_b, cache)
        for rel in ('web/data/repos/ubs-comm.json', 'data/repos/ubs-comm.json'):
            shutil.copy2(bundle_a / rel, cache / rel)  # coherent old-vintage pair
        workspace = self.tmp / 'incremental'
        copy_shared(cache, workspace)
        code, log = run_ensure(workspace, self.site_url(self.tmp / 'void'), self.shim)
        self.assertEqual(code, 0, log)        # ensure sees complete files...
        self.assertIn('summary: cache=4 fallback=0 mirrored=0 missing=0', log)
        code, out = run_verifier(workspace, '--ensure-manifest')
        self.assertNotEqual(code, 0)          # ...but the manifest gate blocks the deploy
        self.assertIn('manifest mismatch', out)
        self.assertIn('repos/ubs-comm.json', out)
        print(f'[chain] AC03 invalid-cache: expected {fp_b} → blocked (mixed ubs-comm vintage)')

    def test_cold_start_empty_snapshot_file_blocks_deploy(self):
        # REQ-020 AC01: a fallback site serving a 0-byte snapshot "restores"
        # fine (HTTP 200, empty body) — the ensure step even reports the
        # bundle complete; only the bundle gate catches the empty file.
        bundle = self.tmp / 'B'
        write_bundle(bundle, generated_at=B_GENERATED_AT, pr_count=2)
        run_verifier(bundle, '--write-manifest')
        site = self.tmp / 'site'
        publish_site(bundle, site)
        (site / 'data/repos/ubs-comm.json').write_bytes(b'')
        workspace = self.tmp / 'incremental'
        workspace.mkdir()
        code, log = run_ensure(workspace, self.site_url(site), self.shim)
        self.assertEqual(code, 0, log)
        self.assertIn('summary: cache=0 fallback=4 mirrored=3 missing=0', log)
        code, out = run_verifier(workspace, '--ensure-manifest')
        self.assertNotEqual(code, 0)
        self.assertIn('ubs-comm', out)
        self.assertIn('not valid JSON', out)
        print('[chain] REQ-020 AC01: empty restored snapshot → deploy blocked')

    def test_pending_and_first_failed_entries_restore_without_fake_success(self):
        # REQ-020 AC02: pending / first-failed repositories have no snapshot
        # on the site; the restore logs the download failures and the bundle
        # gate still passes — they stay uncollected, never fabricated success.
        bundle = self.tmp / 'B'
        write_bundle(bundle, generated_at=B_GENERATED_AT, pr_count=2)
        index_path = bundle / 'web/data/repositories.json'
        index = json.loads(index_path.read_text('utf-8'))
        index['repositories'] += [
            {'name': 'ubs-virt', 'repository': 'openeuler/ubs-virt',
             'status': 'pending', 'snapshot': None, 'meta': None},
            {'name': 'ubs-io', 'repository': 'openeuler/ubs-io',
             'status': 'failed', 'snapshot': None, 'meta': None,
             'error': 'collect failed'},
        ]
        updated = json.dumps(index, ensure_ascii=False)
        index_path.write_text(updated, 'utf-8')
        (bundle / 'data/repositories.json').write_text(updated, 'utf-8')
        code, out = run_verifier(bundle, '--write-manifest')
        self.assertEqual(code, 0, out)
        site = self.tmp / 'site'
        publish_site(bundle, site)
        workspace = self.tmp / 'incremental'
        workspace.mkdir()
        code, log = run_ensure(workspace, self.site_url(site), self.shim)
        self.assertEqual(code, 0, log)
        self.assertIn('web/data/repos/ubs-virt.json is missing; downloading', log)
        self.assertIn('download failed', log)
        self.assertIn('summary: cache=0 fallback=4 mirrored=4 missing=2', log)
        self.assertIn('NOT complete', log)
        code, out = run_verifier(workspace, '--ensure-manifest')
        self.assertEqual(code, 0, out)
        self.assertIn('manifest=verified', out)
        self.assertFalse((workspace / 'web/data/repos/ubs-virt.json').exists())
        self.assertFalse((workspace / 'web/data/repos/ubs-io.json').exists())
        print('[chain] REQ-020 AC02: pending/first-failed restore without fabricated snapshots')

    def test_warm_incomplete_cache_with_unavailable_file_blocks_deploy(self):
        # REQ-020 AC03: the cache path runs the same integrity check as the
        # fallback path — a cache hit missing one referenced snapshot, with
        # the site also lacking it, blocks the deploy identically.
        bundle = self.tmp / 'B'
        write_bundle(bundle, generated_at=B_GENERATED_AT, pr_count=2)
        run_verifier(bundle, '--write-manifest')
        cache = self.tmp / 'cache'
        copy_shared(bundle, cache)
        for rel in ('web/data/repos/ubs-comm.json', 'data/repos/ubs-comm.json'):
            (cache / rel).unlink()
        site = self.tmp / 'site'
        publish_site(bundle, site)
        (site / 'data/repos/ubs-comm.json').unlink()
        workspace = self.tmp / 'incremental'
        copy_shared(cache, workspace)
        code, log = run_ensure(workspace, self.site_url(site), self.shim)
        self.assertEqual(code, 0, log)
        self.assertIn('summary: cache=3 fallback=0 mirrored=0 missing=1', log)
        self.assertIn('download failed', log)
        self.assertIn('NOT complete', log)
        code, out = run_verifier(workspace, '--ensure-manifest')
        self.assertNotEqual(code, 0)
        self.assertIn('ubs-comm', out)
        self.assertIn('missing', out)
        print('[chain] REQ-020 AC03: warm incomplete cache → same bundle gate blocks')


if __name__ == '__main__':
    unittest.main()
