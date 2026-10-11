# 统一看板对抗审查与 PR 门禁实施计划

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans task by task. Preserve each red/green result and review before committing.

**Goal:** 交付基于线上证据的样式、数据、文档与架构审查报告，并在 union_monitor 建立可执行、可阻断合入的基础功能与采集回归门禁。

**Architecture:** 保留当前生产采集流程，通过无 Secrets 的离线 PR 测试保护业务与真实适配器边界；真实浏览器验证路由、筛选、导出和窄屏。只修复审查已复现且阻碍基础门禁的缺陷，未完成的统一生产发布/持久基线/自动回滚如实列为后续上线阻断项。

**Tech Stack:** Python 3.12、Node 22、标准库采集器、Chromium/Playwright 测试、GitHub Actions 与 main 必需状态检查。

**Spec:** 用户 2026-10-11 对抗审查与 PR 门禁请求，以及 docs/design 两份统一看板目标设计。

## Global Constraints

- 基线 `e98c6af7c0640605e220c6696515528c31d343e8`；线上站点 `https://tianli-backkom.github.io/union_monitor/`。
- 使用隔离分支 `codex/union-monitor-audit-gates`；保留原目录三个未跟踪日志。
- 每次改动完成后创建对应 Git commit；交付前相关测试和验证通过。
- PR 使用最小读取权限，不触发生产采集、部署或读取 PAT；禁用 pull_request_target 执行 PR 代码。
- 来源故障不伪装为合法零数据；未知身份记录保留，统计粒度与资格明确。
- 分别报告基线问题、此次修复、剩余未验证/未完成项；抽样来源核查不冒称全量来源核验。
- 不能保证 GitHub 调度或外部来源永不故障；保障可重试故障、失败可见、坏数据不发布及基础功能回归可阻断。

## Review Focus

- 默认适配器真实参数/返回值与 fake runner 测试之间的差异。
- Matrix 同名文件碰撞、缺报告、超时、错误归属及错指纹。
- unresolved 单 workflow 与已关联提交批次混算；NPU 覆盖检查不能使用派生输出自证完整。
- 新旧路由切换后同时显示两页、残留 dialog、搜索误改分母、导出仅当前页、窄屏隐藏核心字段。
- 必需检查被跳过/取消/假成功、空数据冷启动、缺 Secrets、公开文件与本轮生成文件不一致。

## Tasks

- [x] 1. 保存审查证据：线上版本/数据哈希、独立复算与来源抽样、浏览器交互/窄屏、Actions 运行与架构 T/AC 状态。
- [x] 2. 写失败回归后修复真实适配器和影子工件隔离；验证错误不被默认为质量通过，保留影子不部署边界。
- [x] 3. 写失败回归后修复基础路由/视图生命周期、实际刷新时点及发现的统计资格/完整性问题；不扩展成完整产品迁移。
- [x] 4. 新增 PR workflow：全历史 checkout、离线 fixture 引导、Python/Node、真实 Chromium 基础操作、采集错误/超时/限流/分页契约和工件故障检查；单一聚合结果作为必需状态。
- [x] 5. 复核生产采集的发布前/后验证和有限重试；只增加必要防护，保持采集失败结论，不用 continue-on-error 伪造成功。
- [x] 6. 更新简洁 README 和操作说明，交付审查报告/证据索引及产品—架构—测试追踪。
- [ ] 7. 完整本地回归、独立审阅、分项 commit、推送审查分支并创建 PR；验证远端检查后配置/核实 main 必需检查，记录实际生效状态。

## Validation

先用失败用例证明原缺陷，再运行修复后的同一用例。完整回归使用 Python 3.12/Node 22 的 Linux 检出，避免 Windows worktree 指针和 CRLF 被误认为业务失败。PR 离线测试固定 fixture；真实站点和来源抽样另记证据，不能用离线 fixture 证明今日线上数据正确。门禁的聚合 job 必须在前置失败/跳过/取消时给非成功结果，不遗漏任一必需 job。最后核对 commit 文件集合、线上 PR 检查及分支保护读取结果。
