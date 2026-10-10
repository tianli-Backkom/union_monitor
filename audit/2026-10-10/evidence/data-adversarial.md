# Current data adversarial audit

HEAD: 4cfff7d49052734cfb9b3c3c2f03187d01c92108

Cases: {'cases': 54, 'passed': 40, 'failed': 14}

## Confirmed current-code failures

- P1 collector-still-enumerates-only-current-attempt (REQ-015-AC01)
  Expected: `{"attempts": [1, 2, 3]}`
  Actual: `{"attempts": [3], "job_calls": ["/actions/runs/1/attempts/3/jobs"], "batches": 1}`
  Code: triton/dashboard.py:470-491
- P1 collector-old-run-beyond-lookback-is-lost (REQ-015-AC02)
  Expected: `{"attempts": [2], "batches": 1}`
  Actual: `{"attempts": [], "job_calls": [], "batches": 0}`
  Code: triton/dashboard.py:192,457-471
- P2 declared-count-changes-hide-truncation (REQ-018-AC03)
  Expected: `{"rejected": true}`
  Actual: `{"rejected": false, "count": 100}`
  Code: triton/dashboard.py:362-373
- P2 duplicate-records-without-id (REQ-018-AC03)
  Expected: `{"rejected": true}`
  Actual: `{"rejected": false, "count": 200}`
  Code: triton/dashboard.py:364-369
- P2 other-workflow-masks-inverted-applicable-start (REQ-019-AC01)
  Expected: `{"passed": false}`
  Actual: `{"passed": true, "errors": [], "warnings": [], "runs": 2, "batches": 1, "npu_points": 0}`
  Code: triton/quality.py:28-38; triton/dashboard.py:231-248
- P2 invalid-as-of-missing (REQ-019-AC02, REQ-019-AC03)
  Expected: `{"passed": false}`
  Actual: `{"passed": true, "errors": [], "warnings": [], "runs": 1, "batches": 1, "npu_points": 0}`
  Code: triton/quality.py:15-18
- P2 invalid-as-of-invalid (REQ-019-AC02, REQ-019-AC03)
  Expected: `{"passed": false}`
  Actual: `{"passed": true, "errors": [], "warnings": [], "runs": 1, "batches": 1, "npu_points": 0}`
  Code: triton/quality.py:15-18
- P2 quality-duration-negative (REQ-019-AC02)
  Expected: `{"passed": false}`
  Actual: `{"passed": true, "errors": [], "warnings": [], "runs": 1, "batches": 1, "npu_points": 0, "input_duration": -1, "stored_summary": {"prs": 1, "batches": 1, "valid": 1, "median": 300.0, "p90": 300.0, "approximate": 1, "incomplete": 0, "api_calls": 0}, "independent_summary": {"prs": 1, "batches": 1, "valid": 0, "median": null, "p90": null, "approximate": 1, "incomplete": 0, "api_calls": 0}}`
  Code: triton/quality.py:77-89
- P2 quality-duration-null (REQ-019-AC02)
  Expected: `{"passed": false}`
  Actual: `{"passed": true, "errors": [], "warnings": [], "runs": 1, "batches": 1, "npu_points": 0, "input_duration": null, "stored_summary": {"prs": 1, "batches": 1, "valid": 1, "median": 300.0, "p90": 300.0, "approximate": 1, "incomplete": 0, "api_calls": 0}, "independent_summary": {"prs": 1, "batches": 1, "valid": 0, "median": null, "p90": null, "approximate": 1, "incomplete": 0, "api_calls": 0}}`
  Code: triton/quality.py:77-89
- P2 quality-duration-bool (REQ-019-AC02)
  Expected: `{"passed": false}`
  Actual: `{"passed": true, "errors": [], "warnings": [], "runs": 1, "batches": 1, "npu_points": 0, "input_duration": true, "stored_summary": {"prs": 1, "batches": 1, "valid": 1, "median": 300.0, "p90": 300.0, "approximate": 1, "incomplete": 0, "api_calls": 0}, "independent_summary": {"prs": 1, "batches": 1, "valid": 0, "median": null, "p90": null, "approximate": 1, "incomplete": 0, "api_calls": 0}}`
  Code: triton/quality.py:77-89
- P2 quality-duration-string (REQ-019-AC02)
  Expected: `{"passed": false}`
  Actual: `{"passed": true, "errors": [], "warnings": [], "runs": 1, "batches": 1, "npu_points": 0, "input_duration": "300", "stored_summary": {"prs": 1, "batches": 1, "valid": 1, "median": 300.0, "p90": 300.0, "approximate": 1, "incomplete": 0, "api_calls": 0}, "independent_summary": {"prs": 1, "batches": 1, "valid": 0, "median": null, "p90": null, "approximate": 1, "incomplete": 0, "api_calls": 0}}`
  Code: triton/quality.py:77-89
- P2 quality-duration-wrong-span (REQ-019-AC02)
  Expected: `{"passed": false}`
  Actual: `{"passed": true, "errors": [], "warnings": [], "runs": 1, "batches": 1, "npu_points": 0, "input_duration": 999, "stored_summary": {"prs": 1, "batches": 1, "valid": 1, "median": 300.0, "p90": 300.0, "approximate": 1, "incomplete": 0, "api_calls": 0}, "independent_summary": {"prs": 1, "batches": 1, "valid": 1, "median": 999, "p90": 999, "approximate": 1, "incomplete": 0, "api_calls": 0}}`
  Code: triton/quality.py:77-89
- P2 quality-contradictory-summary (REQ-019-AC02, REQ-046-AC01)
  Expected: `{"passed": false}`
  Actual: `{"passed": true, "errors": [], "warnings": [], "runs": 1, "batches": 1, "npu_points": 0, "stored_summary": {"prs": 1, "batches": 1, "valid": 99, "median": 300.0, "p90": 999, "approximate": 1, "incomplete": 0, "api_calls": 0}, "independent_summary": {"prs": 1, "batches": 1, "valid": 1, "median": 300.0, "p90": 300.0, "approximate": 1, "incomplete": 0, "api_calls": 0}}`
  Code: triton/quality.py:13-92
- P2 running-nan-observed-span (REQ-019-AC03)
  Expected: `{"passed": false}`
  Actual: `{"passed": true, "errors": [], "warnings": [], "runs": 1, "batches": 1, "npu_points": 0}`
  Code: triton/quality.py:85-89

## Evidence limits

- No live API, collector cache writes, refresh, migration or deployment occurred; collect() is called only with all I/O mocked.
- Current frozen snapshots are preserved inputs; their agreement cannot establish real source pagination or complete attempt history.
- Full raw source evidence is not present; source accuracy and historical impact are unverified.
- REQ-014 AC04/REQ-016 AC03-04 UI/CSV checks belong to browser reviewer; these cases only establish pure data behavior.
- audit/2026-10-09 is read only; .playwright-mcp is untouched. Root coordinates the required commit.
