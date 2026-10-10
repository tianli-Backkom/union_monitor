"""Finalize owned delivery-evidence audit with per-AC verdicts and fresh scoped tests."""
import contextlib,io,json,os,re,sys,unittest,tempfile
from collections import Counter
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'audit'/'2026-10-10'/'evidence'
sys.path[:0]=[str(ROOT),str(ROOT/'scripts'),str(ROOT/'tests')]
os.environ['PYTHONDONTWRITEBYTECODE']='1'
task_temp=OUT/'delivery-test-temp';task_temp.mkdir(parents=True,exist_ok=True)
tempfile.tempdir=str(task_temp)
os.environ['TEMP']=str(task_temp);os.environ['TMP']=str(task_temp)
import runpy
runpy.run_path(str(Path(__file__).with_name('delivery-probes.py')),run_name='__main__')
report=json.loads((OUT/'delivery-evidence-review.json').read_text('utf-8'))
log=io.StringIO();suite=unittest.TestSuite();loader=unittest.TestLoader()
modules=['test_source_coverage','test_bundle_verifier','test_verify_deployment','test_shared_cache_config']
for name in modules:suite.addTests(loader.loadTestsFromName(name))
with contextlib.redirect_stdout(log),contextlib.redirect_stderr(log):
 result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
report['fresh_scoped_tests']={'modules':modules,'runtime':sys.version,'tests':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'passed':result.wasSuccessful(),'log':log.getvalue()}
matrix={};reasons={};proofs={}
def add(req,statuses,explanations,evidence):
 matrix[req]=statuses;reasons[req]=explanations;proofs[req]=evidence
add(12,['pass','fail','fail','partial'],[
 'Both workflows now use identical ordered shared paths and versioned ubs-snapshots-v1 keys; collection evidence cache is separated.',
 'Warm daily generation cannot stamp bundle B while restored A manifest remains: --write-manifest exits 1 before stamping even if only generated_at changed.',
 'The manifest files table is not checked against computed digests: truncating it to index-only still yields verified, losing the promised complete artifact binding.',
 'Per-file fallback and cache-present logs exist, but file presence is labelled cache hit without binding it to actions/cache-hit/cache-matched-key outputs; warm daily failure remains.'],
 ['.github/workflows/pages.yml:32','.github/workflows/triton-refresh.yml:36','tests/test_shared_cache_config.py','validate_bundle.py:180','validate_bundle.py:225','probes.daily_refresh_existing_manifest','probes.truncated_manifest_files'])
add(13,['fail','pass','pass','partial'],[
 'Existing warm-chain test constructs B in a fresh directory, skipping the production condition of a restored A manifest in the daily workspace. Real --write-manifest rejects that condition.',
 'Local replay extracts production Ensure UBS data script and checks cold fallback plus missing/empty references through the bundle gate; historical chain log is available.',
 'Mixed cached snapshot is rejected by manifest/range verification in local tests.',
 'Local A/B fingerprints and source logs exist, but the SUMMARY explicitly says isolated Actions run IDs are still missing.'],
 ['tests/test_cache_chain.py:95','.omo/evidence/req-013/SUMMARY.txt','repository_store.py:76','validate_bundle.py:225','probes.daily_refresh_existing_manifest'])
add(20,['pass','pass','pass','pass'],[
 'Malformed/empty index and referenced snapshot failures are covered by the actual bundle gate and local controlled tests.',
 'Every referenced snapshot is parsed and repository ownership checked; pending/first-failed entries without snapshots remain distinct.',
 'Both workflow paths call the same validate_bundle gate; local chain tests name missing references and restore sources.',
 'Build gate precedes cache save/upload and deploy needs build. Controlled negative tests cover failed restore; actual online rollback is not claimed.'],
 ['validate_bundle.py:58','validate_bundle.py:104','tests/test_bundle_verifier.py','tests/test_cache_chain.py','.github/workflows/pages.yml:80','.github/workflows/triton-refresh.yml:182'])
add(21,['pass','pass','pass','partial'],[
 'Success/partial snapshots must match index repository and start/end window; repositoryRows applies the current/included rule.',
 'Failed/stale/pending/zero-PR scopes have distinct inclusion and display rules with controlled tests.',
 'Repository/range/manifest mismatches are blocked with explicit reasons in existing tests.',
 'Triton JSON/CSV/manifest/output-evidence consistency is checked, but dashboard-data.json is itself written from the final payload; verify_artifacts does not read or recompute enriched-runs.json build inputs.'],
 ['validate_bundle.py:77','validate_bundle.py:132','tests/test_bundle_verifier.py:258','triton/quality.py:110','triton/dashboard.py','tests/test_triton_quality.py'])
add(22,['fail','pass','pass','unverified'],[
 'No real build/deploy/URL record is provided, and an index-only manifest files list passes the build gate and postdeploy verifier without fetching nine referenced snapshots.',
 'Production verify_triton reads /data/triton.json; fresh controlled tests verify that route.',
 'Bounded retry and failure summary/no-rollback behavior are exercised by fresh controlled mismatch/fetch-error tests and wired into both workflows.',
 'record_success can emit run IDs/URL/time/fingerprints in real CI, but all retained examples are synthetic example.github.io records with null IDs; artifact evidence declares actual deployment unverified.'],
 ['triton/verify_deployment.py:27','triton/verify_deployment.py:42','triton/verify_deployment.py:94','tests/test_verify_deployment.py','source_records.artifact-verification.json.deployment','probes.truncated_manifest_files'])
add(23,['pass','fail','pass','pass'],[
 'Raw-empty applicable jobs remain source-unverified with checks_passed false in fresh integration tests.',
 'Derived-only object yields applicable=1 but verified+difference+missing=0; duplicate applicable identities can yield verified with denominator2/verified1/missing0. The stated three-term accounting invariant is violated.',
 'Partial independent evidence is kept partial and task missing identities are retained in fresh tests.',
 'No-applicable-object result is N/A with a reason and no accuracy percentage.'],
 ['source_coverage.py:47','source_coverage.py:83','tests/test_source_coverage.py','probes.derived_without_independent_raw','probes.duplicate_source_identity'])
add(24,['pass','fail','pass','partial'],[
 '12/5/3 component sum and queue/total/statistical propagation are covered by fresh integrated source tests.',
 'queue_from_raw accepts bool, negative values, NaN and infinity as components; invalid parts do not remain unknown.',
 'Controlled raw-only component tampering is detected with full job URL and components in the existing fresh tests.',
 'Verified/derived/missing categories exist, but derived-only evidence is removed from missing denominator and duplicate identities break complete coverage accounting.'],
 ['source_coverage.py:13','source_coverage.py:83','tests/test_source_coverage.py','probes.invalid_raw_queue_components','probes.derived_without_independent_raw'])
add(25,['partial','fail','pass','partial'],[
 'Job time/queue source states are separated from derived consistency, but source PR identity and attempt-history sections promised by the requirement are omitted/deferred.',
 'failure_report(FileNotFoundError) yields overall_status=failed, contradicting missing-file=unverified distinction required by AC02.',
 'Unexpected exceptions retain error and affected_scope and are re-raised; runtime evidence correctly records raw-audit exit1 rather than wrapper success.',
 'Exit/report consistency is covered for the two implemented categories; omitted PR/attempt scopes and derived coverage accounting prevent a full declared-scope source verdict.'],
 ['validate.py:90','validate_multi.py:134','source_coverage.py:38','tests/test_source_coverage.py','.omo/evidence/req-025/SUMMARY.txt','probes.missing_file_failure_classification'])
add(38,['pass','unverified','unverified','unverified'],[
 'Inventory lists current frozen artifact hashes/windows and honestly marks eight missing categories; this satisfies inventory transparency, not source completion.',
 'Independent verified_consistent is zero in all four artifact categories; payload/CSV self-consistency is derived evidence and original timestamp/queue/identity/attempt proof remains missing.',
 'Seven rerun batches have no same-run multiple-attempt raw records or persisted attempt starts; bounds and a synthetic 300-second example do not establish actual affected batches.',
 'No real controlled merged build/deploy/public JSON correspondence is available; retained report explicitly states unverified.'],
 ['scripts/verify_artifacts.py:140','scripts/verify_artifacts.py:636','scripts/verify_artifacts.py:750','source_records.artifact-verification.json'])
add(39,['unverified','pass','unverified','pass'],[
 'Controlled running A/pending B/C real event sequence and isolated workflow run IDs are absent; only a future protocol exists.',
 'README/test naming now distinguish running protection from pending replacement; current static checks agree.',
 'Actual workflow history is not read; report honestly remains unverified. Lack of a local remote alone cannot prove a repository was never pushed.',
 'queue:max is explicitly deferred with a documented future decision; the requirement does not force enabling it.'],
 ['scripts/verify_concurrency.py:180','scripts/verify_concurrency.py:208','source_records.concurrency-evidence.json'])
add(40,['partial','pass','pass','partial'],[
 'Retained Python3.12.3/Node22.23.3 logs exist and match tails, but contain 255 Python tests before REQ050/051 additions and no source HEAD binding; they do not certify current HEAD. Fresh scoped tests here run Python3.12.14, bundled Node is24.19.0.',
 'Original79/34 baseline is labelled historical rather than used as the target-version result.',
 'Raw audit failures due to missing artifacts are recorded as not_passed/failed_missing_artifacts, not converted to passed from gate exit0.',
 'Declared/support versions are3.12/22 and historical result matches those versions, but current-head same-version verification is incomplete and no exact code revision is recorded.'],
 ['scripts/verify_runtime.py:153','scripts/verify_runtime.py:180','source_records.runtime-evidence.json','fresh_scoped_tests'])
add(50,['fail','pass','partial','fail'],[
 'The ledger derives all AC statuses from commit names and blindly copies each REQ status; hollow evidence, hidden associated tests and a missing delivering commit still produce195 AC passed.',
 'F01-F19, D10/P04 mapping, fixed counts and source hashes are structurally verified.',
 'Frozen failed checks are preserved, but no per-AC post-fix re-evaluation links every old failure to actual proof; fresh counterexamples remain despite all-commit pass.',
 'Input kinds are hardcoded by REQ/type; REQ040 is labelled real deployment although its records are local target-runtime tests and actual deployment is absent. Hollow evidence is accepted.'],
 ['scripts/verify_acceptance.py:510','scripts/verify_acceptance.py:535','scripts/verify_acceptance.py:579','scripts/verify_acceptance.py:68','probes.baseline_acceptance','probes.erase_all_evidence_details_keep_expected_status_only','probes.remove_selected_test_files_from_inventory_in_memory','probes.omit_req051_commit_in_memory'])
add(51,['pass','pass','pass','fail'],[
 'Document has51 unique consecutive requirements and195 uniquely numbered ACs with the required structure and tracking.',
 '37 remediation/3 evidence/9 preservation/2 delivery classifications are explicit and structurally checked.',
 'Frozen source hashes and document baseline match; existing document validation covers local links and attribution; this audit does not change frozen evidence.',
 'check_overall demands51 passed/zero unverified while source evidence is incomplete; truthfully markingREQ038/039 unverified is rejected. Document overall verified is a structural result, not delivery completion.'],
 ['scripts/verify_requirements_doc.py:345','scripts/verify_requirements_doc.py:372','source_records.requirements-doc-evidence.json','probes.truthful_unverified_req038_req039_rejected_by_req051'])
doc=(ROOT/'audit/2026-10-09/requirements.md').read_text('utf-8');ac_text={}
for line in doc.splitlines():
 m=re.match(r'- \*\*(REQ-\d{3}-AC\d{2})：\*\* (.*)',line)
 if m:ac_text[m[1]]=m[2]
rows=[]
for req,statuses in matrix.items():
 for i,status in enumerate(statuses,1):
  identity=f'REQ-{req:03d}-AC{i:02d}'
  rows.append({'id':identity,'req':f'REQ-{req:03d}','status':status,'acceptance_text':ac_text.get(identity),'reason':reasons[req][i-1],'evidence':proofs[req],'source_revision':report['head']})
report['acceptance_review']=rows;report['status_counts']=dict(Counter(x['status'] for x in rows));report['delivery_complete']=False
report['highest_risk_findings']=[
 {'id':'DE01','priority':'P1','title':'Commit-based ledger certifies missing and hollow evidence','reqs':[50,51],'proof':'probes.erase_all_evidence_details_keep_expected_status_only'},
 {'id':'DE02','priority':'P1','title':'Warm daily refresh fails on the restored old manifest before stamping new bundle','reqs':[12,13],'proof':'probes.daily_refresh_existing_manifest'},
 {'id':'DE03','priority':'P1','title':'Manifest file omission suppresses postdeployment snapshot verification','reqs':[12,22],'proof':'probes.truncated_manifest_files'},
 {'id':'DE04','priority':'P1','title':'Required real source/multi-attempt/deployment/concurrency evidence still unverified','reqs':[22,38,39],'proof':'source_records'},
 {'id':'DE05','priority':'P2','title':'Coverage denominator drops derived-only evidence and mishandles duplicate identities','reqs':[23,24,25],'proof':'probes.derived_without_independent_raw'},
 {'id':'DE06','priority':'P2','title':'Invalid raw queue components accepted as numeric values','reqs':[24],'proof':'probes.invalid_raw_queue_components'},
 {'id':'DE07','priority':'P2','title':'Missing artifact exception reported failed instead of source-unverified','reqs':[25],'proof':'probes.missing_file_failure_classification'}]
report['limitations']=['No actual workflow triggered; no collection, deployment or network write occurred.','Scoped tests and controlled fakes prove local behavior only. Real original artifacts and GitHub run IDs remain absent.','Existing runtime records are reviewed as historical logs and have no source revision binding.','No production file or frozen evidence was changed; root handles one audit-only Git commit.']
(OUT/'delivery-evidence-review.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
lines=['# 交付证据对抗审查','',f"审查 HEAD：`{report['head']}`。本范围13个REQ、52个AC，结果：`{report['status_counts']}`。完整交付结论：**不能成立**。",'',
 '## 核心可重复反例','',
 '1. 验收台账：实际证据细节清空只保留期望顶层状态、五个相关测试从内存目录清单移除、REQ051提交从内存映射移除，三种情形均仍为 verified/195个AC通过。代码在 verify_acceptance.py:535/538/579 以提交认定并复制状态；REQ051工具还要求51/51通过，反而拒绝如实未验证状态。',
 '2. 暖每日链路：仅把索引 generated_at 推进而保留缓存旧manifest，生产 validate_bundle.main(--write-manifest)退出1、清单未写；publish_index每次采集均更新该时间，工作流恢复旧清单后会命中此路径。现有暖链测试从空B目录盖章，跳过这个真实前置条件。',
 '3. 清单完整性：将manifest.files缩成仅repositories.json，保留原fingerprint，上传前门禁仍verified（计算10文件，清单只记录1文件）；部署验证仅下载索引便返回成功，九份引用快照完全未抓取。',
 '4. 原始证据：REQ038各类独立verified_consistent为0；没有同run多个attempt、合并站真实部署、并发A/B/C运行ID。文件诚实保留unverified，但逐AC台账全部通过。',
 '5. queue非法原始分项：bool/负数/NaN/Infinity均被queue_from_raw接受；derived-only覆盖分母1而三项和0；重复身份分母2/verified1仍status=verified。', '',
 '复现：先运行 `delivery-probes.py`，再运行 `delivery-finalize.py`（相邻audit脚本，Python3.12；只在本次audit树写证据）。所有tamper仅在内存，原始冻结证据哈希仍相同。', '',
 '## 逐条AC结果','', '| AC | 结果 | 判断依据 |','|---|---|---|']
for row in rows:lines.append('| '+row['id']+' | '+row['status']+' | '+row['reason'].replace('|','/')+' |')
lines+=['','## 追加 REQ041-AC01 核对','',
 '结果未验证。当前193PR/800批的合法新数据可以独立重算；verify_ubs_semantics在指纹不是原冻结版本时将baseline设为not_applicable_input_drifted，仍可给当前输入overall verified。原203PR/826批的事件、批次、任务JSON没有可重放fixture，仅历史报告、聚合和哈希仍存在；这些记录不能替代当时全部输入。数量变化本身不算缺陷。详见JSON additional_review。',
 '','## 验证与限度','',f"本次专项测试：Python {sys.version.split()[0]}，{result.testsRun}项，失败{len(result.failures)}、错误{len(result.errors)}、跳过{len(result.skipped)}。完整日志保存在JSON fresh_scoped_tests.log。",'',
 '历史runtime日志存在且tail一致，支持历史3.12.3/22.23.3的255/122测试记录；其没有HEAD绑定，早于050/051增量测试。该记录不能扩展成当前HEAD全部AC交付。',
 '未执行线上采集、刷新、部署，也未触发工作流。真实历史/原始工件缺失与可重复代码缺陷分别记录，未把未验证写成已确认线上故障。']
(OUT/'delivery-evidence-review.md').write_text('\n'.join(lines)+'\n','utf-8')
print(json.dumps({'tests':report['fresh_scoped_tests']['tests'],'passed':result.wasSuccessful(),'ACs':len(rows),'statuses':report['status_counts'],'delivery_complete':False,'outputs':['delivery-evidence-review.json','delivery-evidence-review.md']},ensure_ascii=False))
