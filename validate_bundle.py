"""Verify the UBS snapshot bundle shared by the daily and incremental workflows.

The bundle is the exact file set both workflows exchange through the versioned
Actions cache key family ``ubs-snapshots-v1-*`` and publish to Pages:

    web/data/repositories.json   index — entry point for every UBS view
    web/data/repos/<name>.json   per-repository snapshots referenced by the index
    web/data/snapshot.json       ubs-engine compat snapshot (published copy)
    web/data/ubs-manifest.json   fingerprint binding index+snapshots to one artifact

Failures (exit 1, must block the deploy and the cache save):
  * the index is unreadable, invalid or has an empty repositories list
  * an entry referencing a snapshot points outside web/data, to a missing file,
    to invalid JSON, or to a snapshot whose meta.repository disagrees with the
    index entry (cross-repo borrowing / mixed versions)
  * a repo-root mirror (data/...) disagrees with its web/data counterpart
  * data/snapshot.json disagrees with the current ubs-engine snapshot
  * a present ubs-manifest.json does not match the fingerprint of the files on
    disk, so an old index can never ship with new snapshots (or the reverse)

Warnings (exit 0): missing compat snapshot, missing mirrors or a missing
manifest — local dev trees may carry a subset; CI restores or fetches them.

Modes:
  (default)          verify only
  --write-manifest   verify, then stamp a fresh manifest (daily workflow)
  --ensure-manifest  verify, then create the manifest only when it is absent
                     (incremental workflow keeps the restored provenance)
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_NAME = 'ubs-manifest.json'
COMPAT_REPOSITORY = 'ubs-engine'


def fail(message):
    print(f'::error::[ubs-bundle] {message}', flush=True)


def warn(message):
    print(f'::warning::[ubs-bundle] {message}', flush=True)


def info(message):
    print(f'[ubs-bundle] {message}', flush=True)


def sha256_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_index(web):
    path = web / 'repositories.json'
    try:
        index = json.loads(path.read_text('utf-8'))
    except OSError as error:
        raise ValueError(f'cannot read the index {path}: {error}') from error
    except ValueError as error:
        raise ValueError(f'the index {path} is not valid JSON: {error}') from error
    if not isinstance(index, dict) or not isinstance(index.get('repositories'), list) or not index['repositories']:
        raise ValueError(f'the index {path} must be an object with a non-empty repositories list')
    return index


def bundle_targets(web, index):
    """Ordered snapshot targets: (relpath, path, required, expected_repository)."""
    targets = [('repositories.json', web / 'repositories.json', True, None)]
    names, snapshot_paths = set(), set()
    for entry in index['repositories']:
        if not isinstance(entry, dict) or not entry.get('name') or not entry.get('repository'):
            raise ValueError(f'index entry without name/repository identity: {entry!r}')
        if entry['name'] in names:
            raise ValueError(f"duplicate repository name in the index: {entry['name']}")
        names.add(entry['name'])
        snapshot = entry.get('snapshot')
        if snapshot is None or snapshot == '':
            continue  # pending repository: never collected, no snapshot file expected
        if not isinstance(snapshot, str):
            raise ValueError(f"index entry {entry['name']} has a non-string snapshot reference: {snapshot!r}")
        if snapshot in snapshot_paths:
            raise ValueError(f'duplicate snapshot reference in the index: {snapshot}')
        snapshot_paths.add(snapshot)
        path = (web / snapshot).resolve()
        if web.resolve() not in path.parents:
            raise ValueError(f"index entry {entry['name']} references a snapshot outside web/data: {snapshot}")
        targets.append((snapshot, path, True, entry['repository']))
    targets.append(('snapshot.json', web / 'snapshot.json', False, None))
    return targets


def verify(root):
    """Return (fingerprint, digests, manifest_state, error_count)."""
    web = root / 'web' / 'data'
    data = root / 'data'
    try:
        index = load_index(web)
        targets = bundle_targets(web, index)
    except ValueError as error:
        fail(str(error))
        return None, [], 'absent', 1
    referenced = sum(1 for _, _, required, _ in targets if required) - 1
    info(f'index ok: {len(index["repositories"])} repositories, {referenced} snapshots referenced')
    errors = 0
    digests = []
    for rel, path, required, expected in targets:
        if not path.exists():
            if required:
                fail(f'missing snapshot {path} referenced by the index')
                errors += 1
            else:
                warn(f'{path} missing (ubs-engine compat copy; CI restores or fetches it)')
            continue
        try:
            payload = json.loads(path.read_text('utf-8'))
        except (OSError, ValueError) as error:
            fail(f'{path} is not valid JSON: {error}')
            errors += 1
            continue
        if expected is not None:
            repository = payload.get('meta', {}).get('repository') if isinstance(payload, dict) else None
            if repository != expected:
                fail(f'{path} belongs to {repository!r} but the index entry says {expected!r} (no cross-repo borrowing)')
                errors += 1
                continue
        digests.append((rel, sha256_file(path)))
    fingerprint = 'sha256:' + hashlib.sha256(
        ''.join(f'{rel} {digest}\n' for rel, digest in sorted(digests)).encode('utf-8')
    ).hexdigest()
    errors += check_mirrors(data, web, index)
    manifest_state = check_manifest(web, digests, fingerprint)
    if manifest_state in ('mismatch', 'invalid'):
        errors += 1
    return fingerprint, digests, manifest_state, errors


def check_mirrors(data, web, index):
    """Repo-root mirrors must never disagree with the published copies."""
    errors = 0
    pairs = [('repositories.json', data / 'repositories.json', web / 'repositories.json')]
    for entry in index['repositories']:
        snapshot = entry.get('snapshot')
        if snapshot:
            pairs.append((snapshot, data / snapshot, web / snapshot))
    pairs.append(('snapshot.json', data / 'snapshot.json', web / 'snapshot.json'))
    for rel, mirror, published in pairs:
        if mirror.exists() and published.exists():
            if mirror.read_bytes() != published.read_bytes():
                fail(f'mirror mismatch for {rel}: {mirror} differs from {published} (mixed versions)')
                errors += 1
        elif not mirror.exists():
            warn(f'mirror {mirror} missing (local subset; the shared cache restores it in CI)')
    compat = data / 'snapshot.json'
    engine = web / 'repos' / (COMPAT_REPOSITORY + '.json')
    if compat.exists() and engine.exists() and compat.read_bytes() != engine.read_bytes():
        fail(f'{compat} does not match the current {engine} (stale compat snapshot = mixed versions)')
        errors += 1
    return errors


def check_manifest(web, digests, fingerprint):
    path = web / MANIFEST_NAME
    if not path.exists():
        warn(f'{path} missing (first run or legacy bundle; version binding unavailable)')
        return 'absent'
    try:
        manifest = json.loads(path.read_text('utf-8'))
    except (OSError, ValueError) as error:
        fail(f'{path} is not valid JSON: {error}')
        return 'invalid'
    if not isinstance(manifest, dict) or not manifest.get('fingerprint'):
        fail(f'{path} has no fingerprint to compare against')
        return 'invalid'
    if manifest['fingerprint'] != fingerprint:
        recorded = manifest.get('files') if isinstance(manifest.get('files'), dict) else {}
        differing = [rel for rel, digest in sorted(digests) if recorded.get(rel) not in (None, digest)]
        detail = ('; differs: ' + ', '.join(differing)) if differing else ''
        fail(f'manifest fingerprint mismatch: expected {manifest["fingerprint"]}, bundle is {fingerprint}{detail}')
        return 'mismatch'
    info(f'manifest verified: bundle matches the recorded artifact fingerprint {fingerprint}')
    return 'verified'


def write_manifest(web, digests, fingerprint):
    payload = {
        'schema': 1,
        'fingerprint': fingerprint,
        'generated_at': datetime.now(timezone.utc).isoformat(),
        'files': {rel: digest for rel, digest in sorted(digests)},
    }
    path = web / MANIFEST_NAME
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', 'utf-8')
    info(f'manifest written: {path.name} ({len(payload["files"])} files, {fingerprint})')


def main():
    parser = argparse.ArgumentParser(description='Verify the shared UBS snapshot bundle before any deploy or cache save.')
    parser.add_argument('--root', default=str(Path(__file__).resolve().parent),
                        help='repository root (defaults to the directory containing this script)')
    parser.add_argument('--write-manifest', action='store_true',
                        help='stamp a fresh manifest after verification (daily workflow)')
    parser.add_argument('--ensure-manifest', action='store_true',
                        help='create the manifest only when absent (incremental workflow)')
    args = parser.parse_args()
    root = Path(args.root).resolve()
    fingerprint, digests, manifest_state, errors = verify(root)
    if fingerprint is None:
        return 1
    if errors == 0 and args.write_manifest:
        write_manifest(root / 'web' / 'data', digests, fingerprint)
        manifest_state = 'written'
    elif errors == 0 and args.ensure_manifest and manifest_state == 'absent':
        write_manifest(root / 'web' / 'data', digests, fingerprint)
        manifest_state = 'created'
    if errors:
        fail(f'{errors} bundle problem(s); refusing to publish or share this bundle')
        return 1
    info(f'ok files={len(digests)} fingerprint={fingerprint} manifest={manifest_state}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
