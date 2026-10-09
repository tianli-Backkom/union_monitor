"""Raw-source coverage accounting for the independent audits (REQ-023).

Derived consistency never masquerades as source accuracy: every verifiable
category declares its denominator, and the report states how many objects were
verified against raw evidence, how many differ and how many lack evidence,
with traceable identities and an explicit status per category.
"""
MISSING_LIMIT = 50


class SourceCategory:
    """Accumulates raw-source verification outcomes for one category of objects."""

    def __init__(self, name, not_applicable_reason='no applicable objects in this run (nothing to verify against raw sources)'):
        self.name = name
        self.not_applicable_reason = not_applicable_reason
        self._applicable = []
        self._verified = set()
        self._differences = []

    def record_applicable(self, identity):
        self._applicable.append(identity)

    def record_verified(self, identity):
        self._verified.add(identity)

    def record_difference(self, identity, detail):
        self._differences.append((identity, detail))

    def result(self):
        applicable = len(self._applicable)
        verified = len(self._verified)
        differences = len(self._differences)
        difference_ids = {identity for identity, _ in self._differences}
        missing = [identity for identity in self._applicable
                   if identity not in self._verified and identity not in difference_ids]
        if applicable == 0:
            status = 'not_applicable'
        elif differences:
            status = 'differences_found'
        elif not missing:
            status = 'verified'
        elif verified == 0:
            status = 'unverified'
        else:
            status = 'partial'
        result = {'category': self.name, 'applicable': applicable, 'verified_consistent': verified,
                  'differences': differences, 'missing_evidence': len(missing),
                  'missing': missing[:MISSING_LIMIT], 'missing_truncated': len(missing) > MISSING_LIMIT,
                  'difference_details': [f'{identity}: {detail}' for identity, detail in self._differences[:MISSING_LIMIT]],
                  'status': status}
        if applicable == 0:
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
