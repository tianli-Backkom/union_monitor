"""Actual downloaded directory trees must not lose or mislabel project bundles."""
import hashlib
import importlib
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from monitor.catalog import Catalog
from monitor.context import RunContext

ROOT = Path(__file__).resolve().parents[1]
CATALOG = Catalog.load(ROOT/'catalog.json')
CONTEXT = RunContext(run_id='run-files-1', code_sha='e'*40, cutoff_at='2026-10-10T00:00:00Z')


class ArtifactFolderTests(unittest.TestCase):
    def loader(self):
        self.assertIsNotNone(importlib.util.find_spec('monitor.artifacts'), 'missing real downloaded-bundle validator')
        return importlib.import_module('monitor.artifacts')

    def bundle(self, root, pid, name=None):
        project = CATALOG.project(pid)
        directory = root/(name or ('project-bundle-'+pid+'-42'))
        directory.mkdir(parents=True)
        window = CONTEXT.window_for(project)
        snapshot = {'schema_version': 3, 'project_id': pid, 'run_id': CONTEXT.run_id,
                    'code_sha': CONTEXT.code_sha, 'collector': project['collector'],
                    'window': window, 'collected_at': '2026-10-10T00:10:00Z',
                    'repositories': {r['repository_id']: ({'repo':r['repository_id'].split(':',1)[1], 'batches': []}
                        if pid=='triton' else {'meta':{'repository':r['repository_id'].split(':',1)[1]},'prs':[]})
                        for r in project['repositories']}}
        raw = json.dumps(snapshot, sort_keys=True).encode()
        (directory/'snapshot.json').write_bytes(raw)
        report = {'run_id': CONTEXT.run_id, 'code_sha': CONTEXT.code_sha, 'project_id': pid,
                  'collector':project['collector'], 'metric_profile':project['metric_profile'],
                  'task_status':'success', 'collection_status':'success', 'validation_status':'passed', 'exit_code':0,
                  'window':window, 'collected_at':snapshot['collected_at'], 'snapshot_version':pid+'@v1',
                  'snapshot_path':'snapshot.json', 'snapshot_sha256':hashlib.sha256(raw).hexdigest()}
        (directory/'collection-report.json').write_text(json.dumps(report), encoding='utf-8')
        return directory, report, snapshot

    def test_two_independent_downloads_survive_with_relocated_paths(self):
        module = self.loader()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for pid in ('ubs','triton'):
                directory, report, _ = self.bundle(root,pid)
                report['snapshot_path'] = '/old/runner/.shadow/work/'+pid+'/snapshot.json'
                (directory/'collection-report.json').write_text(json.dumps(report), encoding='utf-8')
            reports = module.load_project_reports(root,CATALOG,CONTEXT)
            self.assertEqual(set(reports), {'ubs','triton'})
            for pid,report in reports.items():
                self.assertEqual(report['task_status'],'success')
                self.assertEqual(Path(report['snapshot_path']).parent.name,'project-bundle-'+pid+'-42')
                self.assertTrue(Path(report['snapshot_path']).is_file())

    def test_missing_report_is_explicit_failed_project(self):
        module=self.loader()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); self.bundle(root,'ubs')
            reports=module.load_project_reports(root,CATALOG,CONTEXT)
            self.assertEqual(reports['triton']['task_status'],'failed')
            self.assertIn('report',reports['triton']['error'])

    def test_duplicate_reports_block_instead_of_last_file_wins(self):
        module=self.loader()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); self.bundle(root,'ubs'); self.bundle(root,'ubs','duplicate')
            with self.assertRaisesRegex(module.ArtifactError,'duplicate'):
                module.load_project_reports(root,CATALOG,CONTEXT)

    def test_wrong_hash_missing_file_and_escape_are_rejected(self):
        module=self.loader()
        for mutation in ('hash','missing','escape'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                root=Path(folder); directory,report,_=self.bundle(root,'ubs')
                if mutation=='hash': report['snapshot_sha256']='f'*64
                elif mutation=='missing': (directory/'snapshot.json').unlink()
                else: report['snapshot_path']='../other/snapshot.json'
                (directory/'collection-report.json').write_text(json.dumps(report),encoding='utf-8')
                with self.assertRaises(module.ArtifactError): module.load_project_reports(root,CATALOG,CONTEXT)

    def test_wrong_run_code_window_and_snapshot_ownership_are_rejected(self):
        module=self.loader()
        for mutation in ('run','code','window','project','repository'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                root=Path(folder); directory,report,snapshot=self.bundle(root,'ubs')
                if mutation=='run': report['run_id']='other-run'
                elif mutation=='code': report['code_sha']='x'*40
                elif mutation=='window': report['window']['end_at']='2026-10-09T00:00:00Z'
                elif mutation=='project': snapshot['project_id']='triton'
                else: snapshot['repositories']['github:wrong/repo']=snapshot['repositories'].pop('gitcode:openeuler/ubs-engine')
                raw=json.dumps(snapshot).encode(); (directory/'snapshot.json').write_bytes(raw)
                report['snapshot_sha256']=hashlib.sha256(raw).hexdigest()
                (directory/'collection-report.json').write_text(json.dumps(report),encoding='utf-8')
                with self.assertRaises(module.ArtifactError): module.load_project_reports(root,CATALOG,CONTEXT)

    def test_missing_window_components_cannot_claim_fresh(self):
        module=self.loader()
        for key in ('time_basis','start_at','end_at'):
            with self.subTest(key=key), tempfile.TemporaryDirectory() as folder:
                root=Path(folder); directory,report,snapshot=self.bundle(root,'ubs')
                del report['window'][key]
                snapshot['window']=report['window']
                raw=json.dumps(snapshot).encode(); (directory/'snapshot.json').write_bytes(raw)
                report['snapshot_sha256']=hashlib.sha256(raw).hexdigest()
                (directory/'collection-report.json').write_text(json.dumps(report),encoding='utf-8')
                with self.assertRaises(module.ArtifactError): module.load_project_reports(root,CATALOG,CONTEXT)

    def test_failure_cannot_claim_successful_task_or_validation(self):
        module=self.loader()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder); directory,report,_=self.bundle(root,'ubs')
            report['collection_status']='failed'; report['exit_code']=1; report['task_status']='failed'
            (directory/'collection-report.json').write_text(json.dumps(report),encoding='utf-8')
            with self.assertRaises(module.ArtifactError): module.load_project_reports(root,CATALOG,CONTEXT)


if __name__=='__main__': unittest.main()
