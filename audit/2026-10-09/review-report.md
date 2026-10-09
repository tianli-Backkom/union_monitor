# UBS × Triton 合并看板审查报告

**结论：需要修订（Needs revision）。** 本地合并版的主要视图与现有派生数据已完成审查，但交互逻辑未达到本轮确认的验收预期。发现 19 组问题/风险（P1 8、P2 10、P3 1）；没有修改业务代码、正式快照或部署。

**完整性：已完成当前目录可支持的视图、控件、派生数据及静态链路审查；原始来源与真实部署历史验证为 Partial。** 长表重复行、相同模板的重复视觉内容采用抽查，未穷举全部筛选组合。

## 基准与证据

- 验收按README及用户确认：时间/分支全页联动、图状态局部、搜索仅列表、选区P90、按当前筛选导出、两域会话状态分别保留。
- Chrome实际运行桌面1440×1000、平板1024×768、手机390×844；Edge补做挂载、时间筛选与跨域导航。触屏拖动和触屏卡片通过；键盘关键路径有缺陷。
- 独立浏览器和请求拦截用于故障/边界；本地POST导出被拦截保存到审查目录，Pages Blob下载使用本地资产模拟Pages origin；没有向公开站点写入。
- [覆盖矩阵](D:/ubs_core_monitor/audit/2026-10-09/coverage-matrix.md)、[全量检查结果](D:/ubs_core_monitor/audit/2026-10-09/evidence/all-checks.json)、[数据重算](D:/ubs_core_monitor/audit/2026-10-09/evidence/data-audit.json)、[旧站能力对照](D:/ubs_core_monitor/audit/2026-10-09/evidence/baseline-comparison.md)、[截图总览](D:/ubs_core_monitor/audit/2026-10-09/screenshots/contact-sheet.png)。
- 检查项计数：207通过、29失败、2未验证。检查项不是组件准确率；同一个问题可使多项检查失败。
- 计划阶段现有单测Python79/79、Node34/34通过，当前业务文件保持相同版本；这些测试不覆盖完整DOM交互。

## 数据结论

| 域 | 覆盖 | 结果 |
|---|---|---|
| UBS | 九仓、203 PR、826批次 | 全部代表值、跨仓汇总、批次与任务派生值重算一致；任务样本x86=191、ARM=203、DT=195 |
| Triton | 38 PR、66批、434 workflow、593 job、142 NPU job | summary及E2E/NPU派生重算一致；65完成样本、48排队点 |
| 原始来源 | raw/SQLite/evidence/manifest缺失 | 未验证；内部一致性不能替代源时间、queue三分项或历史attempt正确性 |

UBS已知缺口如实保留：12个请求无trigger、6批无唯一请求、17批不完整、2批运行中、16批取消。Triton全部66批使用近似起点；9条NPU时间倒置记录涉及5批，排队值留空。上述属于已明示的数据边界，不直接当作新缺陷。

## 组件质量与分析稳健性

分母为本次明确盘点的组件、控件或问题单元，不是原始行数；0 / N表示没有观察到剩余缺陷，不表示全部来源已验证。各类别重叠，不能合成准确率。

### 看板用途与质量

| Category | Observed defects | Assessment |
|---|---|---|
| 看板用途与完整性 | 1 / 21 | 21个主要视图均有入口与数据验证；Triton全页时间联动未达标。 |
| 分析表达清晰度 | 3 / 4 | 口径主要定义保留；选区、搜索提示、共享外壳与手机显示存在已复现偏差。 |
| 视觉与交互一致性 | 6 / 8 | Chrome三种宽度截图和Edge关键路径已检查；键盘、手机和跨域状态存在问题。长表重复行采用抽查。 |

### 分析正确性与稳健性

| Category | Observed defects | Assessment |
|---|---|---|
| 来源权威与置信度 | 1 / 2 | 当前提供的是派生快照；原始平台和历史attempt证据缺失。发布配置不能替代真实部署历史验证。 Partial review: 1 scoped item has incomplete or stale evidence (原始来源和历史attempt证据). |
| 数值与计算准确性 | 0 / 13 | 203 PR、826批次及Triton66批派生值全量重算一致；该结论不证明原始来源准确。 |
| 图内数值与说明一致 | 1 / 3 | 正常选区的两图统计与独立重算一致；搜索分组说明有偏差。 |
| 完整来源详情 | 1 / 3 | 正常详情可追溯至原始链接；失配事件合成边界漏批，原始证据未提供。 Partial review: 1 scoped item has incomplete or stale evidence (原始来源和历史attempt证据). |
| 跨组件与导出一致 | 3 / 4 | UBS正常导出通过；Triton过滤/导出、跨域状态和切仓详情存在不一致。 |
| 数据质量保护 | 3 / 14 | 缺值/故障/合成时间边界暴露门禁和发布保护不足。 |
| 结论支持 | N/A | 详见审查报告及覆盖矩阵。 Not applicable: 看板没有提出因果或决策性结论；记录的是实际耗时、状态与样本。 |

## 优先问题与修复清单

### F01 · P1 · Triton时间筛选与偏长阈值使用不同集合

- 位置：`web/triton-view.js:165-176,306-319,396-405,458-491`；证据类型：真实快照/浏览器。
- 复现：选6小时，再点“查看全部批次”与“耗时偏长”。
- 预期：图、汇总、列表应同属选区；阈值取该选区完成批次P90。
- 实际：6小时图1点，汇总/列表66批；选区P90=290秒但偏长图0点（应有1点）。
- 影响：使用者会把整个72小时统计解释为所选时段；异常分类也与选区不符。
- **修复建议：** 建立统一分支+时间集合；顶部、列表及阈值都引用它，局部状态只影响各图。
- 证据检查ID：`T08-6,T08-12,T08-24,T09`，见[覆盖矩阵](D:/ubs_core_monitor/audit/2026-10-09/coverage-matrix.md)。

### F02 · P1 · Triton筛选导出仍输出全量快照

- 位置：`web/triton-view.js:417-431`；证据类型：真实快照/浏览器。
- 复现：选6小时，搜索PR2475，导出批次CSV。
- 预期：导出当前分支、时间及列表搜索后的全部匹配记录。
- 实际：应1行，实际66行；本地与Pages下载均可触发。
- 影响：导出数据与读者选定范围不一致。
- **修复建议：** 导出复用页级分支+时间+搜索集合，排除分页/关注分组限制及图表局部状态。
- 证据检查ID：`T16`，见[覆盖矩阵](D:/ubs_core_monitor/audit/2026-10-09/coverage-matrix.md)。

### F03 · P1 · 返回或重新加载会清空Triton会话状态

- 位置：`web/triton-view.js:37-47,160-163; web/app.js:29,59,82`；证据类型：真实快照/浏览器。
- 复现：选分支、6小时、搜索、失败及全部列表；切UBS再返回，或重新加载。
- 预期：各域分别保留会话内筛选与时间选择。
- 实际：分支清空、时间回72小时、搜索清空、状态回all、列表回关注；reload也重置时间。
- 影响：连续调查中已选上下文丢失；UBS却保留输入，体验不一致。
- **修复建议：** 将状态独立于视图挂载保存；有效新快照下恢复，失效选项明确提示并按新窗口约束。
- 证据检查ID：`T17,A02`，见[覆盖矩阵](D:/ubs_core_monitor/audit/2026-10-09/coverage-matrix.md)。

### F04 · P1 · 旧PR详情在切仓后被导出为新仓库

- 位置：`web/app.js:31-61,72,81`；证据类型：真实快照/浏览器。
- 复现：打开ubs-engine PR1600详情，通过哈希切到ubs-comm，点详情导出。
- 预期：关闭旧详情或保留其原始仓库上下文，CSV归属必须正确。
- 实际：详情仍为PR1600，但首列为openeuler/ubs-comm，文件名也使用新仓库。
- 影响：跨仓同编号场景可能把错误来源用于分析或问题定位。
- **修复建议：** 导航时关闭/清空详情；详情实体同时保存仓库和快照标识，导出使用详情自身上下文。
- 证据检查ID：`U34,U35`，见[覆盖矩阵](D:/ubs_core_monitor/audit/2026-10-09/coverage-matrix.md)。

### F05 · P1 · 连续刷新较旧响应覆盖较新快照

- 位置：`web/app.js:82-83`；证据类型：故障注入/浏览器。
- 复现：两次触发reload，先请求延迟450ms，后请求先返回。
- 预期：最后一次刷新结果胜出。
- 实际：响应顺序2→1，最终collected_at从10月9日回退到10月8日。
- 影响：指标和新鲜度可能回退到旧数据。
- **修复建议：** 增加加载代次或AbortController；只有当前代次可提交数据与渲染状态。
- 证据检查ID：`F04`，见[覆盖矩阵](D:/ubs_core_monitor/audit/2026-10-09/coverage-matrix.md)。

### F06 · P1 · UBS索引失败导致Triton与口径页也不可用

- 位置：`web/app.js:82`；证据类型：故障注入/浏览器。
- 复现：打开#triton，拦截UBS索引为404。
- 预期：单域故障隔离，Triton快照和静态口径仍可访问。
- 实际：全部视图被隐藏，Triton请求甚至不执行。
- 影响：UBS故障扩大成整个合并看板不可用。
- **修复建议：** 两域独立读取/验证并分别呈现错误；静态口径不依赖数据加载成功。
- 证据检查ID：`F01-ubs-index-404`，见[覆盖矩阵](D:/ubs_core_monitor/audit/2026-10-09/coverage-matrix.md)。

### F07 · P1 · 每日与增量缓存路径版本不一致

- 位置：`.github/workflows/pages.yml:32-45; .github/workflows/triton-refresh.yml:36-46,131-139`；证据类型：静态配置已确认/线上影响未验证。
- 复现：对比两流程cache.path，再按官方缓存版本规则核对。
- 预期：能够恢复每日更新后的UBS数据。
- 实际：每日7条路径，增量4条；同key前缀不能跨不同缓存版本命中。
- 影响：增量可能恢复自身旧UBS缓存并重新发布；实际发生次数未读取Actions历史。
- **修复建议：** 统一共享缓存的路径集合与顺序，或单独发布带版本的UBS工件；增加跨日冷热缓存集成验证。
- 证据检查ID：`P01`，见[覆盖矩阵](D:/ubs_core_monitor/audit/2026-10-09/coverage-matrix.md)。

### F08 · P1 · Triton重跑使用原run创建时间且只取当前attempt

- 位置：`triton/dashboard.py:190-209,404-425`；证据类型：合成复现/真实历史影响未验证。
- 复现：输入attempt2：原run00:00创建、本attempt02:00开始、02:05结束。
- 预期：重跑应保留独立身份、可证明的本次起点，并说明近似边界。
- 实际：输出7500秒；本attempt已观测跨度为300秒，quality通过；采集只请求最新attempt jobs。
- 影响：可能把两次运行间隔计为本次耗时，且无法保留此前attempt的完整历史。
- **修复建议：** 保存attempt级证据和历史；优先本次触发事件，否则以可证明的attempt起点近似并标注，不能沿用原run创建时间。300秒是示例已观测跨度，不是已验证的真实提交E2E。
- 证据检查ID：`S01`，见[覆盖矩阵](D:/ubs_core_monitor/audit/2026-10-09/coverage-matrix.md)。

### F09 · P2 · 详情漏掉非空但失配的事件批次

- 位置：`web/app.js:72`；证据类型：合成边界/当前真实数据未触发。
- 复现：令某批次event_id非空且不在PR.events中，打开详情。
- 预期：全部批次仍展示，未知关联单独分组。
- 实际：3批只显示2批；当前826批中这类失配为0。
- 影响：证据不完整时反而隐藏需要调查的记录。
- **修复建议：** 按已渲染批次集合补齐所有剩余批次，失配关联归入明确的未知事件组。
- 证据检查ID：`U37`，见[覆盖矩阵](D:/ubs_core_monitor/audit/2026-10-09/coverage-matrix.md)。

### F10 · P2 · 缺失/空串/负耗时被Triton统计当有效样本

- 位置：`web/triton-core.js:53-76,108-116`；证据类型：合成边界/当前真实数据未触发。
- 复现：传入成功null、失败空串、成功-1秒三条。
- 预期：无效值排除，未知不补零。
- 实际：有效count为3（应0），null和空串被Number转换成0；当前65个完成样本无此异常。
- 影响：异常快照可能污染平均值和分位数。
- **修复建议：** 要求原始值是有限非负number，再参与汇总和少样本判断。
- 证据检查ID：`S04`，见[覆盖矩阵](D:/ubs_core_monitor/audit/2026-10-09/coverage-matrix.md)。

### F11 · P2 · 采集质量门禁放行缺字段或倒置workflow时间

- 位置：`triton/dashboard.py:225,297-313; triton/quality.py:12-63`；证据类型：合成边界。
- 复现：workflow_runs字段缺失，或completed run updated_at早于created_at。
- 预期：缺字段拒绝；倒置时间作为异常排除/阻断发布。
- 实际：缺字段返回合法空列表；倒置耗时截成0，quality仍通过。
- 影响：可能把源异常当合法零数据覆盖旧快照。
- **修复建议：** 验证API必要字段和分页契约；在批次门禁核对起止、状态、观测参照与汇总。
- 证据检查ID：`S02,S03`，见[覆盖矩阵](D:/ubs_core_monitor/audit/2026-10-09/coverage-matrix.md)。

### F12 · P2 · 发布工件完整性和部署后校验未接入

- 位置：`.github/workflows/triton-refresh.yml:90-118; 两流程deploy job; README.md:182`；证据类型：静态配置已确认。
- 复现：检查fallback错误处理、no-deploy guard及deploy后的步骤。
- 预期：引用快照齐全且范围可解释；部署后指纹核对兑现文档。
- 实际：坏索引枚举退出0，单仓下载失败被吞，最后只检查index非空；两个deploy均无verify_deployment。
- 影响：不完整或混合快照可进入部署，旧数据发布不能被承诺的校验发现。
- **修复建议：** 部署前验证JSON/引用/归属/时间范围；上传并核对构建manifest，部署后使用实际/data/triton.json入口校验。
- 证据检查ID：`P02,P03`，见[覆盖矩阵](D:/ubs_core_monitor/audit/2026-10-09/coverage-matrix.md)。

### F13 · P2 · 来源审计允许原始证据覆盖为零

- 位置：`validate.py:40-44,69; validate_multi.py:98-110`；证据类型：静态审计已确认/本地无法完整运行。
- 复现：核对raw存在时才比对的分支及最终checks_passed。
- 预期：结果区分派生一致性与原始来源覆盖。
- 实际：checked可为0仍写checks_passed=True，queue三项也未独立验证；本地原始工件缺失。
- 影响：容易将内部一致性误称为来源准确性。
- **修复建议：** 输出证据覆盖率/缺失清单及分项结果，来源校验不足时不得整体宣称通过。
- 证据检查ID：`P05,D10`，见[覆盖矩阵](D:/ubs_core_monitor/audit/2026-10-09/coverage-matrix.md)。

### F14 · P2 · 搜索后的关注分组说明与实际退化策略矛盾

- 位置：`web/triton-view.js:396-405; web/triton-core.js:108-116`；证据类型：真实快照/浏览器。
- 复现：搜索PR2455后回关注列表。
- 预期：少样本提示与实际组名/策略一致。
- 实际：组名“耗时最长1”，旁注仍写“优先显示超过P90”。
- 影响：用户无法判断列表是异常样本还是少样本中的最长项。
- **修复建议：** 搜索只筛选全局关注集合或说明当前退化策略；组名、阈值和样本说明使用同一上下文。
- 证据检查ID：`A01`，见[覆盖矩阵](D:/ubs_core_monitor/audit/2026-10-09/coverage-matrix.md)。

### F15 · P2 · 键盘不能操作Triton滑块和批次展开入口

- 位置：`web/triton-view.js:92,362-371,405,472-493`；证据类型：浏览器/DOM。
- 复现：使用Tab/方向键/Enter访问时间滑块、散点、批次行。
- 预期：关键交互可聚焦并能通过键盘操作，slider值可读。
- 实际：slider无tabindex及aria值，行是不可聚焦div，仅pointer/click绑定。
- 影响：键盘用户无法完成下钻和时间选择；触屏拖动本身通过。
- **修复建议：** 补可聚焦语义和键盘事件，正确维护范围ARIA值与焦点；散点提供等价列表入口。
- 证据检查ID：`T26,T27`，见[覆盖矩阵](D:/ubs_core_monitor/audit/2026-10-09/coverage-matrix.md)。

### F16 · P2 · 手机顶栏裁切、横轴拥挤及导航缺视觉说明

- 位置：`web/style.css:521-529,557-565; web/triton-view.js:202-205,245-248`；证据类型：截图人工确认/浏览器几何。
- 复现：390×844打开Triton，查看顶栏及两图横轴。
- 预期：动作文字在顶栏内，日期刻度不重叠，图标导航易识别。
- 实际：reload上沿-23.5px/下沿86.5px越过64px顶栏；7个完整时间刻度重叠并裁边；导航font-size:0且无title。
- 影响：小屏读取时间和识别动作受影响；DOM保留导航文字，不等同于屏幕阅读器没有名称。
- **修复建议：** 顶栏小屏换行/收起或图标按钮加标签；刻度数量随宽度调整，端点对齐；导航提供可见说明或tooltip。
- 证据检查ID：`A10,M01,V-mobile-nav-label`，见[覆盖矩阵](D:/ubs_core_monitor/audit/2026-10-09/coverage-matrix.md)。

### F17 · P2 · Triton共享顶栏和仓库链接仍指向UBS

- 位置：`web/index.html:40-41; web/app.js:45-59`；证据类型：真实快照/浏览器。
- 复现：先看UBS总览，再进入Triton。
- 预期：分支、代码仓链接和页脚属于当前域或明确标注为共享信息。
- 实际：顶栏仍master、代码仓链接GitCode UBS；页脚残留9 REPOSITORIES/203 PR。
- 影响：容易误读当前仓库、分支与统计粒度。
- **修复建议：** 按domain更新共享外壳的分支、源链接和页脚；多分支时明确表达。
- 证据检查ID：`A03`，见[覆盖矩阵](D:/ubs_core_monitor/audit/2026-10-09/coverage-matrix.md)。

### F18 · P2 · 仓库选择器替换历史使后退跳过上一仓库

- 位置：`web/app.js:28,83`；证据类型：真实快照/浏览器。
- 复现：总览点击ubs-engine，用选择器切ubs-comm，再后退。
- 预期：浏览器后退逐步返回上一仓库。
- 实际：直接回#ubs，ubs-engine历史已被replaceState覆盖。
- 影响：跨仓比较时后退行为与普通侧栏链接不同。
- **修复建议：** 用户导航用pushState或标准hash跳转，仅旧链接规范化用replaceState，并回归前进/后退。
- 证据检查ID：`A05`，见[覆盖矩阵](D:/ubs_core_monitor/audit/2026-10-09/coverage-matrix.md)。

### F19 · P3 · 最小fixture的P90与实际统计契约不一致

- 位置：`tests/fixtures/minimal/triton.json:225`；证据类型：测试fixture。
- 复现：重算三条完成样本[600,600,900]。
- 预期：线性插值P90=840秒。
- 实际：fixture summary写900秒；真实快照summary重算正确。
- 影响：开发最小数据可能掩盖统计不一致或导致误验收。
- **修复建议：** 更正fixture派生值并验证fixture与当前kind/统计契约。
- 证据检查ID：`S05`，见[覆盖矩阵](D:/ubs_core_monitor/audit/2026-10-09/coverage-matrix.md)。

## 截图与范围限制

![桌面与平板视图总览](D:/ubs_core_monitor/audit/2026-10-09/screenshots/contact-sheet.png)

![手机时间刻度拥挤](D:/ubs_core_monitor/audit/2026-10-09/screenshots/mobile-triton-charts-crop.png)

优先复现截图：[六小时时间窗](D:/ubs_core_monitor/audit/2026-10-09/screenshots/triton-six-hour-mismatch.png)、[切仓旧详情](D:/ubs_core_monitor/audit/2026-10-09/screenshots/ubs-cross-repo-wrong-detail.png)、[索引失败阻断Triton](D:/ubs_core_monitor/audit/2026-10-09/screenshots/failure-ubs-index-blocks-triton.png)、[手机顶栏](D:/ubs_core_monitor/audit/2026-10-09/screenshots/visual-mobile-triton-viewport.png)。

原始平台数据、历史重跑attempt和真实Actions执行历史没有补采；冷/暖缓存与跨日发布的实际结果、实际部署fingerprint以及CI Python3.12/Node22兼容性仍未验证。没有触发采集或部署。静态链路问题与合成缺陷不能证明当前线上数据已经遭受对应影响。

发布风险依据：[Actions缓存版本](https://github.com/actions/cache#cache-version)说明路径参与版本；[Actions并发规则](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)说明默认仅保留一个pending。两流程cancel-in-progress:false保护运行中的任务，但不保证所有排队任务均保留；这项记为运行风险，未计入19组已确认问题。

## 修复与回归顺序

1. 优先统一Triton页级数据集合和状态保存，同时修正筛选导出与P90阈值（F01–F03）。
2. 修正详情归属、刷新代次、两域故障隔离（F04–F06），用本次同样的故障/导航输入回归。
3. 完成缓存/attempt证据/发布完整性与原始来源覆盖保护（F07–F13），补真实工件验证后再判断来源准确性。
4. 修正搜索说明、键盘、小屏及共享外壳/历史导航/fixture（F14–F19）。

修复后的通过标准：所有相关失败检查转为通过，原始证据缺口仍需保留；不得通过删除记录、补零或放宽预期让检查通过。

## 保持原文件与可复现性

58个受保护业务源码、测试、配置及正式数据文件SHA-256复核无变化，见[校验结果](D:/ubs_core_monitor/audit/2026-10-09/evidence/protected-files-after.json)。审查输出全部位于本目录。

审查结果生成于 2026-10-09 14:57:02 Asia/Shanghai。原始来源审计缺口和并发历史影响仍标为未验证。

复现入口：`scripts/ubs-browser.cjs`、`scripts/triton-browser.cjs`、`scripts/additional-browser.cjs`、`scripts/data-audit.py`、`scripts/deployment-audit.py`。浏览器脚本要求本机服务18765和已安装Chrome/Edge，所有写入限定在审查目录；不触发collect或deploy。
