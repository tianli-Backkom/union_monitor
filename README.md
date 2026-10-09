# 统一工程监控看板（openEuler UBS × Triton-Ascend）

双域统一工程监控看板：openEuler UBS 域覆盖 ubs-engine、ubs-comm、ubs-virt、ubs-io、ubs-mem、OmniStateStore、ham、ubturbo、ubs-atomic 九个仓库的 PR 工程效率；Triton-Ascend 域采集 [triton-lang/triton-ascend](https://github.com/triton-lang/triton-ascend) 最近 72 小时的 PR 门禁任务，监控门禁效率。两域共用一个明亮风格的侧边栏界面（openEuler UBS 与 Triton-Ascend 两组导航），Python 标准库采集程序 + SQLite + 无外部依赖的网页，由 GitHub Actions 每日自动采集、验证并发布。

## 在线地址

合并看板 Pages 地址（待部署后填写）：`https://<user>.github.io/<repo>/`

## 看板内容与操作

侧边栏分两组导航：openEuler UBS（九仓效率总览 `#ubs`、单仓页 `#ubs/repo/NAME`、数据质量、统计口径）与 Triton-Ascend（门禁效率趋势 `#triton`）。

### openEuler UBS 组

- **跨仓总览**：默认首页展示九仓对比、跨仓指标、PR 状态筛选、采集时间与状态；点击仓库进入单仓页。跨仓指标直接汇聚入选 PR 的代表值，不平均各仓均值或 P90。无匹配 PR 的仓库仍保留，未知耗时不补零。首页同时展示「等待后失败的 PR」与最长 E2E 等跨仓事实列表（口径见「计算规则」）。
- **PR 工程效率**：合并总览与明细，顶部按 PR 代表值展示 E2E、x86、ARM、DT 平均/P90及有效 PR 样本数，下方展示单值耗时和代表 trigger。仓库切换器与返回总览支持跨仓浏览。旧 `#overview`、`#prs` 链接自动进入 ubs-engine 单仓页；`#repositories` 自动进入跨仓首页。
- **筛选与排序**：按状态、搜索、完整性选择 PR，代表批次保持固定；支持最新创建、代表 E2E 降序、批次数降序及任务排队/执行/总耗时切换。
- **PR 下钻**：始终显示全部提交、重跑、批次与任务，代表批次标注“用于 PR 效率汇总”并默认展开（位于失配组时同样标注），不展示 PR 平均/P90。未能归入已知事件的批次进入“关联未知/失配”组并注明原因（event_id 为空或不在事件列表），不伪造事件；批次 CSV 始终包含同一完整集合，不因分组丢行。
- **数据质量**：未匹配事件、无门禁 PR、未完成或关联不完整批次及采集异常。取消但已结束的批次属于失败体验数据，不是数据质量问题。耗时未知显示空值，不补零。
- **统计口径**：完整定义与本地更新命令。

统计基于原始毫秒；页面主单位是分钟，悬浮可查看秒或毫秒。仓库汇总 CSV 包含仓库采集状态、覆盖率和各项汇总；PR 与批次 CSV 均包含仓库标识。PR 导出包含代表 trigger 编号、链接及 E2E、三类任务全部三种耗时单值，单位毫秒；批次导出保留全部明细并标记代表批次。CSV 对公式前缀转义。本地服务将文件保存至 `web/exports/`，GitHub Pages 使用浏览器直接下载。

### Triton-Ascend 组

- **E2E 时长趋势**：每个点代表一次 PR 提交或手动重跑触发的 E2E，可按全部、耗时偏长、失败、执行中筛选。
- **NPU Job 最长排队时长趋势**：每个点代表一次包含 NPU Job 的 E2E，纵轴取其子 NPU Job 中最长排队时长。
- **所选时间范围的平均值、P50、P90 和有效样本数**，随筛选实时更新。
- **合入分支、状态和时间范围联动筛选**：全局筛选同步更新全部指标、图表和列表。
- **时间范围联动**：两张趋势图共用一个时间导航器，可拖拽整体窗口或左右边界，也可键盘操作：Tab 依次聚焦整体窗口/起点/终点滑块，方向键移动窗口或调整对应边界，Home/End 到达允许边界；三个滑块带名称与 aria 最小/最大/当前值及可读时间描述并随操作同步，指针、触屏与键盘采用同一时间约束（不越过采集窗、至少保留 30 分钟选区，采集窗更短时以可用窗为限），重绘不丢失可见焦点；并提供 6/12/24/48/72 小时快捷档。
- **PR、GitHub Actions、重点 NPU Job 的直达链接**，由散点悬浮/固定卡片承载；散点可键盘访问：Tab 聚焦散点并以 aria 标签报出批次身份，Enter/Space 固定详情卡片，卡内链接可继续 Tab 访问，Esc 或关闭按钮退出并把焦点返回原散点；固定卡片不遮住发起散点（空间不足时上翻/左移并限制卡片高度，卡内滚动），悬停与点击固定交互保留。
- **关注列表**：需要关注的 PR 按耗时偏长、执行中、失败归类，支持按 PR 编号或标题搜索及查看全部批次。每个批次行可键盘展开与收起：Tab 到达展开按钮，Enter/Space 切换，aria-expanded 与明细可见性同步，重叠分组中同一批次的行互不影响；展开后 PR/Actions/job 链接可继续键盘访问，收起的明细不进入 Tab 序；筛选或重绘移除当前行时焦点回到同行的展开按钮或搜索框。分组策略由当前页级范围 G 的有效完成样本数决定：少于 10 个展示「耗时最长」前 5，否则使用 G 的 P90 偏长组；搜索只在各组内过滤记录，不改变策略、阈值与组名，提示标明同一分母；三组之间可能有批次重叠，组计数之和不是唯一批次数。数据边界（使用近似起点的批次数、存在明细或关联缺口的批次数）在页面明示。

### 统一交互

- 旧链接哈希自动重定向：`#repositories` 进入跨仓首页 `#ubs`，`#overview`、`#prs` 进入 ubs-engine 单仓页。
- 统一 CSV 导出：UBS 的仓库汇总、PR、批次导出与 Triton 的批次明细导出使用一致的导出入口，语义见上文各组说明。
- 「重新加载快照」一次刷新两域数据。窄屏（含 390px 手机）下顶栏自动换行增高：面包屑与采集时间可换行，动作按钮保持单行完整、不裁切、不与时间文字重叠。

## 本地运行与更新

在 PowerShell 中运行：

```powershell
cd D:\ubs_core_monitor
python serve.py --port 8765
```

打开 http://127.0.0.1:8765 。服务仅监听本机，按 Ctrl+C 停止。如果服务已启动，直接打开地址即可。

### openEuler UBS 采集

统一截止时间刷新全部九仓最近 30 天数据：

```powershell
python -X utf8 collect.py --all --days 30
```

单独更新使用 `python -X utf8 collect.py --repo ubs-comm --days 30`；不指定 `--repo` 或 `--all` 时保持只更新 ubs-engine。单仓更新不会覆盖其他仓库。

采集完成后，在看板点击“重新加载快照”。默认 4 个并发请求，共享约 10 次/秒的限速；失败最多重试 3 次。PR 列表、评论、操作日志和 Jenkins 构建索引重新查询；已结束构建的日志和事件元数据复用缓存。`--refresh` 强制更新历史缓存。本地仍由用户手动更新，线上由 GitHub Actions 定时更新。

指定滚动区间截止点：

```powershell
python -X utf8 collect.py --days 30 --until "2026-09-09T21:58:38.753+08:00"
```

截止点控制 PR 创建时间及门禁事件时间；PR 状态仍为本次从平台读取的状态，不是历史状态重建。无时区的截止时间按上海时间解释。

使用同一截止点和 `--offline` 可仅从缓存重算，验证幂等性或调整计算逻辑。`--limit N` 仅用于诊断抽样，会在看板显示显著的非全量提示。

离线重算当前已交付快照：

```powershell
$snapshotIndex = Get-Content data/repositories.json -Raw | ConvertFrom-Json
$cutoff = [DateTimeOffset]::FromUnixTimeMilliseconds($snapshotIndex.end_ms).ToString("o")
python -X utf8 collect.py --all --days 30 --until $cutoff --offline
```

### Triton-Ascend 采集

```powershell
$env:GH_TOKEN = '<GitHub Token>' # 可选；建议设置以提高 API 配额
python -X utf8 -m triton.dashboard --hours 72
```

仅使用已保存证据重新生成：

```powershell
python -X utf8 -m triton.dashboard --from-evidence
```

`--as-of` 指定采集窗口截止时间（默认当前时刻），并作为执行中批次已观测时长的参照；`--refresh-focus` 从已保存的 run 页面抓取重点 A3/A5 任务耗时。采集证据保存在 `evidence/triton/`，看板数据输出到 `web/data/triton.json`、`web/data/triton-batches.csv` 与 `web/data/triton-manifest.json`。

### 开发数据引导

```powershell
python scripts/devdata.py
```

从两个线上站点拉取真实已发布数据填充本地 `web/data/`；`--offline` 改用 `tests/fixtures/minimal/` 中的最小 fixtures。

## 数据与接口

### openEuler UBS

| 位置 | 用途 |
|---|---|
| `collect.py` | GitCode/Jenkins 只读采集、关联、快照生成 |
| `metrics.py` | 不依赖网络的统计与状态计算 |
| `data/efficiency.sqlite` | PR、事件、批次、子任务、元数据表 |
| `data/raw/*.json` | 按来源 URL 哈希缓存的响应，带抓取时间 |
| `repositories.json` | 九仓标识与 master 分支配置 |
| `repository_store.py` | 仓库隔离持久化、历史迁移、原子发布 |
| `data/repos/NAME.json`、`web/data/repos/NAME.json` | 各仓相同的完整派生快照 |
| `data/repositories.json`、`web/data/repositories.json` | 仓库索引、统一范围、采集状态与快照路径 |
| `data/snapshot.json`、`web/data/snapshot.json` | ubs-engine 兼容快照 |
| `web/core.js` | 可独立测试的前端筛选与统计 |
| `validate.py`、`validate_multi.py`、`source_coverage.py` | 原始时间、跨仓隔离、代表值、SQLite 和前端算法独立审计；source_audit 按类别声明原始来源覆盖（适用/已验证一致/派生自洽/差异/缺证据计数与缺失身份清单），queue/total 由原始 waiting/blocked/buildable 分项之和独立核验（分项缺失时 queue 与 total 保持未知不补 0）；sections 分项状态（派生一致性/源时间/排队分项/发布一致性 N/A 及理由）推导 overall_status 并与退出码一致，审计异常先写失败报告（错误与受影响范围）再重抛 |
| `validate_bundle.py`、`web/data/ubs-manifest.json` | 发布与缓存共享前的 UBS 快照束校验：索引↔快照归属、纳入跨仓的 success/partial 快照时间范围、仓根镜像一致性与工件指纹 |

SQLite 的 PR 与事件主键包含仓库标识，批次按完整 Jenkins URL 唯一；任务记录复用完整 URL。首次迁移会在 `data/` 自动保留 `*-before-multi-*.sqlite` 备份，将旧数据归入 ubs-engine。

各仓 trigger 与任务映射从该仓 PR 门禁报告发现，并经 Jenkins 只读接口核验；核验依据保存在快照 `meta.job_mapping`。无法发现或确认的任务明确记录为缺失或异常，不借用别仓映射。

批量采集统一截止时间并隔离失败。失败仓保留上次成功快照，首次失败显示未获取数据；旧快照范围与索引当前范围不一致时不纳入跨仓汇总。采集失败与成功采集零 PR 明确区分。单仓更新时间范围变化后，其他仓库可能因范围不同被排除；使用同一 `--until` 更新或重新 `--all` 恢复统一范围。

使用 GitCode 官方 API v5 的 `pulls`、`comments` 和 `operate_logs`。PR 列表遍历全部分页，再按创建时间和 master 过滤；评论和操作日志完整分页。门禁来源取机器人报告与 Jenkins trigger 历史索引的并集，避免仅依赖最后一次检查。

Jenkins 构建主键为完整任务 URL（含 build number）。从 trigger 控制台发现下游，结合 PR 报告交叉检查，再以子任务 `upstreamBuild`、`upstreamProject` 验证父子关系。GitCode 和 Jenkins 当前公开接口可直接读取；无需复制浏览器 Cookie 或登录凭证。若未来接口需要认证，采集失败会明确标记，不生成虚构结果。

环境信息接口在内存中提取允许的事件字段后才写入缓存：事件类型、请求时间、PR ID、目标分支、重跑评论 ID。其他环境变量不落盘、不进入网页。

多仓索引 schema_version=3；每仓派生快照保留单仓结构，PR 的 `metrics` 保存代表批次 URL、编号、E2E 毫秒和三类任务的单值耗时；SQLite PR payload 保存同一结构。

### Triton-Ascend

| 位置 | 用途 |
|---|---|
| `triton/dashboard.py` | GitHub Actions 只读采集、按 PR head SHA 聚合批次、生成看板数据 |
| `triton/quality.py` | 发布前质量校验：Jobs 分页完整性、NPU 识别覆盖、已完成任务时间戳、批次最大排队时长、工件一致性 |
| `triton/pr_identity.py` | Fork PR 与 workflow run 的可靠关联 |
| `triton/verify_deployment.py` | 发布后逐一校验公开数据文件（Triton /data/triton.json、UBS 索引与全部引用快照、两份 manifest）与本次构建清单的 SHA-256/JSON 指纹，最多重试 8 次 |
| `evidence/triton/` | 采集证据：run/job/PR 页面缓存、PR 关联依据、质量报告 |
| `evidence/triton/pr-associations/` | PR 关联依据 |
| `evidence/triton/quality-report.json` | 质量校验结果（失败与警告） |
| `web/data/triton.json` | 看板所需派生数据 |
| `web/data/triton-batches.csv` | 批次明细 CSV |
| `web/data/triton-manifest.json` | 构建清单与 SHA-256 校验值 |

## 计算规则

### openEuler UBS

- 每个 trigger 是一个独立批次；提交次数为创建 PR 加推送事件次数，重跑另列。强制推送不会覆盖先前批次。
- 创建 PR 起点取 `created_at`；重跑以评论 ID 精确关联；推送须 PR ID、事件类型与唯一平台推送日志共同匹配，日志时间与 webhook 时间差不超过 5 秒。无法唯一匹配时 E2E 留空，保留独立 Jenkins 跨度。
- SHA 来自平台操作日志。一次推送包含多个 commit 时保留 `shas` 列表，不猜测 head SHA；未确认的 SHA 不影响已经核验的请求时间。
- 全批结束时间取 trigger 与全部子任务结束时间的最大值。成功必须子任务全部成功，不能依据 trigger 自身 SUCCESS。
- 已结束且可确认起止时间的成功、失败和取消批次均纳入 E2E，反映开发者从提交到门禁停止的真实等待；执行中、数据不完整和缺失请求时间的批次不纳入。每个 PR 选择 E2E 最长的可测量终态批次；并列取 trigger 编号较大者。任务耗时全部取自该代表批次，不从其他批次补取。缺少任务或同类任务关联不唯一时留空。无有效代表批次的 PR 仍计入 PR 数。
- 排队 = `waitingTimeMillis + blockedTimeMillis + buildableTimeMillis`；执行 = `duration`；总计 = 排队 + 执行；缺少任何排队分项时排队和总计为空。
- P90 使用 `(n−1)×0.9` 位置的线性插值，与 Excel `PERCENTILE.INC` 一致。单仓与跨仓指标均使用每个 PR 的代表值，每项最多一个样本。趋势按 PR 创建日期聚合，覆盖率为有代表批次的 PR 数 / 当前 PR 数。筛选只选择 PR，不改变代表批次。

#### 开发者等待与触发方式（UBS）

首页“等待后失败的 PR”取每个 PR 有明确 E2E 的最长失败批次（含中止），按时长降序展示前 8 条；后续成功不抹去历史失败。此事实列表不改变效率汇总使用的代表批次，也不推断失败原因。执行中或缺失起止时间不伪造终态耗时。

PR 列表、详情和 CSV 区分创建、推送和重跑的平台请求次数，另列门禁执行批次数。请求按事件 ID 去重；未关联门禁的请求和来源未知的批次明确提示，采集不完整时次数可能低估。单仓可筛选有重跑请求或推送提交的 PR，详情保留其全部批次。重跑次数不用于判断偶现失败或开发习惯；原因需要结合 SHA、任务结果和日志核验。

### Triton-Ascend

- 批次按 PR head SHA 聚合：一次推送的提交是 E2E 的身份单位，辅助 workflow 即使更晚启动也归入同一 head SHA，不产生额外数据点；手动重跑单独成批。
- 重跑按 run 与 attempt 编号独立成批并保留历史：同一 run 的 attempt 1 归入初次提交批次，attempt 2 起各自独立，重复采集同一 attempt 不重复计数；采集发现窗口向前回溯 14 天，只要本次 attempt 起点落在展示窗口内即被识别（原 run 创建在窗口外的重跑不遗漏），完全在窗口外的运行仅作关联证据，不计入当前窗口批次。重跑 E2E 从本次 attempt 起点计算，不沿用原 run 创建时间。
- **E2E 口径**：E2E 从提交事件到该批次最后一项自动检查结束，包含排队与依赖等待；并行任务不相加。
- **起点来源**：优先使用本次触发事件；无法恢复精确触发时，重跑使用本次 attempt 开始时间、初次提交使用最早 workflow 创建时间，一律标记 approximate 并以 start_source 注明来源，悬浮卡片、批次详情与 CSV 使用同一口径；无本次起点证据时 E2E 留空并在缺口中明示，不从原 run 创建时间或时间接近猜测。页面数据边界显示使用近似起点的批次数。
- **展示规则**：成功和失败批次参与趋势；取消与运行中仅展示已观测耗时。
- **有效耗时口径**：纳入计数、平均、分位数、耗时阈值与小样本策略的耗时必须是有限且非负的原始数值；缺失、空串、数字字符串、NaN、无穷或负值不按 0 计入。真实 0 是合法值，与无值在展示、图表和 CSV 中可区分；无有效耗时的点不绘制在 0 位置。
- **关注分组与小样本策略**：关注列表先按当前页级范围 G 及其有效完成样本数确定分组，再以搜索过滤各组：G 有效完成样本少于 10 个时展示「耗时最长」前 5 批次，否则使用 G 的 P90 偏长组；搜索不改变策略或阈值，组名与提示依据同一 G 样本分母。失败与偏长组可有批次重叠，组计数之和不是唯一批次数；「查看全部批次」与 CSV 导出均为 G 经搜索后的完整记录集合，不受前 5 或关注分组约束。

#### 数据质量保护（Triton）

每次生成页面前，`triton/quality.py` 校验 Jobs 分页完整性、NPU 识别覆盖、已完成任务时间戳及批次最大排队时长。校验失败写入 `evidence/triton/quality-report.json` 并终止发布，保留上一份已发布页面。合法的零 NPU 样本不会被误判为失败。

workflow 与批次时间过同一门禁：已完成 workflow 的起止缺失、不可解析、倒置（结束早于起点）或完成时间超出采集参照（as_of）都会明确报错并阻断发布；倒置跨度不会截成 0 秒，无合法完成时间的批次不作为完成样本（记录警告并排除），运行中批次只报告起点到 as_of 的已观测跨度，起点与参照可追溯。

GitHub 响应契约同样过门禁：workflow_runs、jobs 等列表字段缺失、为 null 或非数组，分页间重复记录，或声明的 total_count 与实得记录数不符时，采集立即失败并在错误中注明来源接口，不会被当作合法零数据发布；真正为空的列表仍表示零数据。契约失败本次不发布，上一份有效页面保持，错误信息不含任何凭证。

GitHub 源时间戳倒置的任务显式标记异常，相关批次不参与排队统计，并写入质量报告 warnings；不再将负值截成零。仍排队、跳过及取消前未启动的任务允许没有最终排队值。

每次构建在写出 `triton.json`、`triton-batches.csv`、manifest 与证据副本后立即运行跨文件一致性门禁：`triton.quality.verify_artifacts` 交叉校验四者的批次身份、统计范围与采集时间，不一致则本次运行失败、不上传当前工件。部署后两个发布流程的 verify job 运行 `python -X utf8 -m triton.verify_deployment <site-url>`，以本次构建的两份 manifest 为基准逐一校验公开的 Triton /data/triton.json、UBS 索引与全部引用快照及两份 manifest 本身（SHA-256/稳定 JSON 指纹），最多重试 8 次。成功在运行摘要记录运行 ID、URL、校验时刻与指纹；公开 URL 仍返回旧数据或篡改数据时，重试耗尽后运行失败并在摘要指出不一致文件；此检查发生在部署后，不自动回滚。

页面每分钟检查数据新鲜度。按北京时间 08:00、13:00、18:00、20:00 的计划及 90 分钟采集发布宽限期显示更新延迟提醒。Actions 失败的外部邮件通知由仓库订阅者的 GitHub 通知设置控制，本项目不配置邮件收件人。

#### PR 关联证据（Triton）

Fork PR 的 workflow `pull_requests` 和 commit 关联接口可能同时返回空数组。采集器优先使用 run 显式 PR 关联；回退以来源仓库、分支、真实 head SHA 或 PR 提交历史校验候选，查询包括已关闭 PR，并完整分页和缓存。PR 编号、标题、链接及目标分支均从 PR 元数据获取，不以运行标题或时间接近猜测关联，也不再按最近 run 覆盖 `pull_request_target` 的 SHA。

关联依据写入 `evidence/triton/pr-associations/`。无法唯一关联或 API 查询失败会保存 `pr-association-errors.json`，阻止本次发布；质量检查同时验证关联证据及聚合前后 PR/SHA 一致性。未知运行按 run ID 与 attempt 隔离，避免相同 SHA 被误并。

## 自动发布

- **每日全量**（[pages.yml](.github/workflows/pages.yml)，`Collect and deploy dashboard`）：北京时间 07:30（UTC 23:30）依次恢复共享 UBS 快照缓存（`ubs-snapshots-v1`，与增量流程路径、顺序和键完全一致）与每日采集缓存（`ubs-collection-v1`，含原始响应、SQLite 与 Triton 证据）、采集九仓最近 30 天的 master PR、采集 Triton 最近 72 小时门禁数据、运行 Python 和 Node 测试、执行真实数据审计，再上传 `web/` 并部署 Pages，随后以本次构建的两份 manifest 校验公开数据指纹。失败保留上一版。计划任务可能因 GitHub 平台负载延迟启动。
- **Triton 增量**（[triton-refresh.yml](.github/workflows/triton-refresh.yml)）：北京时间 08:00、13:00、18:00、20:00 仅重新采集 Triton 最近 72 小时数据并发布。UBS 数据从与每日流程完全一致的版本化共享快照缓存（`ubs-snapshots-v1`）恢复；缓存缺失时通过 `SITE_FALLBACK_URL`（默认旧 UBS 线上地址，可修改）逐文件回退拉取并补齐仓根镜像，日志逐文件标记命中、回退或镜像来源；UBS 索引仍缺失则不部署。两流程上传前都运行 `validate_bundle.py`：校验索引与被引用单仓快照归属一致、纳入跨仓的 success/partial 快照时间范围与索引窗口一致（失败仓保留的过期快照合法，改标成功即被阻断）、仓根镜像不混版本，并与 `web/data/ubs-manifest.json` 记录的工件指纹比对，旧索引配新快照（或相反）会被阻断；坏 JSON、空文件、缺失 `repositories` 结构或被引用快照缺失、下载失败同样阻断，不能只凭索引非空上传。pending 与首次失败且无快照的仓库合法，页面显示未获取而非空成功数据；缓存命中与站点回退两条恢复路径共用同一完整性检查，错误报告注明具体缺失引用与恢复来源。恢复或校验失败的工作流不保存共享缓存、不上传部署——重试恢复上一份有效缓存，线上保持上一版有效页面。部署后与每日流程同样运行公开数据指纹校验。两工作流共用 concurrency group `pages`，增量运行不会取消正在进行的每日全量构建。
- 两个工作流均支持在 Actions 页面手动运行（`workflow_dispatch`）。

原始 API 缓存、SQLite、历史 CSV 和备份不会包含在 Pages artifact 或 Git 提交中；线上只公开看板所需的派生 JSON 与数据文件。

若 GitHub-hosted runner 无法访问 GitCode、Jenkins 或 GitHub API，先在 Actions 日志确认是 401/403、网络超时还是任务路径变化。UBS 单仓失败会显示采集失败或过期快照；采集进程、测试、审计或 Triton 质量校验整体失败时不会部署并覆盖上一版 Pages。可在网络恢复后通过 `workflow_dispatch` 重跑。

## 验证

```
python -m unittest discover -s tests -v
node --test tests/*.test.cjs
python validate.py
python validate_bundle.py
python -X utf8 -m triton.verify_deployment <site-url> --triton-manifest web/data/triton-manifest.json --ubs-manifest web/data/ubs-manifest.json
```

浏览器已人工验证：PR 状态筛选、搜索、多次提交和重跑下钻、任务时间线；Triton 时间导航器键盘路径（Tab 依次聚焦三个滑块、方向键与 Home/End、aria 值随操作同步、重绘后焦点保持、指针与键盘同一约束）、批次行键盘展开（Tab 到达展开按钮、Enter/Space 切换、aria-expanded 与可见性同步、展开后明细链接可键盘访问且收起时不入 Tab 序、筛选移除当前行时焦点回落）与趋势散点键盘固定（Tab 聚焦散点并报出批次身份、Enter/Space 固定详情卡片、卡内链接可 Tab 访问、Esc 或关闭按钮退出且焦点返回原散点、固定卡片不遮住发起散点、悬停与点击固定保留）与手机顶栏完整显示（390×844 五页：重新加载动作完整位于顶栏边界内、单行不折叠、与采集时间不重叠、无整页横向溢出，点击仍触发同一重载）经真实浏览器核验。多仓审计结果见 `data/validation-multi.json`，包含每仓采集状态、PR 数及跨仓有效样本；`source_audit` 段按类别声明原始来源覆盖率（已验证一致 + 派生自洽 + 已发现差异 + 缺证据 = 适用总数，附缺失与差异身份清单及任务 URL 与字段），raw 为空即未验证、部分补齐保持缺失清单、无适用对象记 N/A 及原因；queue/total 由原始 waiting/blocked/buildable 分项独立重算核验，分项缺失或非法时 queue 与 total 保持未知且不补 0（已知 duration 保留），篡改分项即使派生总和自洽也会被点名；来源覆盖不足或发现差异时审计以非零退出，不以派生一致性冒充来源准确性。报告 `sections` 按分项给出状态与理由：派生一致性（报告存在即全部派生断言通过）、源时间、排队分项（已验证/未验证/部分/差异/N/A）与发布一致性（N/A，注明归属 validate_bundle 与 verify_deployment，本审计不重复校验）；`overall_status` 从分项推导，verified/not_applicable 才退出 0，与 checks_passed 和 CI 结果一致；审计中途异常先写入失败报告（overall_status=failed、错误与受影响范围）再原样重抛，不残留上一轮的通过声明。Triton 审计冻结快照（`tests/fixtures/triton-audit-freeze.json`：38 PR/66 批/65 完成样本/48 NPU 排队点/9 条 NPU 时间倒置）由测试独立重算 summary、逐批 NPU 派生与两图选区统计并锁定，统计契约不随新数据漂移。

## 接口依据与致谢

- openEuler UBS：门禁与 PR 数据来自 GitCode 官方 API v5 的 `pulls`、`comments`、`operate_logs` 及 Jenkins 只读接口。接口依据：[GitCode PR API 文档](https://docs.gitcode.com/v1-docs/docs/openapi/repos/pulls/)。
- Triton-Ascend：门禁数据来自 GitHub Actions API 的 workflow runs、jobs 与 PR 关联只读接口；`GH_TOKEN` 可选，建议设置以提高 API 配额。
