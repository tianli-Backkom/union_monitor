"""Fail closed on incomplete legacy UBS collection before the Pages build.

This gate reads the collector's diagnostic index and snapshots. It does not
change collector exit behavior or turn retained snapshots into a fallback
release. Empty, successfully collected repositories are valid.
"""
import argparse
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def verify_collection_status(index_path, config_path=ROOT / 'repositories.json'):
    errors = []
    index_path = Path(index_path)
    try:
        config = read_json(config_path)
        index = read_json(index_path)
        if not isinstance(config, list) or not config:
            raise ValueError('configured repository list is empty or invalid')
        if not isinstance(index, dict) or not isinstance(index.get('repositories'), list):
            raise ValueError('collection index has no repository list')
    except (OSError, ValueError, TypeError) as exc:
        return {'passed': False, 'errors': ['repository index/config: ' + str(exc)]}

    expected = {}
    for item in config:
        if not isinstance(item, dict) or not isinstance(item.get('name'), str) or not item.get('name'):
            errors.append('configured repository has no valid name')
            continue
        name = item['name']
        if name in expected or not isinstance(item.get('repository'), str) or not item.get('repository'):
            errors.append('configured repository identity is invalid or duplicated: ' + name)
            continue
        expected[name] = item['repository']

    seen = set()
    for entry in index['repositories']:
        if not isinstance(entry, dict):
            errors.append('repository index entry is not an object')
            continue
        name = entry.get('name')
        if not isinstance(name, str) or name not in expected:
            errors.append('unexpected repository in collection index: ' + str(name))
            continue
        if name in seen:
            errors.append('duplicate repository in collection index: ' + name)
            continue
        seen.add(name)
        repository = expected[name]
        if entry.get('repository') != repository:
            errors.append(name + ': repository identity does not match configuration')
        if entry.get('status') != 'success':
            errors.append(name + ': collection status ' + str(entry.get('status')) + '; ' + str(entry.get('error') or 'collection did not succeed'))

        def check_meta(meta, source):
            if not isinstance(meta, dict) or meta.get('repository') != repository:
                errors.append(name + ': ' + source + ' metadata has invalid repository identity')
                return
            source_errors = meta.get('errors')
            if not isinstance(source_errors, list):
                errors.append(name + ': ' + source + ' meta.errors is missing or invalid')
            elif source_errors:
                errors.append(name + ': ' + source + ' meta.errors: ' + json.dumps(source_errors, ensure_ascii=False))

        check_meta(entry.get('meta'), 'index')
        # The collector publishes this exact repository-isolated relative path.
        # Reject alternate/escaping references instead of following them.
        snapshot = entry.get('snapshot')
        if snapshot != 'repos/' + name + '.json':
            errors.append(name + ': repository snapshot reference is missing or invalid')
            continue
        path = index_path.parent / snapshot
        try:
            path.resolve().relative_to(index_path.parent.resolve())
            payload = read_json(path)
            if not isinstance(payload, dict):
                raise ValueError('snapshot is not an object')
            check_meta(payload.get('meta'), 'snapshot')
        except (OSError, ValueError, TypeError) as exc:
            errors.append(name + ': repository snapshot could not be verified: ' + str(exc))

    for name in sorted(expected.keys() - seen):
        errors.append('missing repository in collection index: ' + name)
    return {'passed': not errors, 'expected_repositories': len(expected),
            'checked_repositories': len(seen), 'errors': errors}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--index', type=Path, default=ROOT / 'data/repositories.json')
    parser.add_argument('--config', type=Path, default=ROOT / 'repositories.json')
    args = parser.parse_args(argv)
    report = verify_collection_status(args.index, args.config)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
