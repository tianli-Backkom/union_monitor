# 统一工程监控看板（openEuler UBS × Triton-Ascend）

双域统一工程监控看板：

- **openEuler UBS**：覆盖 ubs-engine、ubs-comm、ubs-virt、ubs-io、ubs-mem、OmniStateStore、ham、ubturbo、ubs-atomic 九个仓库的 PR 工程效率（E2E、x86、ARM、DT 耗时与排队、门禁）。
- **Triton-Ascend**：采集 [triton-lang/triton-ascend](https://github.com/triton-lang/triton-ascend) 最近 72 小时的 PR 门禁任务，监控门禁效率。

两域共用一个侧边栏界面。纯 Python 标准库采集 + SQLite + 无外部依赖网页，由 GitHub Actions 每日自动采集、验证并发布到 GitHub Pages。

## 在线地址

合并看板 Pages 地址（待部署后填写）：`https://<user>.github.io/<repo>/`

## 看板功能

侧边栏分两组导航：openEuler UBS 与 Triton-Ascend。

### openEuler UBS

- 跨仓总览（默认首页，九仓对比与跨仓指标）、单仓页、数据质量、统计口径。
- PR 工程效率：E2E/x86/ARM/DT 平均与 P90、代表批次，支持下钻全部提交、重跑、批次与任务。
- 筛选与排序：状态/搜索/完整性，按创建时间、E2E、批次数或排队/执行/总耗时排序。
- 数据质量：未匹配事件、无门禁 PR、不完整批次、采集异常。
- 旧链接自动跳转：`#overview`/`#prs` → ubs-engine 单仓页，`#repositories` → 跨仓首页。

### Triton-Ascend

- E2E 时长趋势与 NPU Job 最长排队时长趋势，按分支、状态、时间范围（6/12/24/48/72 小时）联动，两图共用时间导航器（拖拽 / 键盘可操作）。
- 平均值、P50、P90 与样本数随筛选实时更新。
- PR、GitHub Actions、重点 NPU Job 的直达链接；关注列表按耗时偏长 / 执行中 / 失败归类并支持搜索。

### 统一交互

- 统一 CSV 导出；「重新加载快照」一次刷新两域数据并各自独立提交。
- 窄屏（含 390px 手机）自适应，键盘可访问，旧链接哈希自动规范化。

## 本地运行与采集

```powershell
cd D:\ubs_core_monitor
python serve.py --port 8765
```

打开 http://127.0.0.1:8765 ，服务仅监听本机，Ctrl+C 停止。

### openEuler UBS

```powershell
python -X utf8 collect.py --all --days 30              # 刷新全部九仓最近 30 天
python -X utf8 collect.py --repo ubs-comm --days 30    # 单仓更新
python -X utf8 collect.py --days 30 --until "2026-09-09T21:58:38.753+08:00"   # 指定滚动截止
```

`--offline` 仅从缓存重算（验证幂等性）；`--limit N` 诊断抽样。本地手动更新，线上由 GitHub Actions 定时更新。

### Triton-Ascend

```powershell
$env:GH_TOKEN = '<GitHub Token>'      # 可选，提高 API 配额
python -X utf8 -m triton.dashboard --hours 72
python -X utf8 -m triton.dashboard --from-evidence   # 仅用已存证据重生成
```

### 开发数据引导

```powershell
python scripts/devdata.py   # 从线上站点拉取真实数据；--offline 用最小 fixtures
```

## 目录结构

| 位置 | 用途 |
|---|---|
| `collect.py`、`metrics.py`、`repository_store.py` | GitCode/Jenkins 采集、统计与多仓隔离发布 |
| `triton/dashboard.py`、`quality.py` | GitHub Actions 采集与发布前质量校验 |
| `data/` | SQLite、原始缓存、各仓快照（不入库） |
| `web/` | 无依赖前端（`app.js`、`core.js`、`triton-core.js` 等） |
| `validate*.py`、`source_coverage.py` | 数据一致性、跨仓隔离与来源覆盖独立审计 |
| `scripts/verify_*.py` | 各需求的独立保持性审计 |
| `tests/` | Python 与 Node 测试 |

原始缓存、SQLite、历史 CSV 与备份不进入 Git 提交或 Pages 工件；Pages 只公开看板所需的派生 JSON。

## 计算口径（要点）

- 每个 trigger 是一个独立批次。E2E = 提交/重跑起点到全部子任务结束的最长可测终态耗时；每 PR 选 E2E 最长的可测终态批次作代表批次（并列取 trigger 编号较大者），任务耗时全部取自代表批次。
- 排队 = `waiting + blocked + buildable`，执行 = `duration`，总计 = 排队 + 执行；缺任一分项时排队/总计留空。
- 成功、失败、取消（已结束）批次纳入 E2E；执行中、不完整、缺起点的不纳入。
- P90 用 `(n−1)×0.9` 线性插值（同 Excel `PERCENTILE.INC`）。
- Triton：批次按 PR head SHA 聚合，手动重跑按 run+attempt 独立成批；有效耗时必须是有限非负数值，缺失、NaN、无穷不补 0。

## 自动发布

- **每日全量**（`.github/workflows/pages.yml`）：北京时间 07:30 采集九仓（30 天）+ Triton（72 小时）、跑测试与审计、部署 Pages，并校验公开数据指纹；失败保留上一版。
- **Triton 增量**（`.github/workflows/triton-refresh.yml`）：北京时间 08:00/13:00/18:00/20:00 仅重采 Triton 并发布。
- 两流程共用 concurrency group `pages` 且 `cancel-in-progress: false`：正在运行的构建不被新触发取消，排队中的运行遵循平台默认替换规则（queue: single，同一并发组仅保留最新一个排队运行）。均支持 `workflow_dispatch` 手动运行。

## 验证

CI 目标运行时：Python 3.12 / Node 22。

```
python -m unittest discover -s tests -v
node --test tests/*.test.cjs
python validate.py
python validate_bundle.py
python -X utf8 scripts/verify_artifacts.py
python -X utf8 scripts/verify_ubs_semantics.py
python -X utf8 scripts/verify_ubs_filtering.py
python -X utf8 scripts/verify_ubs_sorting.py
python -X utf8 scripts/verify_ubs_csv.py
python -X utf8 scripts/verify_ubs_detail.py
python -X utf8 scripts/verify_ubs_routes.py
python -X utf8 scripts/verify_interactions.py
python -X utf8 scripts/verify_freshness.py
python -X utf8 scripts/verify_acceptance.py --delivering REQ-051
python -X utf8 scripts/verify_requirements_doc.py
python -X utf8 -m triton.verify_deployment <site-url> --triton-manifest web/data/triton-manifest.json --ubs-manifest web/data/ubs-manifest.json
```

## 接口依据

- openEuler UBS：GitCode 官方 API v5 的 `pulls`、`comments`、`operate_logs` 及 Jenkins 只读接口。参考 [GitCode PR API 文档](https://docs.gitcode.com/v1-docs/docs/openapi/repos/pulls/)。
- Triton-Ascend：GitHub Actions API 的 workflow runs、jobs 与 PR 关联只读接口；`GH_TOKEN` 可选。
