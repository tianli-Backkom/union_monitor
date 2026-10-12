"""The legacy daily workflow must not deploy after a swallowed UBS failure."""
import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/'scripts'/'verify_collection_status.py'
CONFIG=json.loads((ROOT/'repositories.json').read_text('utf-8'))


class CollectionStatusGateTests(unittest.TestCase):
    def write_bundle(self, folder):
        root=Path(folder); (root/'repos').mkdir()
        entries=[]
        for config in CONFIG:
            meta={'repository':config['repository'], 'errors':[], 'expected_prs':0, 'collected_prs':0}
            snapshot='repos/'+config['name']+'.json'
            (root/snapshot).write_text(json.dumps({'meta':meta,'prs':[]}),encoding='utf-8')
            entries.append({**config,'status':'success','snapshot':snapshot,'meta':copy.deepcopy(meta)})
        index=root/'repositories.json'
        index.write_text(json.dumps({'repositories':entries}),encoding='utf-8')
        return root,index,entries

    def gate(self, index):
        return subprocess.run([sys.executable,'-B',str(SCRIPT),'--index',str(index)],capture_output=True,text=True,encoding='utf-8')

    def test_all_nine_success_with_zero_samples_is_legal(self):
        with tempfile.TemporaryDirectory() as folder:
            _,index,_=self.write_bundle(folder)
            result=self.gate(index)
        self.assertEqual(result.returncode,0,result.stderr+result.stdout)
        self.assertTrue(json.loads(result.stdout)['passed'])

    def test_failed_and_partial_repository_each_block_the_cli(self):
        for status in ('failed','partial'):
            with self.subTest(status=status),tempfile.TemporaryDirectory() as folder:
                _,index,entries=self.write_bundle(folder)
                entries[2]['status']=status; entries[2]['error']='source unavailable'
                index.write_text(json.dumps({'repositories':entries}),encoding='utf-8')
                result=self.gate(index)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('ubs-virt',result.stdout)
                self.assertIn(status,result.stdout)

    def test_index_or_snapshot_collection_errors_cannot_hide_under_success(self):
        for owner in ('index','snapshot'):
            with self.subTest(owner=owner),tempfile.TemporaryDirectory() as folder:
                root,index,entries=self.write_bundle(folder)
                if owner=='index':
                    entries[0]['meta']['errors']=[{'source':'comments','reason':'collection failed'}]
                    index.write_text(json.dumps({'repositories':entries}),encoding='utf-8')
                else:
                    snapshot=root/entries[0]['snapshot']; payload=json.loads(snapshot.read_text('utf-8'))
                    payload['meta']['errors']=[{'source':'comments','reason':'collection failed'}]
                    snapshot.write_text(json.dumps(payload),encoding='utf-8')
                result=self.gate(index)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('ubs-engine',result.stdout)
                self.assertIn('collection failed',result.stdout)

    def test_missing_or_duplicate_repository_cannot_shrink_the_required_set(self):
        for mutation in ('missing','duplicate'):
            with self.subTest(mutation=mutation),tempfile.TemporaryDirectory() as folder:
                _,index,entries=self.write_bundle(folder)
                if mutation=='missing': entries.pop()
                else: entries[-1]=copy.deepcopy(entries[0])
                index.write_text(json.dumps({'repositories':entries}),encoding='utf-8')
                result=self.gate(index)
                self.assertNotEqual(result.returncode,0)
                self.assertIn('repository',result.stdout)

    def test_daily_workflow_checks_collection_status_before_further_collection(self):
        workflow=(ROOT/'.github/workflows/pages.yml').read_text('utf-8')
        self.assertIn('python -X utf8 scripts/verify_collection_status.py',workflow)
        self.assertLess(workflow.index('collect.py --all'),workflow.index('scripts/verify_collection_status.py'))
        self.assertLess(workflow.index('scripts/verify_collection_status.py'),workflow.index('triton.dashboard --hours'))


if __name__=='__main__': unittest.main()
