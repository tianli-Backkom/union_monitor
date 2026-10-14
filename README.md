# 统一工程监控看板（openEuler UBS × Triton-Ascend）

查看 PR 门禁耗时、失败批次、排队和来源证据。UBS 覆盖 ubs-engine、ubs-comm、ubs-virt、ubs-io、ubs-mem、OmniStateStore、ham、ubturbo、ubs-atomic 九仓；Triton 采集 [triton-lang/triton-ascend](https://github.com/triton-lang/triton-ascend) 最近 72 小时的 GitHub Actions 门禁。

## 直接使用

- [工作台](https://tianli-backkom.github.io/union_monitor/#workbench)：查看已加载快照和进入项目。
- [UBS 跨仓总览](https://tianli-backkom.github.io/union_monitor/#ubs)：九仓对比 → 单仓 PR → 批次与任务；另有数据质量和统计口径。
- [Triton 看板](https://tianli-backkom.github.io/union_monitor/#triton)：E2E / NPU 排队趋势、关注批次及来源链接。

「重新加载快照」只读取已发布文件，不触发采集。页面使用各快照的原采集时间；读取失败时会提示，并尽可能保留已加载的有效数据。当前工作台未接入统一运行报告、发布版本和跨项目关注聚合，不能用它判断本轮采集成功或“没有关注记录”。

## 本地启动

在仓库根目录运行，开发快照会写入本地数据目录：

```powershell
python -B scripts/devdata.py --offline    # 固定最小 fixture，无需访问源站
python serve.py --port 8765
```

打开 [本地工作台](http://127.0.0.1:8765/#workbench)，Ctrl+C 停止。服务只监听本机并仅公开 `web/`。需要线上已发布快照时运行 `python -B scripts/devdata.py`：默认从 `union_monitor/data/` 读取 UBS 索引、各仓快照和 `triton.json`，不会重新采集 GitCode / GitHub。`--ubs-url BASE`、`--triton-url URL` 可覆盖地址；显式传入旧 Triton `index.html` URL 仍可提取内嵌 JSON。

## 筛选、口径与导出

- **UBS**：列表搜索只定位 PR，不改变 KPI / 趋势；状态、完整性、触发类别筛选会改变统计样本。排序支持代表 E2E、批次数、创建时间；排队 / 执行 / 总计选择切换任务指标列。
- **Triton**：分支和时间范围控制全页分析范围；每张图的状态按钮只改变该图及图内统计。列表搜索只改变列表和导出集合。关注按批次去重，同批次可有多个原因标签。
- **E2E 不跨项目混算**：UBS 每 PR 取最长合格 E2E 的代表批次，并列按 trigger 编号和 URL 决定；x86 / ARM / DT 均取该批次内唯一、关联有效的终态任务。Triton 按提交及重跑 attempt 形成批次，只有成功 / 失败且耗时有限非负、E2E 关联资格有效的批次进入终态分位数；未关联 PR 的观测记录仍保留，NPU 资格独立判断。
- UBS 排队 = `waiting + blocked + buildable`，总计 = 排队 + 执行；缺失分项留空。取消处理保留各项目口径，不能统一当失败或统一排除。空值不补零，合法 0 保留；P90 使用 `(n−1)×0.9` 线性插值，是样本分位数，不是 SLA。
- **CSV 仍保留各项目原字段与单位**（UBS 毫秒、Triton 秒），分页 / 折叠不截断导出。Triton 另下载 `triton-qualifications-v1.json` 说明每批次资格，这不是完整统一导出格式。本地 CSV 保存到 `web/exports/`，资格 JSON 由浏览器下载；Pages 上两者均由浏览器下载。

## 生产采集与迁移状态

当前生产继续使用两条流程，均可在 Actions 手动运行：

| 流程 | 北京时间计划启动 | 范围 |
|---|---|---|
| [每日采集与发布](.github/workflows/pages.yml) | 07:30 | UBS 九仓最近 30 天 + Triton 最近 72 小时 |
| [Triton 增量](.github/workflows/triton-refresh.yml) | 08:00/12:00/16:00/18:00/20:00 | 仅重采 Triton，复用经校验的 UBS 快照 |

这是启动日程，不是更新时间保证。两流程共用 `pages` 并发组且 `cancel-in-progress: false`，保护正在运行的构建；排队中的运行遵循平台默认替换规则（queue: single，同组仅保留最新排队运行）。构建门禁失败会阻止该构建进入部署；部署后的验证失败不会自动回滚。

[统一 shadow 流程](.github/workflows/unified-shadow.yml) 仅手动生成候选工件，不部署 Pages。完整任务导航、统一数据版本发布、全站可信回退及自动回滚尚未上线；当前新路由提供已有项目能力的兼容入口，未提供的任务会明确说明。目标态与迁移约束见 [产品方案](docs/design/2026-10-10-unified-dashboard-product.md)、[技术方案](docs/design/2026-10-10-unified-dashboard-architecture.md)；本轮门禁工作见 [实施计划](docs/superpowers/plans/2026-10-11-adversarial-audit-and-pr-gates.md)。

## 本地验证与 PR 门禁

审查整改及后续实施统一按 [38 项需求与自动化验收规格](docs/requirements/2026-10-12-unified-dashboard-audit-requirements.md) 追踪；每项包含描述、输入/操作/断言、验收条件及已有/待补测试，规格完整不代表业务验收通过。

目标运行时：**Python 3.12 / Node 22**。网页运行本身不依赖 Node 包；浏览器测试使用锁定的 Playwright / Chromium。[PR 工作流](.github/workflows/pr-gate.yml) 汇总 Python、前端、采集契约和工作流语法检查，最终检查名为 `Dashboard quality gate`。

```powershell
python -m pip install PyYAML==6.0.3
python -B scripts/devdata.py --offline
python -B -m unittest discover -s tests -v
node --test tests/*.test.cjs
npm ci --ignore-scripts
npx playwright install --with-deps chromium
npm run test:browser
```

Chromium 测试自动启动本地服务，使用确定性 fixture，覆盖路由、列表搜索、详情 / 浮层清理、重载失败、导出和 390px 布局。失败证据位于 `test-results/`；离线 fixture 通过不等于线上来源数据完整。

公开站点健康检查：

```powershell
python -B -m scripts.published_health
```

[健康工作流](.github/workflows/published-health.yml) 只验证公开文件一致性、仓库状态和按生产日程计算的新鲜度，输出 `test-results/published-health.json`；不补采、不部署、不回滚，也不证明发布来源可信或源站数据全量完整。网络、采集、部署延迟都可能使检查失败。

既有数据与需求审计（需先准备相应快照 / 证据）：

```powershell
python validate.py
python validate_bundle.py
python -X utf8 scripts/verify_interactions.py
python -X utf8 scripts/verify_freshness.py
python -X utf8 scripts/verify_acceptance.py --delivering REQ-051
python -X utf8 scripts/verify_requirements_doc.py
python -X utf8 -m triton.verify_deployment https://tianli-backkom.github.io/union_monitor/ --triton-manifest web/data/triton-manifest.json --ubs-manifest web/data/ubs-manifest.json
```

最后一条使用本地预期构建 manifest 对照线上文件；与仅使用线上 manifest 的健康检查不同。

## 手动采集与代码入口

```powershell
python -X utf8 collect.py --all --days 30           # UBS 九仓
python -X utf8 collect.py --repo ubs-comm --days 30 # UBS 单仓
python -X utf8 -m triton.dashboard --hours 72       # Triton，GH_TOKEN 用于 API 配额和强推历史查询
```

UBS 的 `--offline` 从缓存重算，`--limit N` 用于诊断抽样；Triton 的 `--from-evidence` 从已存证据重生成。原始缓存、SQLite 和历史导出不公开到 Pages。

Triton 的历史 PR 关联读取完整的强推事件分页，并通过 GitHub Compare 证明中间提交属于后续强推前的历史，同时排除基础分支共同祖先。恢复后保留原运行 SHA，按 PR、提交和 attempt 重新归并，进入 E2E 统计。真正缺少唯一证据的记录仍保留为未关联观测；网络、认证或配额错误会阻止本次刷新，不再冒充未关联数据发布。

每日和增量工作流无论成功或失败都保存 `triton-collection-*` 证据 7 天。可在修复分支手动运行 Triton 增量工作流验证真实采集与构建，仅 main 分支部署看板。

| 位置 | 用途 |
|---|---|
| `collect.py`、`metrics.py`、`repository_store.py` | GitCode / Jenkins 采集与 UBS 统计 |
| `triton/` | GitHub Actions 采集、质量和部署验证 |
| `catalog.json`、`monitor/` | 项目配置、适配器及 shadow 统一采集 / 候选工件 |
| `web/` | 当前网页和派生快照 |
| `tests/`、`scripts/verify_*.py` | Python、Node、Chromium 回归及独立审计 |
