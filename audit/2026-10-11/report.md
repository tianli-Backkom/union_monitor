# 统一看板对抗性审查报告

证据采集：2026-10-11；修复与验证：2026-10-12。审查代码基线：`e98c6af7c0640605e220c6696515528c31d343e8`。对象：[union_monitor](https://github.com/tianli-Backkom/union_monitor)、[线上看板](https://tianli-backkom.github.io/union_monitor/#triton)、[产品设计](../../docs/design/2026-10-10-unified-dashboard-product.md)与[技术设计](../../docs/design/2026-10-10-unified-dashboard-architecture.md)。

## 审查结论

当前站点有可用的 UBS / Triton 分析能力，但**尚未达到完整统一看板目标态**。最重要的数据问题是 Triton 把未关联 PR 的单 workflow 记录混入提交批次 E2E 样本。基础导航、窄屏核心字段、采集失败状态与影子工件链也存在可复现缺陷。本轮修复这些缺陷并建立回归门禁；统一生产调度、可信降级发布、权威发布基线与自动恢复仍需独立迁移验收。

审查采用三个独立视角（数据、前端/文档、架构），结合线上截图、冻结数据独立复算、来源定向抽样、故障注入和真实 Chromium。既有测试全绿曾漏掉真实适配器、界面接线和整批数据丢失，因此新增测试覆盖实际入口及错误传播。P1 表示核心功能或统计可信性受损；P2 表示分析、使用或运维判断受影响。以下修复状态是代码状态，部署状态以[交付记录](evidence/delivery.json)为准。

## 主要发现与处置

| ID / 优先级 | 基线问题及用户影响 | 本轮处置 / 验证 |
|---|---|---|
| R01 / P1 | Triton 未关联 PR 的 workflow 与 PR 提交批次混算，E2E 分母和分位数失真 | 保留所有观测记录，明确 E2E 资格及排除原因；Python、Node、实际视图与资格导出一致 |
| R02 / P1 | NPU 门禁从派生批次推导“应存在”集合，删除整个窗内批次仍通过 | 从来源 run/attempt 独立推导应有集合；原删除攻击现在失败，合法窗外 attempt 允许排除 |
| R03 / P1 | 所有新项目路由落到工作台；旧路由切回后可能同时显示两页，原详情引用残留 | 对接已有项目能力，未提供任务明确提示；视图互斥和同步清理；真实浏览器覆盖往返、历史与 modal |
| R04 / P1 | 工作台未读取当前生产快照，却显示“本轮失败/不可用”或“无关注” | 使用实际加载快照；分别说明读取结果和原采集时间，明确统一运行报告/关注聚合尚未提供 |
| R05 / P1 | 默认 Triton adapter 参数类型和返回协议不匹配，影子采集确定失败；adapter 默认伪造验证通过 | 修复真实 collector 边界，执行项目验证，来源错误传播为非成功；以真实协议测试代替全盘 fake runner |
| R06 / P1 | 两个 Matrix artifact 同名文件合并覆盖，项目报告/数据串归属 | 保留独立工件目录；加载器核对项目集合、run/SHA/窗口、实际文件和指纹；缺报告按失败 |
| R07 / P1 | legacy UBS collect 吞掉单仓错误，来源失败仍可能以成功 Actions 发布 | 每日流程新增九仓采集状态门禁；failed/partial/meta.errors 阻断本轮整站部署，合法零数据允许。该策略尚非目标态的部分成功发布 |
| R08 / P2 | 关注列表同一批次重复；未知 PR 被赋共同“第 N/276 次”和空 PR 链接 | 按稳定批次去重、多原因标签；未知 PR 显示独立 run/attempt，不伪造 PR 序列或链接 |
| R09 / P2 | 390px 隐藏批次结果和时长；跨路由遗留定时器/浮层；超时只覆盖响应头 | 显示核心字段并允许模块横向查看；清理监听、定时器及 pointer capture；完整 JSON 读取超时、并发响应防护和旧数据保留 |
| R10 / P2 | 新鲜度按错误的 08/13/18/20 日程计算，可能错过真实增量更新 | 与实际 08/12/16/18/20 计划及 90 分钟宽限一致；新增只读公开健康检查 |
| R11 / P2 | README 在线地址仍占位，默认开发数据来自两个旧站，筛选、排序、统一导出描述不准确 | 简化为入口→启动→口径→生产状态→门禁；同站 JSON 引导，保留显式旧 HTML 兼容；文档契约测试 |
| R12 / P1（统一上线阻断） | 通用 assemble 接受不可信 fresh/fallback；monitor.verify 只比部分字段；rollback 只返回记录 | 未冒充本轮已完成；见下表。影子加载器和 legacy 公开逐文件验证的修复不替代这三个公共接口 |

## 数据准确性与完整性

审查捕获的 72 小时 Triton 快照含 **371 批次、53 个已知 PR**。其中 **276 条（74.39%）未关联 PR**；256 条未关联 workflow 观测进入原 349 个终态 E2E 样本。该集合与“PR 提交/重跑批次”的粒度不同。

| 同一冻结快照的诊断集合 | 行数 | 有效 E2E 样本 | 中位数（秒） | P90（秒） |
|---|---:|---:|---:|---:|
| 原发布集合 | 371 | 349 | 227 | 2359.2 |
| 已知 PR 关联子集 | 95 | 93 | 1580 | 6428.4 |
| 未知 PR 观测子集 | 276 | 256（原错误资格） | 16.5 | 1075.5 |

修复本地回放保留 **371 行及原 batch ID**，已关联 PR 的有效批次 E2E 样本为 93（不是 93 个 PR 代表样本）。这个子集 P90 不是全部真实 PR 的总体 P90；排除未知身份减少混算，但未修复关联缺失的来源原因。资格谓词检查明确未知 PR、显式资格排除、终态及有限非负耗时，仍依赖既有 PRResolver/质量证据链确认来源身份；旧快照缺少资格/身份字段时保留数值规则兼容，不表示重新验证了 PR/SHA/attempt 身份。22 个取消批次保留观测而不进入 Triton 终态分位数；UBS 的终态取消资格按原项目定义保留。P90 采用 `(n−1)×0.9` 线性插值，非 SLA。旧 Triton CSV 16 列及秒单位保持，新增资格 JSON 单独版本化并绑定发布指纹。

UBS 捕获九仓均为 success，**167 PR / 720 批次**；PR、批次身份及窗口检查未发现串仓。独立复算每 PR 代表批次和任务汇总无差异，跨仓 E2E 为 n=167、P90=**4010760.2 毫秒**，采用样本合并计算而非平均各仓 P90。异常长样本 `ubs-comm PR #1092 / trigger #4268` 的约 21.68 天 E2E 及 DT duration 与 Jenkins 抽样记录一致，不能仅因极端值断言采集错误。

发布一致性：UBS manifest 的 11 个文件指纹匹配；Triton JSON 的 canonical 指纹匹配 manifest，371 行/16 列 CSV 与 JSON 逐字段一致。公开数据中 885 个唯一 workflow-attempt、1232 个 job、293 个 NPU job；独立排队复算一致，11 个时间倒置值被排除、8 个 NPU 缺口，108 个排队点。manifest 标记 runs=887 与公开唯一 workflow-attempt=885 的差异仍需结合完整 enriched evidence 解释，不能据此断言完整或遗漏。

定向来源核查覆盖 GitHub 3 个 run/attempt 和 11 个 job、PR #2467/#2513；GitCode PR #1600；Jenkins 4 个任务（含上述长 DT）。可对照的核查字段无差异；PR #2513 仅核实 fork/branch 相符，历史 SHA 关联仍未确认，并非已恢复关联。这是有目的的样本核对，**不证明所有分页、历史 attempt、强推历史或全部 PR 生命周期均完整**。整个窗内批次删除攻击则已证明原质量门禁存在确定缺口，并有修复回归。完整来源独立审计是后续验收，不能用缓存或派生 JSON 自证全量来源。

## 样式与使用体验

桌面配色、排版、侧栏及卡片已有一致基础；这部分无需重做视觉主题。实际障碍集中在任务路径和状态表达：工作台到项目不能正确进入、读取状态被误写成采集失败、窄屏隐藏诊断字段、关注记录重复。本轮优先修复这些可操作问题，见[原桌面](screenshots/live-triton-desktop.jpg)、[原窄屏](screenshots/live-triton-mobile.jpg)、[原工作台](screenshots/live-workbench.jpg)。

完整固定任务导航、UBS 高级统计样本筛选入口、统一详情面板、统一导出、分析/列表/详情身份的完整 URL 恢复尚未接入。新路由当前是已有能力的兼容入口。不能根据单独 router/export/detail helper 测试通过，把它们认定为真实页面已完成。已有 UBS 普通列表搜索不改变 KPI，审查未重复把已经修复的问题作为现存缺陷。

## 架构需求完成情况

| 目标要求 | 当前及本轮后状态 | 后续验收条件 |
|---|---|---|
| 项目目录、稳定身份、统一运行上下文、同一截止与各自窗口 | 公共模型/计划部分具备；shadow 可生成 Matrix，适配器及工件边界本轮修复 | 真实 shadow 采集两社区并与 legacy 窗口/统计对照 |
| 每日 07:30 单一生产入口，等待所有社区后发布 | **未完成**：生产是每日 legacy 全量与五次 Triton 增量；shadow 手动不部署 | 验证后一次切换，移除社区独立定时/部署入口 |
| 部分失败成功社区更新、失败社区可信回退、首次不可用、全失败保留上一版 | **未完成**：本轮 legacy 防护直接阻断失败构建 | 可信旧束校验、故障矩阵与发布状态真实呈现 |
| 完整发布束校验与公开逐文件核验 | legacy 已有真实逐文件核验，本轮加入资格 sidecar；公共 assemble/verify 仍不足 | 公共发布器验证每个实际资源、归属/窗口/版本及完整集合，拒绝伪造 fresh/fallback |
| 核验通过后才提升基线、拒绝旧版本覆盖 | **未完成**：缺权威持久 archive/pointer 和 promotion 事务 | immutable 完整束、核验 receipt、非强推基线提升与旧运行拒绝发布 |
| 自动回滚与恢复后重新核验 | **未完成**：rollback 返回记录，没有执行 Pages 部署 | 真实上一完整束重部署并再次核验，完成后才报告恢复 |
| 主工作流与加载器不依赖社区名，第三社区可配置接入 | Matrix 目录具备；来源实现和特色视图仍有固定仓/分支逻辑 | 第三项目默认真实 adapter、数据归属、路由/导出及公开核验均验收；不能只验证目录 |
| 统一公共交互与项目特色度量 | 基础兼容入口修复，公共任务路径仍部分接入 | 完整产品任务与上下文恢复的浏览器验收 |

## PR 与定时刷新防护

新增 `.github/workflows/pr-gate.yml` 在 PR、merge_group、main push 和手动运行时执行。无 Secrets、无生产采集/部署、contents 只读；所有 PR 均检查，未使用路径排除。最终必需状态名为 **`Dashboard quality gate`**：Python 全量、Node/Chromium、真实适配器/工件契约、actionlint + ShellCheck 四个前置必须全部 success；failed/skipped/cancelled/missing 均阻断，不把“没有运行”当通过。浏览器依赖精确锁定，语法检查器下载校验固定 SHA。

生产发布已有前置数据/工件校验与部署后预期构建指纹对照，本轮增加 UBS 本次采集状态门禁及资格文件对照。新增 `published-health.yml` 在现有计划宽限后只读检查公开指纹、九仓状态和新鲜度；旧仓快照不能被更新索引时间掩盖，失败保留 JSON 诊断及 Actions 失败结论。

这些防护降低功能回归和坏数据发布风险，并暴露延迟/失败，**不能保证外部 API、网络或 GitHub 定时调度永不失败**。定时事件可能延迟或丢弃，长期无活动的公开仓库可能被禁用；见 [GitHub schedule 说明](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule)。当前同组仅保留一个排队运行，仍不满足目标的整轮排队要求。运行失败后应查看失败 step/健康报告、排查来源配额或缺证据，再手动补采；不得绕过门禁部署。部署核验失败当前不会自动恢复。

仓库必需检查已通过 main 保护规则绑定 `Dashboard quality gate`（GitHub Actions app 15368），启用 strict 和管理员约束，要求 PR，禁止强推/删除；依据 [GitHub 保护分支说明](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches)。[PR #1](https://github.com/tianli-Backkom/union_monitor/pull/1) 的首轮检查 [38186105499](https://github.com/tianli-Backkom/union_monitor/actions/runs/38186105499) 五个 job 均 success；读取/设置结果见交付证据。代码中存在 workflow 文件不等于分支保护生效，也不能以离线绿色测试证明今日来源采集成功。

## 验证与证据入口

| 层次 | 可复核内容 |
|---|---|
| 基线公开文件 | [检索时间/URL/哈希](evidence/retrieval.json)、[九仓检索](evidence/retrieval-repositories.json) |
| 独立计算与来源 | [复算](evidence/independent-recompute.json)、[来源抽样对比](evidence/source-sample-comparison.json)、[原删除攻击](evidence/gate-attack.json) |
| 修复同输入回放 | [数据回放](evidence/post-fix-data-replay.json)，保留身份/条数且删除攻击失败 |
| 真实生产历史 | 基线 SHA 的 [legacy run 38139646786](https://github.com/tianli-Backkom/union_monitor/actions/runs/38139646786) build/deploy/verify 成功；不证明统一架构完成 |
| 新防护回归 | [本轮验证记录](evidence/validation.json)、[远端 PR/保护状态](evidence/delivery.json) |
| 公开健康检查 | [生产快照 smoke](evidence/published-health-smoke.json)，只证明该时刻的公开一致性/新鲜度 |

测试按“用户能力→实际入口→故障”追踪：路由/搜索/导出/详情/窄屏由 Chromium 及 Node 运行测试保护；样本资格/覆盖/时间与 sidecar 由 Triton Python/Node 测试保护；采集状态/真实 adapter/错归属/缺报告/错指纹由 Python 契约测试保护；CI 失败传播、日程和文档由 workflow/health/README 测试保护。保留旧审计冻结文件作为历史证据，不重写历史测试结论。本轮只提交任务文件，原工作目录的三份未提交日志未纳入。
