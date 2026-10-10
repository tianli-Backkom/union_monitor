/* Query-state primitives for the S/L model and concern de-duplication
   (T-004, P-004, T-005, P-005).

   - analysis set S: records selected by the analysis scope + explicit sample
     conditions (KPI/trend/threshold/denominator consume S).
   - list set L: S narrowed by the list search and list-local filters only;
     a search never recomputes KPI, coverage or P90, and never changes S.

   Concern rows are de-duplicated by stable batch identity: one row per batch
   with multiple reason labels; reason counts may overlap while the unique
   total never sums overlapping reasons. */
(function (root) {
  function matchesQuery(record, query, fields) {
    const q = String(query == null ? '' : query).trim().toLowerCase();
    if (!q) return true;
    const haystack = (fields || [])
      .map(function (fn) { return fn(record); })
      .filter(function (value) { return value != null; })
      .map(String)
      .join(' ');
    return haystack.toLowerCase().indexOf(q) !== -1;
  }

  function selectAnalysis(records, predicate) {
    const list = Array.isArray(records) ? records : [];
    const test = predicate || (function () { return true; });
    return list.filter(test);
  }

  function selectList(analysisSet, query, fields) {
    return analysisSet.filter(function (record) { return matchesQuery(record, query, fields); });
  }

  function dedupeConcerns(concerns, batchIdOf, reasonsOf) {
    const index = new Map();
    for (const concern of (Array.isArray(concerns) ? concerns : [])) {
      const id = batchIdOf(concern);
      if (id == null || id === '') continue;
      if (!index.has(id)) index.set(id, { batchId: id, item: concern, reasons: [] });
      const entry = index.get(id);
      for (const reason of (reasonsOf(concern) || [])) {
        if (entry.reasons.indexOf(reason) === -1) entry.reasons.push(reason);
      }
    }
    return Array.from(index.values());
  }

  function concernSummary(indexed) {
    const reasonCounts = {};
    for (const entry of indexed) {
      for (const reason of entry.reasons) {
        reasonCounts[reason] = (reasonCounts[reason] || 0) + 1;
      }
    }
    return { unique: indexed.length, reasonCounts };
  }

  const api = { matchesQuery, selectAnalysis, selectList, dedupeConcerns, concernSummary };
  if (typeof module !== 'undefined') module.exports = api;
  else root.QueryState = api;
})(typeof window !== 'undefined' ? window : globalThis);