# 交付证据对抗审查

审查 HEAD：`4cfff7d49052734cfb9b3c3c2f03187d01c92108`。本范围13个REQ、52个AC，结果：`{'pass': 27, 'fail': 10, 'partial': 9, 'unverified': 6}`。完整交付结论：**不能成立**。

## 核心可重复反例

1. 验收台账：实际证据细节清空只保留期望顶层状态、五个相关测试从内存目录清单移除、REQ051提交从内存映射移除，三种情形均仍为 verified/195个AC通过。代码在 verify_acceptance.py:535/538/579 以提交认定并复制状态；REQ051工具还要求51/51通过，反而拒绝如实未验证状态。
2. 暖每日链路：仅把索引 generated_at 推进而保留缓存旧manifest，生产 validate_bundle.main(--write-manifest)退出1、清单未写；publish_index每次采集均更新该时间，工作流恢复旧清单后会命中此路径。现有暖链测试从空B目录盖章，跳过这个真实前置条件。
3. 清单完整性：将manifest.files缩成仅repositories.json，保留原fingerprint，上传前门禁仍verified（计算10文件，清单只记录1文件）；部署验证仅下载索引便返回成功，九份引用快照完全未抓取。
4. 原始证据：REQ038各类独立verified_consistent为0；没有同run多个attempt、合并站真实部署、并发A/B/C运行ID。文件诚实保留unverified，但逐AC台账全部通过。
5. queue非法原始分项：bool/负数/NaN/Infinity均被queue_from_raw接受；derived-only覆盖分母1而三项和0；重复身份分母2/verified1仍status=verified。

复现：先运行 `delivery-probes.py`，再运行 `delivery-finalize.py`（相邻audit脚本，Python3.12；只在本次audit树写证据）。所有tamper仅在内存，原始冻结证据哈希仍相同。

## 逐条AC结果

| AC | 结果 | 判断依据 |
|---|---|---|
| REQ-012-AC01 | pass | Both workflows now use identical ordered shared paths and versioned ubs-snapshots-v1 keys; collection evidence cache is separated. |
| REQ-012-AC02 | fail | Warm daily generation cannot stamp bundle B while restored A manifest remains: --write-manifest exits 1 before stamping even if only generated_at changed. |
| REQ-012-AC03 | fail | The manifest files table is not checked against computed digests: truncating it to index-only still yields verified, losing the promised complete artifact binding. |
| REQ-012-AC04 | partial | Per-file fallback and cache-present logs exist, but file presence is labelled cache hit without binding it to actions/cache-hit/cache-matched-key outputs; warm daily failure remains. |
| REQ-013-AC01 | fail | Existing warm-chain test constructs B in a fresh directory, skipping the production condition of a restored A manifest in the daily workspace. Real --write-manifest rejects that condition. |
| REQ-013-AC02 | pass | Local replay extracts production Ensure UBS data script and checks cold fallback plus missing/empty references through the bundle gate; historical chain log is available. |
| REQ-013-AC03 | pass | Mixed cached snapshot is rejected by manifest/range verification in local tests. |
| REQ-013-AC04 | partial | Local A/B fingerprints and source logs exist, but the SUMMARY explicitly says isolated Actions run IDs are still missing. |
| REQ-020-AC01 | pass | Malformed/empty index and referenced snapshot failures are covered by the actual bundle gate and local controlled tests. |
| REQ-020-AC02 | pass | Every referenced snapshot is parsed and repository ownership checked; pending/first-failed entries without snapshots remain distinct. |
| REQ-020-AC03 | pass | Both workflow paths call the same validate_bundle gate; local chain tests name missing references and restore sources. |
| REQ-020-AC04 | pass | Build gate precedes cache save/upload and deploy needs build. Controlled negative tests cover failed restore; actual online rollback is not claimed. |
| REQ-021-AC01 | pass | Success/partial snapshots must match index repository and start/end window; repositoryRows applies the current/included rule. |
| REQ-021-AC02 | pass | Failed/stale/pending/zero-PR scopes have distinct inclusion and display rules with controlled tests. |
| REQ-021-AC03 | pass | Repository/range/manifest mismatches are blocked with explicit reasons in existing tests. |
| REQ-021-AC04 | partial | Triton JSON/CSV/manifest/output-evidence consistency is checked, but dashboard-data.json is itself written from the final payload; verify_artifacts does not read or recompute enriched-runs.json build inputs. |
| REQ-022-AC01 | fail | No real build/deploy/URL record is provided, and an index-only manifest files list passes the build gate and postdeploy verifier without fetching nine referenced snapshots. |
| REQ-022-AC02 | pass | Production verify_triton reads /data/triton.json; fresh controlled tests verify that route. |
| REQ-022-AC03 | pass | Bounded retry and failure summary/no-rollback behavior are exercised by fresh controlled mismatch/fetch-error tests and wired into both workflows. |
| REQ-022-AC04 | unverified | record_success can emit run IDs/URL/time/fingerprints in real CI, but all retained examples are synthetic example.github.io records with null IDs; artifact evidence declares actual deployment unverified. |
| REQ-023-AC01 | pass | Raw-empty applicable jobs remain source-unverified with checks_passed false in fresh integration tests. |
| REQ-023-AC02 | fail | Derived-only object yields applicable=1 but verified+difference+missing=0; duplicate applicable identities can yield verified with denominator2/verified1/missing0. The stated three-term accounting invariant is violated. |
| REQ-023-AC03 | pass | Partial independent evidence is kept partial and task missing identities are retained in fresh tests. |
| REQ-023-AC04 | pass | No-applicable-object result is N/A with a reason and no accuracy percentage. |
| REQ-024-AC01 | pass | 12/5/3 component sum and queue/total/statistical propagation are covered by fresh integrated source tests. |
| REQ-024-AC02 | fail | queue_from_raw accepts bool, negative values, NaN and infinity as components; invalid parts do not remain unknown. |
| REQ-024-AC03 | pass | Controlled raw-only component tampering is detected with full job URL and components in the existing fresh tests. |
| REQ-024-AC04 | partial | Verified/derived/missing categories exist, but derived-only evidence is removed from missing denominator and duplicate identities break complete coverage accounting. |
| REQ-025-AC01 | partial | Job time/queue source states are separated from derived consistency, but source PR identity and attempt-history sections promised by the requirement are omitted/deferred. |
| REQ-025-AC02 | fail | failure_report(FileNotFoundError) yields overall_status=failed, contradicting missing-file=unverified distinction required by AC02. |
| REQ-025-AC03 | pass | Unexpected exceptions retain error and affected_scope and are re-raised; runtime evidence correctly records raw-audit exit1 rather than wrapper success. |
| REQ-025-AC04 | partial | Exit/report consistency is covered for the two implemented categories; omitted PR/attempt scopes and derived coverage accounting prevent a full declared-scope source verdict. |
| REQ-038-AC01 | pass | Inventory lists current frozen artifact hashes/windows and honestly marks eight missing categories; this satisfies inventory transparency, not source completion. |
| REQ-038-AC02 | unverified | Independent verified_consistent is zero in all four artifact categories; payload/CSV self-consistency is derived evidence and original timestamp/queue/identity/attempt proof remains missing. |
| REQ-038-AC03 | unverified | Seven rerun batches have no same-run multiple-attempt raw records or persisted attempt starts; bounds and a synthetic 300-second example do not establish actual affected batches. |
| REQ-038-AC04 | unverified | No real controlled merged build/deploy/public JSON correspondence is available; retained report explicitly states unverified. |
| REQ-039-AC01 | unverified | Controlled running A/pending B/C real event sequence and isolated workflow run IDs are absent; only a future protocol exists. |
| REQ-039-AC02 | pass | README/test naming now distinguish running protection from pending replacement; current static checks agree. |
| REQ-039-AC03 | unverified | Actual workflow history is not read; report honestly remains unverified. Lack of a local remote alone cannot prove a repository was never pushed. |
| REQ-039-AC04 | pass | queue:max is explicitly deferred with a documented future decision; the requirement does not force enabling it. |
| REQ-040-AC01 | partial | Retained Python3.12.3/Node22.23.3 logs exist and match tails, but contain 255 Python tests before REQ050/051 additions and no source HEAD binding; they do not certify current HEAD. Fresh scoped tests here run Python3.12.14, bundled Node is24.19.0. |
| REQ-040-AC02 | pass | Original79/34 baseline is labelled historical rather than used as the target-version result. |
| REQ-040-AC03 | pass | Raw audit failures due to missing artifacts are recorded as not_passed/failed_missing_artifacts, not converted to passed from gate exit0. |
| REQ-040-AC04 | partial | Declared/support versions are3.12/22 and historical result matches those versions, but current-head same-version verification is incomplete and no exact code revision is recorded. |
| REQ-050-AC01 | fail | The ledger derives all AC statuses from commit names and blindly copies each REQ status; hollow evidence, hidden associated tests and a missing delivering commit still produce195 AC passed. |
| REQ-050-AC02 | pass | F01-F19, D10/P04 mapping, fixed counts and source hashes are structurally verified. |
| REQ-050-AC03 | partial | Frozen failed checks are preserved, but no per-AC post-fix re-evaluation links every old failure to actual proof; fresh counterexamples remain despite all-commit pass. |
| REQ-050-AC04 | fail | Input kinds are hardcoded by REQ/type; REQ040 is labelled real deployment although its records are local target-runtime tests and actual deployment is absent. Hollow evidence is accepted. |
| REQ-051-AC01 | pass | Document has51 unique consecutive requirements and195 uniquely numbered ACs with the required structure and tracking. |
| REQ-051-AC02 | pass | 37 remediation/3 evidence/9 preservation/2 delivery classifications are explicit and structurally checked. |
| REQ-051-AC03 | pass | Frozen source hashes and document baseline match; existing document validation covers local links and attribution; this audit does not change frozen evidence. |
| REQ-051-AC04 | fail | check_overall demands51 passed/zero unverified while source evidence is incomplete; truthfully markingREQ038/039 unverified is rejected. Document overall verified is a structural result, not delivery completion. |

## 追加 REQ041-AC01 核对

结果未验证。当前193PR/800批的合法新数据可以独立重算；verify_ubs_semantics在指纹不是原冻结版本时将baseline设为not_applicable_input_drifted，仍可给当前输入overall verified。原203PR/826批的事件、批次、任务JSON没有可重放fixture，仅历史报告、聚合和哈希仍存在；这些记录不能替代当时全部输入。数量变化本身不算缺陷。详见JSON additional_review。

## 验证与限度

本次专项测试：Python 3.12.14，62项，失败0、错误0、跳过0。完整日志保存在JSON fresh_scoped_tests.log。

历史runtime日志存在且tail一致，支持历史3.12.3/22.23.3的255/122测试记录；其没有HEAD绑定，早于050/051增量测试。该记录不能扩展成当前HEAD全部AC交付。
未执行线上采集、刷新、部署，也未触发工作流。真实历史/原始工件缺失与可重复代码缺陷分别记录，未把未验证写成已确认线上故障。
