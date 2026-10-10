"""Delivery evidence adversarial probes. No production files or frozen evidence are changed."""
import argparse, contextlib, hashlib, importlib.util, io, json, os, subprocess, sys
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'audit'/'2026-10-10'/'evidence'
sys.path[:0]=[str(ROOT),str(ROOT/'scripts')]
import verify_acceptance as va
import verify_requirements_doc as vd
import verify_artifacts as artifacts
import verify_concurrency as concurrency
import verify_runtime as runtime
import source_coverage
import validate_bundle
import verify_ubs_semantics
from triton import verify_deployment as deployed
SELECTED=[12,13,20,21,22,23,24,25,38,39,40,50,51]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def ledger_summary(report):
 return {'overall':report['overall'],'req_statuses':dict(Counter(x['status'] for x in report['ledger'])),'ac_statuses':dict(Counter(x['status'] for x in report['acceptance_criteria'])),'selected_acs':[x for x in report['acceptance_criteria'] if int(x['req'][4:]) in SELECTED]}
def build_acceptance():
 audit=str(ROOT/'audit'/'2026-10-09');root=str(ROOT);problems=[]
 text=va._read_text(os.path.join(audit,'requirements.md'))
 model=va._load_json(os.path.join(audit,'evidence','requirements-model.json'))
 verification=va._load_json(os.path.join(audit,'evidence','requirements-verification.json'))
 checks=va._load_json(os.path.join(audit,'evidence','all-checks.json'))
 findings=va._load_json(os.path.join(audit,'evidence','findings.json'))
 reqs,doc=va.check_doc(text,model,verification,problems)
 _,findings_section=va.check_findings_mapping(text,findings,checks,model,problems)
 conclusions=va.check_conclusions(text,problems)
 integrity=va.check_integrity(root,audit,text,checks,findings,problems)
 commits,dup,error=va.collect_commits(root)
 if error:problems.append(error)
 ledger,acs,meta=va.build_ledger(reqs,commits,dup,'REQ-051',problems)
 kinds=va.check_kinds_and_synthesis(root,text,ledger,problems)
 return va.build_report(argparse.Namespace(root=root,delivering='REQ-051'),audit,{'doc':doc,'findings':findings_section,'conclusions':conclusions,'integrity':integrity,'ledger':ledger,'acs':acs,'kinds':kinds,'ledger_meta':meta},problems)
def run():
 frozen=ROOT/'audit'/'2026-10-09'/'evidence'
 protected=[ROOT/'audit'/'2026-10-09'/'requirements.md']+list(frozen.glob('*.json'))
 before={str(x.relative_to(ROOT)):sha(x) for x in protected}
 baseline=build_acceptance()
 load_json=va._load_json
 evidence_by_file={name:(keys,want) for name,keys,want in va.EVIDENCE_FILES.values()}
 def hollow_evidence(path):
  info=evidence_by_file.get(Path(path).name)
  if info:
   keys,want=info;data={};cur=data
   for key in keys[:-1]:cur[key]={};cur=cur[key]
   cur[keys[-1]]=want
   return data
  return load_json(path)
 with patch.object(va,'_load_json',hollow_evidence):hollow=build_acceptance()
 listdir=os.listdir
 removed=['test_acceptance.py','test_artifact_verification.py','test_concurrency_evidence.py','test_runtime_evidence.py','test_requirements_doc.py']
 def hide_tests(path):
  names=listdir(path)
  if Path(path).resolve()==(ROOT/'tests').resolve():return [x for x in names if x not in removed]
  return names
 with patch.object(os,'listdir',hide_tests):without_tests=build_acceptance()
 collect=va.collect_commits
 def omit_req051(root):
  commits,dup,error=collect(root);commits=dict(commits);commits.pop(51,None);return commits,dup,error
 with patch.object(va,'collect_commits',omit_req051):without_commit=build_acceptance()
 def truthful_acceptance(path):
  data=load_json(path)
  if Path(path).name=='acceptance-evidence.json':
   data=deepcopy(data)
   for entry in data['ledger']:
    if entry['req'] in ['REQ-038','REQ-039']:entry['status']='未验证'
   for entry in data['acceptance_criteria']:
    if entry['req'] in ['REQ-038','REQ-039']:entry['status']='未验证'
  return data
 truth_problems=[]
 with patch.object(va,'_load_json',truthful_acceptance):truth_result=vd.check_overall(str(ROOT),str(ROOT/'audit'/'2026-10-09'),truth_problems)
 category=source_coverage.SourceCategory('queue_components');category.record_applicable('https://ci.example/job/x/1/');category.record_derived('https://ci.example/job/x/1/')
 derived=category.result()
 duplicate=source_coverage.SourceCategory('job_timing');duplicate.record_applicable('job/1');duplicate.record_applicable('job/1');duplicate.record_verified('job/1');duplicate=duplicate.result()
 invalid_queue=[]
 for label,value in [('boolean',True),('negative',-12),('nan',float('nan')),('infinity',float('inf'))]:
  queue,parts=source_coverage.queue_from_raw({'actions':[{'waitingTimeMillis':value,'blockedTimeMillis':5,'buildableTimeMillis':3}]})
  invalid_queue.append({'input_kind':label,'queue_returned':repr(queue),'components_accepted':parts is not None})
 old_read_text,old_read_bytes=Path.read_text,Path.read_bytes
 index_path=ROOT/'web/data/repositories.json';index=json.loads(old_read_text(index_path,encoding='utf-8'));index['generated_at']='2026-10-10T02:30:00Z';index_bytes=json.dumps(index,ensure_ascii=False).encode()
 def changed_index_text(path,*args,**kwargs):
  if path.resolve()==index_path.resolve():return index_bytes.decode()
  return old_read_text(path,*args,**kwargs)
 def changed_index_bytes(path,*args,**kwargs):
  if path.resolve()==index_path.resolve():return index_bytes
  return old_read_bytes(path,*args,**kwargs)
 daily_log=io.StringIO()
 with patch.object(Path,'read_text',changed_index_text),patch.object(Path,'read_bytes',changed_index_bytes),patch.object(validate_bundle,'write_manifest') as writer,patch.object(sys,'argv',['validate_bundle.py','--root',str(ROOT),'--write-manifest']),contextlib.redirect_stdout(daily_log):
  daily_code=validate_bundle.main();daily_written=writer.called
 original_manifest=json.loads(old_read_text(ROOT/'web/data/ubs-manifest.json',encoding='utf-8'))
 truncated=deepcopy(original_manifest);truncated['files']={'repositories.json':original_manifest['files']['repositories.json']}
 def truncated_manifest_text(path,*args,**kwargs):
  if path.resolve()==(ROOT/'web/data/ubs-manifest.json').resolve():return json.dumps(truncated)
  return old_read_text(path,*args,**kwargs)
 manifest_log=io.StringIO();fetched=[]
 def fake_published_fetch(url):
  fetched.append(url)
  if url.endswith('/data/repositories.json'):return old_read_bytes(ROOT/'web/data/repositories.json')
  return b'{"tampered":true}'
 with patch.object(Path,'read_text',truncated_manifest_text),contextlib.redirect_stdout(manifest_log):
  _,digests,manifest_state,manifest_errors=validate_bundle.verify(ROOT)
  with patch.object(deployed,'fetch',fake_published_fetch):deployment_subset=deployed.verify_ubs('https://example.invalid/audit',ROOT/'web/data/ubs-manifest.json')
 source_records={}
 for name in ['artifact-verification.json','concurrency-evidence.json','runtime-evidence.json','acceptance-evidence.json','requirements-doc-evidence.json']:
  p=frozen/name;d=load_json(str(p));source_records[name]={'sha256':sha(p),'generated_at':d.get('generated_at',d.get('executed_at')),'overall':d.get('overall',d.get('overall_status'))}
  if name=='artifact-verification.json':source_records[name].update(sections=d['sections'],categories={key:{k:v[k] for k in ['applicable','verified_consistent','derived_consistent','differ','missing_evidence','status']} for key,v in d['ac02_comparisons'].items()},rerun_impact=d['ac03_rerun_impact']['summary'],deployment=d['ac04_deployment']['merged_dashboard_deployment'])
  if name=='concurrency-evidence.json':source_records[name].update(ac01=d['ac01_controlled_sequence'],ac03=d['ac03_run_history'],ac04=d['ac04_queue_max'])
  if name=='runtime-evidence.json':
   logs=[]
   for entry in d['runs']:
    p=ROOT/entry['log'];row={'label':entry['label'],'command':entry['command'],'exit_code':entry['exit_code'],'log':entry['log'],'exists':p.exists(),'summary':entry.get('summary'),'kind':entry['kind'],'audit_classification':entry.get('audit_classification')}
    if p.exists():row.update(bytes=p.stat().st_size,sha256=sha(p),tail_matches=p.read_text('utf-8').strip().endswith(entry['log_tail'].strip()))
    logs.append(row)
   source_records[name].update(runtimes=d['runtimes'],runs=logs,raw_audit_summary=d['raw_audit_summary'],has_source_revision=any(k in d for k in ['commit','git_sha','revision','head']),ci_declarations=d['ci_declarations'])
 fresh_artifact_log=io.StringIO()
 with contextlib.redirect_stdout(fresh_artifact_log):fresh_artifact,diff=artifacts.build_report(ROOT)
 fresh_concurrency,_=concurrency.build_report(ROOT)
 report={'schema_version':1,'generated_at':datetime.now(timezone.utc).isoformat(),'head':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),'runtime':sys.version,'scope':SELECTED,'source_records':source_records,'fresh_artifact_report_summary':{'overall_status':fresh_artifact['overall_status'],'sections':fresh_artifact['sections'],'has_differences':diff},'fresh_concurrency_summary':{'overall':fresh_concurrency['overall'],'ac01':fresh_concurrency['ac01_controlled_sequence']['status'],'ac03':fresh_concurrency['ac03_run_history']['status']},'probes':{'baseline_acceptance':ledger_summary(baseline),'erase_all_evidence_details_keep_expected_status_only':ledger_summary(hollow),'remove_selected_test_files_from_inventory_in_memory':{'hidden_files':removed,**ledger_summary(without_tests)},'omit_req051_commit_in_memory':ledger_summary(without_commit),'truthful_unverified_req038_req039_rejected_by_req051':{'result':truth_result,'problems':truth_problems},'derived_without_independent_raw':{'result':derived,'required_ac02_sum':derived['verified_consistent']+derived['differences']+derived['missing_evidence'],'denominator':derived['applicable']},'duplicate_source_identity':duplicate},'protected_evidence_unchanged':all(sha(ROOT/key)==value for key,value in before.items()),'notes':['All tampering is process-memory-only. No test, production snapshot, business source, or frozen evidence was modified.','Actual fresh helper reports were built in memory; their default output paths were never used.','No network writes, collection or deployment occurred.']}
 report['probes'].update(invalid_raw_queue_components=invalid_queue,daily_refresh_existing_manifest={'mutation':'Only index.generated_at advanced; retained manifest from restored warm cache','exit_code':daily_code,'manifest_written':daily_written,'log':daily_log.getvalue()},truncated_manifest_files={'build_gate_manifest_state':manifest_state,'build_gate_error_count':manifest_errors,'computed_file_count':len(digests),'recorded_file_count':len(truncated['files']),'postdeploy_record':deployment_subset,'fetched_urls':fetched,'log':manifest_log.getvalue()})
 report['probes']['missing_file_failure_classification']=source_coverage.failure_report(FileNotFoundError('raw artifact unavailable'))
 with contextlib.redirect_stdout(io.StringIO()):current_semantics,_=verify_ubs_semantics.build_report(ROOT)
 archived_semantics=json.loads((frozen/'ubs-semantics-evidence.json').read_text('utf-8'))
 report['additional_review']=[{'id':'REQ-041-AC01','status':'unverified','requirement':'Full replay of frozen203PR/826batch events/tasks/representatives with191/203/195task samples','fresh_counts':current_semantics['counts'],'fresh_overall':current_semantics['overall'],'fresh_baseline':current_semantics['audit_baseline_comparison'],'fresh_matches_audit_frozen_input':current_semantics['input']['matches_audit_frozen_input'],'historical_counts':archived_semantics['counts'],'historical_input':archived_semantics['input'],'available_fixtures':[str(x.relative_to(ROOT)) for x in (ROOT/'tests/fixtures').rglob('*.json')],'reason':'Current193PR/800batch data can be recomputed and is legitimate new input; old203PR event/batch/task source JSON is not retained as a replayable fixture. Stored hashes/aggregate audit report or historical verified status cannot replace those rows. Quantity drift itself is not a defect.','evidence':['scripts/verify_ubs_semantics.py:296','scripts/verify_ubs_semantics.py:298','scripts/verify_ubs_semantics.py:368','tests/test_ubs_semantics.py:301','audit/2026-10-09/evidence/ubs-semantics-evidence.json']}]
 OUT.mkdir(parents=True,exist_ok=True)
 path=OUT/'delivery-evidence-review.json';path.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
 print(json.dumps({'path':str(path),'head':report['head'],'baseline':baseline['overall'],'hollow_evidence':hollow['overall'],'tests_hidden':without_tests['overall'],'no_req051_commit':without_commit['overall'],'truthful_unverified_problems':truth_problems,'source_coverage_probe':derived,'protected_evidence_unchanged':report['protected_evidence_unchanged']},ensure_ascii=False,indent=2))
if __name__=='__main__':run()
