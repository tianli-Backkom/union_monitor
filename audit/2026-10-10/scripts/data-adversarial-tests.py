"""Audit regression tests. Expected failures explicitly document unmet ACs."""
import sys
sys.dont_write_bytecode=True
import copy, importlib.util, math, unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('data_review',Path(__file__).with_name('data-adversarial.py'))
a=importlib.util.module_from_spec(spec);spec.loader.exec_module(a)

class DataReviewTests(unittest.TestCase):
    def test_independent_interpolation(self):
        self.assertEqual(a.ref_stats([600,600,900]),{'n':3,'mean':700,'p50':600,'p90':840})
        self.assertEqual(a.ref_stats([None,True,-1,float('nan')])['n'],0)

    def test_attempt_current_start_control(self):
        b=a.payload([a.row(2)])['batches'][0]
        self.assertEqual(b['duration_seconds'],300)
        self.assertEqual(b['start_source'],'attempt_start')
        self.assertTrue(b['approximate'])

    def test_no_attempt_start_remains_visible_and_unmeasured(self):
        p=a.payload([a.row(2,run_started_at=None)])
        self.assertEqual(len(p['batches']),1)
        self.assertIsNone(p['batches'][0]['duration_seconds'])
        self.assertEqual(p['summary']['valid'],0)

    def test_pages_schema_controls(self):
        before=len(a.R['cases']);a.pagination_cases()
        rows=a.R['cases'][before:]
        self.assertTrue(all(c['passed'] for c in rows if c['id'] in ['workflow-schema-missing','workflow-schema-null','workflow-schema-object','legal-zero-page','duplicate-page-id','declared-count-missing-page']))

    @unittest.expectedFailure
    def test_req015_ac01_collector_keeps_previous_attempts(self):
        before=len(a.R['cases']);a.attempt_cases()
        c=next(c for c in a.R['cases'][before:] if c['id']=='collector-still-enumerates-only-current-attempt')
        self.assertEqual(c['actual']['attempts'],[1,2,3])

    @unittest.expectedFailure
    def test_req018_ac03_declared_count_drift_rejected(self):
        before=len(a.R['cases']);a.pagination_cases()
        c=next(c for c in a.R['cases'][before:] if c['id']=='declared-count-changes-hide-truncation')
        self.assertTrue(c['actual']['rejected'])

    @unittest.expectedFailure
    def test_req019_ac01_checks_each_workflow_applicable_start(self):
        bad=a.row(1,trigger_at='2026-10-08T02:00:00Z',trigger_exact=True,updated_at='2026-10-08T01:00:00Z')
        aux=a.row(1,id=2,trigger_at='2026-10-08T00:30:00Z',trigger_exact=True,updated_at='2026-10-08T03:00:00Z')
        self.assertFalse(a.gate([bad,aux],a.payload([bad,aux]))['passed'])

    @unittest.expectedFailure
    def test_req019_ac02_invalid_as_of_rejected(self):
        r=a.row(2);p=a.payload([r]);p['window_end']='invalid'
        self.assertFalse(a.gate([r],p)['passed'])

    @unittest.expectedFailure
    def test_req019_gate_reconciles_summary(self):
        r=a.row(2);p=a.payload([r]);p['summary']['valid']=99
        self.assertFalse(a.gate([r],p)['passed'])

    @unittest.expectedFailure
    def test_req019_ac03_running_nan_not_observed(self):
        r=a.row(2,status='in_progress',conclusion=None);p=a.payload([r]);p['batches'][0]['duration_seconds']=float('nan')
        self.assertFalse(a.gate([r],p)['passed'])

if __name__=='__main__':unittest.main(verbosity=2)
