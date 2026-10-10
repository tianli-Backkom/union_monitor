"""Validate the audit artifact, not claim the failing product acceptance criteria pass."""
import hashlib,json,re,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'audit'/'2026-10-10'
def read(name):return json.loads((OUT/'evidence'/name).read_text('utf-8'))
class AuditArtifactTests(unittest.TestCase):
    def test_original_files_unchanged(self):
        before=read('tracked-before.json')
        self.assertEqual(len(before['files']),245)
        for f in before['files']:
            self.assertEqual(hashlib.sha256((ROOT/f['path']).read_bytes()).hexdigest(),f['sha256'],f['path'])
    def test_all_requirements_and_criteria_present(self):
        expected=json.loads((ROOT/'audit/2026-10-09/evidence/requirements-model.json').read_text('utf-8'))
        matrix=read('acceptance-matrix.json')
        # The review's producer must expose its actual AC records, not a success total.
        rows=matrix.get('acceptance',matrix.get('criteria',matrix.get('ac_results',[])))
        if not rows and 'requirements' in matrix:
            rows=[a for r in matrix['requirements'] for a in r.get('acceptance',r.get('criteria',[]))]
        wanted={a['id']:a['text'] for r in expected['requirements'] for a in r['acceptance']}
        self.assertEqual(len(rows),195)
        self.assertEqual({a.get('id',a.get('ac')) for a in rows},set(wanted))
        self.assertEqual(len({a.get('req',a.get('id',a.get('ac',''))[:7]) for a in rows}),51)
        for a in rows:
            self.assertIn(a['status'],{'passed','failed','partial','unverified','not_applicable'})
            self.assertTrue(a.get('reason'),a)
            self.assertEqual(a['criterion'],wanted[a['id']])
            if a['status']=='passed':self.assertTrue(a.get('evidence'),a)
        self.assertTrue(any(a['status']=='failed' for a in rows),'Known counterexamples may not be suppressed')
        self.assertTrue(any(a['status']=='unverified' for a in rows),'Missing source proofs may not be marked passed')
    def test_matrix_evidence_versions_match(self):
        matrix=read('acceptance-matrix.json')
        for source in matrix['sources']:
            self.assertEqual(hashlib.sha256(Path(source['path']).read_bytes()).hexdigest(),source['sha256'])
        counts={status:sum(a['status']==status for a in matrix['acceptance']) for status in matrix['counts']}
        self.assertEqual(counts,matrix['counts'])
        self.assertFalse(matrix['delivery_complete'])
    def test_findings_reproducible_and_traceable(self):
        findings=read('findings.json')['findings']
        self.assertEqual(len(findings),16)
        self.assertEqual(len({f['id'] for f in findings}),16)
        for f in findings:
            for k in ['reqs','location','reproduction','expected','actual','impact','recommendation','evidence','input_kind']:
                self.assertTrue(f[k],(f['id'],k))
            source,line=f['location'].rsplit(':',1)
            self.assertTrue((ROOT/source).is_file(),source)
            self.assertLessEqual(int(line),len((ROOT/source).read_text('utf-8').splitlines()))
            for link in f['evidence']:
                p=OUT/'evidence'/link.split('#')[0]
                self.assertTrue(p.is_file(),p)
    def test_browser_findings_are_recorded_as_failures(self):
        tr=read('triton-adversarial.json')
        records={x['id']:x for x in tr['checks']}
        for key in ['EMPTY-RESTORE','INVALID-WINDOW','DOMAIN-HANG','BRANCH-PROTOTYPE']:
            self.assertEqual(records[key]['state'],'failed')
        for h in [6,12,24,48,72]:self.assertEqual(records['FROZEN-G-'+str(h)]['state'],'passed')
        self.assertEqual(tr['pageErrors'],[])
    def test_ci_logs_have_target_runtime_success(self):
        py=(OUT/'evidence/python-tests-ci.log').read_text('utf-8')
        node=(OUT/'evidence/node-tests-ci.log').read_text('utf-8')
        self.assertIn('Ran 425 tests',py)
        self.assertIn('OK (skipped=1)',py)
        self.assertRegex(node,r'# pass 122\b')
        self.assertRegex(node,r'# fail 0\b')
    def test_report_and_matrix_are_not_complete_claims(self):
        report=(OUT/'adversarial-review.md').read_text('utf-8')
        self.assertIn('完整交付尚未成立',report)
        self.assertIn('expectedFailure',report)
        self.assertTrue((OUT/'coverage-matrix.md').is_file())
        for i in range(1,17):self.assertIn('A'+str(i).zfill(2),report)
if __name__=='__main__':
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(AuditArtifactTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    record={'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'passed':result.wasSuccessful(),
            'scope':'audit artifact integrity only; product failing ACs remain failed'}
    (OUT/'evidence/audit-validation.json').write_text(json.dumps(record,indent=2)+'\n','utf-8')
    raise SystemExit(0 if result.wasSuccessful() else 1)
