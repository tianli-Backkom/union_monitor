import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGES = (ROOT / '.github' / 'workflows' / 'pages.yml').read_text(encoding='utf-8')
REFRESH = (ROOT / '.github' / 'workflows' / 'triton-refresh.yml').read_text(encoding='utf-8')

SHARED_PATHS = [
    'web/data/repositories.json',
    'web/data/repos',
    'web/data/snapshot.json',
    'web/data/ubs-manifest.json',
    'data/repositories.json',
    'data/repos',
    'data/snapshot.json',
]
COLLECTION_PATHS = ['data/raw', 'data/efficiency.sqlite', 'evidence/triton']
SHARED_KEY = 'ubs-snapshots-v1-${{ runner.os }}-${{ github.run_id }}'
SHARED_RESTORE_KEYS = 'ubs-snapshots-v1-${{ runner.os }}-'
COLLECTION_KEY = 'ubs-collection-v1-${{ runner.os }}-${{ github.run_id }}'
COLLECTION_RESTORE_KEYS = 'ubs-collection-v1-${{ runner.os }}-'


def cache_steps(text):
    """Parse every workflow step into uses/key/restore-keys/paths."""
    steps = []
    for chunk in re.split(r'(?m)^      - name: ', text)[1:]:
        uses = re.search(r'(?m)^        uses: (.+?)\s*$', chunk)
        key = re.search(r'(?m)^          key: (.+?)\s*$', chunk)
        restore = re.search(r'(?m)^          restore-keys: \|\n            (.+?)\s*$', chunk)
        paths = re.search(r'(?m)^          path: \|\n((?:            .+\n)+)', chunk)
        steps.append({
            'uses': uses.group(1) if uses else None,
            'key': key.group(1) if key else None,
            'restore_keys': restore.group(1) if restore else None,
            'paths': [line.strip() for line in paths.group(1).splitlines()] if paths else [],
        })
    return steps


class SharedSnapshotCacheConfigTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pages_steps = cache_steps(PAGES)
        cls.refresh_steps = cache_steps(REFRESH)

    def test_daily_restores_and_saves_both_cache_families(self):
        restores = [s for s in self.pages_steps if s['uses'] == 'actions/cache/restore@v4']
        saves = [s for s in self.pages_steps if s['uses'] == 'actions/cache/save@v4']
        self.assertEqual(len(restores), 2)
        self.assertEqual(len(saves), 2)
        shared = [s for s in restores + saves if s['key'] == SHARED_KEY]
        collection = [s for s in restores + saves if s['key'] == COLLECTION_KEY]
        self.assertEqual(len(shared), 2)
        self.assertEqual(len(collection), 2)
        for step in shared:
            self.assertEqual(step['paths'], SHARED_PATHS)
        for step in collection:
            self.assertEqual(step['paths'], COLLECTION_PATHS)
        self.assertEqual({s['restore_keys'] for s in restores},
                         {SHARED_RESTORE_KEYS, COLLECTION_RESTORE_KEYS})

    def test_incremental_shares_the_exact_snapshot_cache_identity(self):
        restores = [s for s in self.refresh_steps if s['uses'] == 'actions/cache/restore@v4']
        saves = [s for s in self.refresh_steps if s['uses'] == 'actions/cache/save@v4']
        self.assertEqual(len(restores), 1)
        self.assertEqual(len(saves), 1)
        for step in restores + saves:
            self.assertEqual(step['key'], SHARED_KEY)
            self.assertEqual(step['paths'], SHARED_PATHS)
        self.assertEqual(restores[0]['restore_keys'], SHARED_RESTORE_KEYS)

    def test_collection_cache_stays_daily_only_and_disjoint(self):
        # REQ-012: raw responses, SQLite and Triton evidence never mix into the
        # shared snapshot version, and the incremental flow never touches them.
        self.assertNotIn('ubs-collection-', REFRESH)
        self.assertFalse(set(COLLECTION_PATHS) & set(SHARED_PATHS))
        self.assertNotIn('evidence/triton', SHARED_PATHS)
        for step in self.refresh_steps:
            self.assertNotEqual(step['key'], COLLECTION_KEY)

    def test_no_wholesale_web_data_and_no_legacy_prefix(self):
        # Caching all of web/data would pull Triton outputs into the shared UBS
        # artifact; the legacy unversioned prefix must be gone from both flows.
        for step in self.pages_steps + self.refresh_steps:
            self.assertNotIn('web/data', step['paths'])
        self.assertNotIn('pages-data-', PAGES)
        self.assertNotIn('pages-data-', REFRESH)

    def test_bundle_verification_precedes_every_upload(self):
        self.assertIn('python -X utf8 validate_bundle.py --write-manifest', PAGES)
        self.assertIn('python -X utf8 validate_bundle.py --ensure-manifest', REFRESH)
        for text, flag in ((PAGES, '--write-manifest'), (REFRESH, '--ensure-manifest')):
            self.assertLess(text.index('validate_bundle.py ' + flag),
                            text.index('uses: actions/upload-pages-artifact@v3'))
        # The daily audit still runs before the bundle check.
        self.assertLess(PAGES.index('python -X utf8 validate.py'),
                        PAGES.index('validate_bundle.py --write-manifest'))

    def test_cache_uses_the_same_action_versions_in_both_flows(self):
        for text in (PAGES, REFRESH):
            self.assertIn('uses: actions/cache/restore@v4', text)
            self.assertIn('uses: actions/cache/save@v4', text)
            self.assertNotIn('uses: actions/cache@v4', text)


if __name__ == '__main__':
    unittest.main()
