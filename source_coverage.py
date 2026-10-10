"""Raw-source coverage accounting for the independent audits (REQ-023, REQ-024).

Derived consistency never masquerades as source accuracy: every verifiable
category declares its denominator, and the report states how many objects were
verified against raw evidence, how many are only derived-self-consistent, how
many differ and how many lack evidence, with traceable identities and an
explicit status per category.
"""
import math

MISSING_LIMIT = 50
QUEUE_KEYS = ('waitingTimeMillis', 'blockedTimeMillis', 'buildableTimeMillis')


def _valid_component(value):
    # REQ-024 (A11): True is an int in Python, so a bare isinstance check
    # accepts booleans; NaN and Infinity pass float checks but cannot be
    # queue milliseconds; negative queue time is physically impossible.
    # Any of these must leave queue unknown instead of "verified against raw".
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value) and value >= 0)


def queue_from_raw(raw):
    """Recompute queue_ms from a raw Jenkins record under the REQ-024 contract.

    Mirrors the metrics.normalize_job arithmetic (sum of the three raw queue
    fields), but every component must be a finite non-negative number with
    bools rejected: any missing or illegal component leaves queue unknown
    (REQ-024 AC02) instead of being summed into a "verified" value.

    Returns (queue_ms, components): components is a dict of the three raw
    queue fields when all are valid, else None.
    """
    actions = raw.get('actions', [])
    q = next((a for a in actions if 'waitingTimeMillis' in a), {})
    if all(_valid_component(q.get(k)) for k in QUEUE_KEYS):
        return sum(q[k] for k in QUEUE_KEYS), {k: q[k] for k in QUEUE_KEYS}
    return None, None


PUBLISH_CONSISTENCY_REASON = ('owned by validate_bundle.py before upload and triton.verify_deployment after deploy; '
                              'this audit does not re-verify it')


def section_of(category):
    """Project a source category result into a report section: status plus N/A reason (REQ-025)."""
    result = {'status': category['status']}
    if 'reason' in category:
        result['reason'] = category['reason']
    return result


def failure_report(error):
    """Report written when an audit aborts on a missing-evidence or unexpected exception (REQ-025 AC02/AC03)."""
    # REQ-025 (A12): a missing raw artifact or missing permission is a known
    # missing-evidence condition, so it must read as unverified rather than
    # failed; a real crash stays failed. checks_passed stays False either way
    # because unknown must never become a pass.
    if isinstance(error, (FileNotFoundError, PermissionError)):
        return {'overall_status': 'unverified', 'checks_passed': False,
                'error': f'{type(error).__name__}: {error}',
                'affected_scope': 'audit aborted before completion; raw evidence unavailable so coverage is unverified; no section of this run can be claimed passed'}
    return {'overall_status': 'failed', 'checks_passed': False,
            'error': f'{type(error).__name__}: {error}',
            'affected_scope': 'audit aborted before completion; no section of this run can be claimed passed'}


class SourceCategory:
    """Accumulates raw-source verification outcomes for one category of objects."""

    def __init__(self, name, not_applicable_reason='no applicable objects in this run (nothing to verify against raw sources)'):
        self.name = name
        self.not_applicable_reason = not_applicable_reason
        self._applicable = []
        self._verified = set()
        self._verified_absent = set()
        self._derived = set()
        self._differences = []

    def record_applicable(self, identity):
        self._applicable.append(identity)

    def record_verified(self, identity):
        self._verified.add(identity)

    def record_verified_absence(self, identity):
        """Raw evidence confirms no value exists (e.g. queue components absent, snapshot keeps None)."""
        self._verified.add(identity)
        self._verified_absent.add(identity)

    def record_derived(self, identity):
        """Value present but unverifiable from raw; only derived consistency could be checked."""
        self._derived.add(identity)

    def record_difference(self, identity, detail):
        self._differences.append((identity, detail))

    def result(self):
        # REQ-023 (A10): every count is accounted per unique applicable identity —
        # duplicate registrations can neither inflate the denominator nor
        # duplicate a missing entry, and a derived-consistent object still
        # lacks raw evidence, so it counts as missing evidence;
        # derived_consistent stays an attribute of that missing population
        # (REQ-024 AC04).
        applicable_ids = list(dict.fromkeys(self._applicable))
        applicable = set(applicable_ids)
        verified = len(self._verified & applicable)
        difference_ids = {identity for identity, _ in self._differences} & applicable
        differences = len(difference_ids)
        missing = [identity for identity in applicable_ids
                   if identity not in self._verified and identity not in difference_ids]
        derived = len(self._derived & set(missing))
        if not applicable_ids:
            status = 'not_applicable'
        elif differences:
            status = 'differences_found'
        elif not missing:
            status = 'verified'
        elif verified == 0:
            status = 'unverified'
        else:
            status = 'partial'
        result = {'category': self.name, 'applicable': len(applicable_ids), 'verified_consistent': verified,
                  'verified_absent': len(self._verified_absent & applicable), 'derived_consistent': derived,
                  'differences': differences, 'missing_evidence': len(missing),
                  'missing': missing[:MISSING_LIMIT], 'missing_truncated': len(missing) > MISSING_LIMIT,
                  'difference_details': [f'{identity}: {detail}' for identity, detail in self._differences[:MISSING_LIMIT]],
                  'status': status}
        if not applicable_ids:
            result['reason'] = self.not_applicable_reason
        return result


def source_report(categories):
    """Combine per-category results into the overall source-audit verdict (REQ-023)."""
    results = {name: category.result() for name, category in categories.items()}
    statuses = [result['status'] for result in results.values()]
    if all(status == 'not_applicable' for status in statuses):
        overall = 'not_applicable'
    elif any(status == 'differences_found' for status in statuses):
        overall = 'differences_found'
    elif all(status in ('verified', 'not_applicable') for status in statuses):
        overall = 'verified'
    elif any(status == 'unverified' for status in statuses):
        overall = 'unverified'
    else:
        overall = 'partial'
    return {'status': overall, 'categories': results}
