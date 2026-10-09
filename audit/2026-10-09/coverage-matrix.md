# 审查覆盖矩阵

正常路径覆盖独立视图和控件；边界与故障输入另列。重复ID采用最终补充检查，最初的审查脚本错误已被完整重跑替代。计数是检查项数量，不是准确率。

| ID | 检查 | 结果 | 输入/证据 |
|---|---|---|---|
|T01|Triton 初始批次数|通过|real；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|T02|初始 E2E 散点身份|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|T03|初始 NPU 散点身份|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|T04|单分支全局汇总|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|T05|单分支两图联动|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|T06|多分支集合|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|T07|清除分支恢复全部|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|T08-6|时间窗全页联动 6h|失败|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|T08-12|时间窗全页联动 12h|失败|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|T08-24|时间窗全页联动 24h|失败|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|T08-48|时间窗全页联动 48h|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|T08-72|时间窗全页联动 72h|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|T09|偏长阈值使用所选时间窗 P90|失败|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|T10|E2E 状态仅作用于对应图|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|T11|E2E 状态不改变 NPU 图|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|T12|NPU 独立状态筛选|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|T13|列表搜索尊重当前时间窗|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|T14|列表搜索不改变图表|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|T15|列表无匹配提示|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|T16|Triton CSV 按分支/时间/列表搜索导出|失败|real；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|T18|散点悬浮卡片显示|通过|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|T19|卡片点击固定|通过|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|T20|卡片可追溯原始链接|通过|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|T21|点击外部关闭卡片|通过|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|T22|拖动时间窗口改变时间范围|通过|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|T23|拖动左边界改变范围|通过|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|T24|拖动右边界改变范围|通过|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|T25|点击导航空白跳转窗口|通过|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|T26|时间滑块具备键盘与 slider 值|失败|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|T27|关注批次展开入口可键盘聚焦|失败|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|T28|关注批次点击展开|通过|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|T29|Pages 使用浏览器下载 CSV|通过|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|F01-ubs-index-404|故障隔离 ubs-index-404|失败|fault-injection；[evidence/triton-browser.json](evidence/triton-browser.json)|
|F01-single-repo-404|故障隔离 single-repo-404|通过|fault-injection；[evidence/triton-browser.json](evidence/triton-browser.json)|
|F01-triton-404|故障隔离 triton-404|通过|fault-injection；[evidence/triton-browser.json](evidence/triton-browser.json)|
|F02-triton-404|Triton 异常提供明确空态|通过|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|F03-triton-404|Triton 异常不影响 UBS|通过|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|F01-triton-bad-json|故障隔离 triton-bad-json|通过|fault-injection；[evidence/triton-browser.json](evidence/triton-browser.json)|
|F02-triton-bad-json|Triton 异常提供明确空态|通过|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|F03-triton-bad-json|Triton 异常不影响 UBS|通过|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|F01-triton-empty|故障隔离 triton-empty|通过|fault-injection；[evidence/triton-browser.json](evidence/triton-browser.json)|
|F02-triton-empty|Triton 异常提供明确空态|通过|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|F03-triton-empty|Triton 异常不影响 UBS|通过|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|F04|连续刷新不能让旧响应覆盖新响应|失败|fault-injection；[evidence/triton-browser.json](evidence/triton-browser.json)|
|V-desktop-ubs|页面无整体横向溢出 desktop ubs|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|V-desktop-ubs/repo/ubs-engine|页面无整体横向溢出 desktop ubs/repo/ubs-engine|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|V-desktop-ubs/repo/ubs-engine/quality|页面无整体横向溢出 desktop ubs/repo/ubs-engine/quality|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|V-desktop-method|页面无整体横向溢出 desktop method|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|V-desktop-triton|页面无整体横向溢出 desktop triton|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|V-tablet-ubs|页面无整体横向溢出 tablet ubs|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|V-tablet-ubs/repo/ubs-engine|页面无整体横向溢出 tablet ubs/repo/ubs-engine|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|V-tablet-ubs/repo/ubs-engine/quality|页面无整体横向溢出 tablet ubs/repo/ubs-engine/quality|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|V-tablet-method|页面无整体横向溢出 tablet method|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|V-tablet-triton|页面无整体横向溢出 tablet triton|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|V-mobile-ubs|页面无整体横向溢出 mobile ubs|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|V-mobile-ubs/repo/ubs-engine|页面无整体横向溢出 mobile ubs/repo/ubs-engine|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|V-mobile-ubs/repo/ubs-engine/quality|页面无整体横向溢出 mobile ubs/repo/ubs-engine/quality|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|V-mobile-method|页面无整体横向溢出 mobile method|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|V-mobile-triton|页面无整体横向溢出 mobile triton|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|V-mobile-nav-label|手机导航仍可识别文字或替代标签|失败|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|V-mobile-tip|触屏散点显示详情|通过|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|E01|Edge 可挂载 Triton 两图|通过|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|E02|Edge 时间窗图表|通过|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|E03|Edge 跨域导航|通过|当前快照/代码/截图；[evidence/triton-browser.json](evidence/triton-browser.json)|
|T17|跨域返回保留 Triton 会话状态|失败|当前快照/代码/截图；[evidence/triton-browser-supplement.json](evidence/triton-browser-supplement.json)|
|U01|九仓完整显示|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U02-open|跨仓状态筛选计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U03-open|空仓仍保留|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U02-merged|跨仓状态筛选计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U03-merged|空仓仍保留|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U02-closed|跨仓状态筛选计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U03-closed|空仓仍保留|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U02-all|跨仓状态筛选计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U03-all|空仓仍保留|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U04-name|仓库排序 name|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U04-prs|仓库排序 prs|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U05-ubs-engine|单仓入口 PR 计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U06-ubs-engine|单仓导航高亮|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U07-ubs-engine|单仓表格属于当前仓库|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U08-ubs-engine|质量页导航高亮|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U09-ubs-engine|质量页记录计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U05-ubs-comm|单仓入口 PR 计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U06-ubs-comm|单仓导航高亮|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U07-ubs-comm|单仓表格属于当前仓库|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U08-ubs-comm|质量页导航高亮|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U09-ubs-comm|质量页记录计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U05-ubs-virt|单仓入口 PR 计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U06-ubs-virt|单仓导航高亮|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U07-ubs-virt|单仓表格属于当前仓库|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U08-ubs-virt|质量页导航高亮|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U09-ubs-virt|质量页记录计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U05-ubs-io|单仓入口 PR 计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U06-ubs-io|单仓导航高亮|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U07-ubs-io|单仓表格属于当前仓库|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U08-ubs-io|质量页导航高亮|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U09-ubs-io|质量页记录计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U05-ubs-mem|单仓入口 PR 计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U06-ubs-mem|单仓导航高亮|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U07-ubs-mem|单仓表格属于当前仓库|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U08-ubs-mem|质量页导航高亮|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U09-ubs-mem|质量页记录计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U05-OmniStateStore|单仓入口 PR 计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U06-OmniStateStore|单仓导航高亮|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U07-OmniStateStore|单仓表格属于当前仓库|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U08-OmniStateStore|质量页导航高亮|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U09-OmniStateStore|质量页记录计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U05-ham|单仓入口 PR 计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U06-ham|单仓导航高亮|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U07-ham|单仓表格属于当前仓库|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U08-ham|质量页导航高亮|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U09-ham|质量页记录计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U05-ubturbo|单仓入口 PR 计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U06-ubturbo|单仓导航高亮|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U07-ubturbo|单仓表格属于当前仓库|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U08-ubturbo|质量页导航高亮|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U09-ubturbo|质量页记录计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U05-ubs-atomic|单仓入口 PR 计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U06-ubs-atomic|单仓导航高亮|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U07-ubs-atomic|单仓表格属于当前仓库|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U08-ubs-atomic|质量页导航高亮|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U09-ubs-atomic|质量页记录计数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U10-repositories|旧链接兼容 repositories|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U10-overview|旧链接兼容 overview|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U10-prs|旧链接兼容 prs|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U10-quality|旧链接兼容 quality|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U10-repo/ubs-comm|旧链接兼容 repo/ubs-comm|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U10-method|旧链接兼容 method|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U11|未知仓库有明确不可用提示|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U12-63|组合筛选 {"state":"open"}|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U13-64|组合筛选明细集合|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U12-65|组合筛选 {"state":"merged","trigger":"retest"}|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U13-66|组合筛选明细集合|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U12-67|组合筛选 {"quality":"incomplete"}|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U13-68|组合筛选明细集合|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U12-69|组合筛选 {"quality":"complete","trigger":"push"}|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U13-70|组合筛选明细集合|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U12-71|组合筛选 {"q":"1655"}|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U13-72|组合筛选明细集合|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U12-73|组合筛选 {"q":"xuke--"}|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U13-74|组合筛选明细集合|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U12-75|组合筛选 {"q":"4cf1f74e"}|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U13-76|组合筛选明细集合|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U12-77|组合筛选 {"q":"__NO_RESULTS__"}|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U13-78|组合筛选明细集合|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U14|第一页边界|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U15|第二页记录|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U16|末页记录与边界|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U17|筛选缩页回第一页|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U18-created|PR 排序 created|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U18-batches|PR 排序 batches|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U18-e2e|PR 排序 e2e|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U19-queue|切换耗时仍固定代表批次|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U19-duration|切换耗时仍固定代表批次|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U19-total|切换耗时仍固定代表批次|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U20|空结果分页正确|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U21|PR 导出全筛选集不是当前15行|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U22|PR CSV 全字段毫秒单位|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U23|PR CSV 代表值字段|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U24|详情保留全部批次|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U25|代表批次默认展开|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U26|详情 CSV 覆盖全部批次任务|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U27|Esc 关闭详情|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U28|关闭按钮关闭详情|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U29|质量导出记录数|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U30|质量记录跳转详情|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U31|仓库 CSV 覆盖九仓|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U32|跨仓最长记录可下钻|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U33|失败等待下钻展开对应批次|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U34|切仓清理旧详情|失败|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U35|切仓后的详情 CSV 归属与 PR 一致|失败|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U36|UBS 跨域保留搜索|通过|当前快照/代码/截图；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U37|非空失配事件批次仍显示|失败|synthetic；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|U38|CSV 中文引号换行和公式前缀|通过|synthetic；[evidence/ubs-browser.json](evidence/ubs-browser.json)|
|A12-e2e-failure|完整窗口 E2E 状态身份 failure|通过|当前快照/代码/截图；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A12-e2e-running|完整窗口 E2E 状态身份 running|通过|当前快照/代码/截图；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A12-e2e-all|完整窗口 E2E 状态身份 all|通过|当前快照/代码/截图；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A12-npu-failure|完整窗口 NPU 状态身份 failure|通过|当前快照/代码/截图；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A12-npu-running|完整窗口 NPU 状态身份 running|通过|当前快照/代码/截图；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A12-npu-all|完整窗口 NPU 状态身份 all|通过|当前快照/代码/截图；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A13-e2e|图表选区有效样本/平均/P50/P90与独立重算|通过|当前快照/代码/截图；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A13-npu|图表选区有效样本/平均/P50/P90与独立重算|通过|当前快照/代码/截图；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A01|少量搜索结果的关注分组说明一致|失败|当前快照/代码/截图；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A02|重新加载保留 Triton 时间选择|失败|当前快照/代码/截图；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A03|Triton 顶栏分支与来源不误指UBS|失败|semantic；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A04|Triton 导出失败明确且按钮恢复|通过|当前快照/代码/截图；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A14|跨仓P90排序使用独立重算值|通过|当前快照/代码/截图；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A05|仓库切换可逐步后退|失败|navigation；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A06|浏览器前进恢复路由|通过|当前快照/代码/截图；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A07|点击弹窗外部关闭详情|通过|当前快照/代码/截图；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A08-0|分页边界 0条|通过|synthetic；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A08-1|分页边界 1条|通过|synthetic；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A08-15|分页边界 15条|通过|synthetic；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A08-16|分页边界 16条|通过|synthetic；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A08-30|分页边界 30条|通过|synthetic；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A08-31|分页边界 31条|通过|synthetic；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A09|触屏拖动共享时间导航器|通过|当前快照/代码/截图；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A10|手机重新加载按钮文字在顶栏内|失败|当前快照/代码/截图；[evidence/additional-browser.json](evidence/additional-browser.json)|
|A11|UBS Pages实际Blob下载|通过|当前快照/代码/截图；[evidence/additional-browser.json](evidence/additional-browser.json)|
|D01-ubs-engine|仓库范围与归属 ubs-engine|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D02-ubs-engine|索引meta与实际快照一致 ubs-engine|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D01-ubs-comm|仓库范围与归属 ubs-comm|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D02-ubs-comm|索引meta与实际快照一致 ubs-comm|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D01-ubs-virt|仓库范围与归属 ubs-virt|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D02-ubs-virt|索引meta与实际快照一致 ubs-virt|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D01-ubs-io|仓库范围与归属 ubs-io|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D02-ubs-io|索引meta与实际快照一致 ubs-io|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D01-ubs-mem|仓库范围与归属 ubs-mem|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D02-ubs-mem|索引meta与实际快照一致 ubs-mem|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D01-OmniStateStore|仓库范围与归属 OmniStateStore|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D02-OmniStateStore|索引meta与实际快照一致 OmniStateStore|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D01-ham|仓库范围与归属 ham|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D02-ham|索引meta与实际快照一致 ham|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D01-ubturbo|仓库范围与归属 ubturbo|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D02-ubturbo|索引meta与实际快照一致 ubturbo|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D01-ubs-atomic|仓库范围与归属 ubs-atomic|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D02-ubs-atomic|索引meta与实际快照一致 ubs-atomic|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D03|全部 PR 代表值/批次/事件/任务派生一致性|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D04|复合 PR 主键唯一|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D05|批次完整URL唯一|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D06|独立Python代表值与实际前端算法全部一致|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D07|跨仓直接汇聚独立重算与前端一致|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D08|Triton 快照汇总独立重算|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|D09|Triton E2E与NPU排队/最大值派生一致性|通过|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|S01|重跑只计算本次attempt已观测跨度|失败|synthetic；[evidence/data-audit.json](evidence/data-audit.json)|
|S02|倒置workflow时间不得作为合法零耗时通过|失败|synthetic；[evidence/data-audit.json](evidence/data-audit.json)|
|S03|缺失workflow_runs字段必须拒绝|失败|synthetic；[evidence/data-audit.json](evidence/data-audit.json)|
|S04|缺失/空串/负值不得纳入有效完成统计|失败|synthetic；[evidence/data-audit.json](evidence/data-audit.json)|
|S05|最小fixture P90符合线性插值|失败|fixture；[evidence/data-audit.json](evidence/data-audit.json)|
|D10|原始平台时间/queue分项/PR身份/重跑历史独立来源审计|未验证|当前快照/代码/截图；[evidence/data-audit.json](evidence/data-audit.json)|
|P01|每日与增量使用同一缓存路径版本|失败|static-confirmed；[evidence/deployment-audit.json](evidence/deployment-audit.json)|
|P02|两个发布流程接入发布后数据指纹校验|失败|static-confirmed；[evidence/deployment-audit.json](evidence/deployment-audit.json)|
|P03|增量数据恢复检查索引JSON及全部引用快照|失败|static-confirmed；[evidence/deployment-audit.json](evidence/deployment-audit.json)|
|P04|并发配置能保留多个pending运行|未验证|documented-risk；[evidence/deployment-audit.json](evidence/deployment-audit.json)|
|P05|原始时间审计要求非零/完整证据覆盖|失败|static-confirmed；[evidence/deployment-audit.json](evidence/deployment-audit.json)|
|M01|手机Triton横轴时间标签可读|失败|当前快照/代码/截图；[evidence/visual-review.json](evidence/visual-review.json)|
|M02|桌面主要视图视觉与单样本图|通过|当前快照/代码/截图；[evidence/visual-review.json](evidence/visual-review.json)|
|M03|UBS批次详情与时间线|通过|当前快照/代码/截图；[evidence/visual-review.json](evidence/visual-review.json)|
|M04|Triton新鲜度延迟提醒|通过|当前快照/代码/截图；[evidence/visual-review.json](evidence/visual-review.json)|