# 注意事项

- 每次改动完成后，都必须创建一个对应的Git commit，以便后续追踪和回滚。
- 每次改动后，都必须编写或更新相关测试，并在交付给用户前，确保所有测试和验证全部通过。

# 代码提交与合入规范（GitHub）

- 严禁移除或绕过 `main` 分支保护，尤其是以下两项：
  - `required_status_checks`（必需状态检查 `Dashboard quality gate`）
  - `required_pull_request_reviews`（必须通过 PR 合入）
- 所有代码合入 `main` 一律走 Fork-Pull（Pull Request）流程：在分支上提交并推送，创建 Pull Request，不得直接推送到 `main`。
- 合入前必须等待 CI 门禁 `Dashboard quality gate`（python-tests / frontend-tests / collector-contracts / workflow-lint）全部通过（绿色）后，才能合并 PR 进 `main`。
- 门禁失败（红色）时，先修复代码并重新推送，让门禁转绿后再合并；不得通过临时移除保护或直接推送绕过门禁。
- PR 合并后删除该临时分支，远端与本地只保留 `main` 一个分支。