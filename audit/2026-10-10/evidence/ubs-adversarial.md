# UBS adversarial review

{
  "checks": 63,
  "passed": 62,
  "failed": 1,
  "unverified": 0,
  "acs": {
    "passed": 37,
    "failed": 1,
    "unverified": 2
  },
  "pageerrors": 0,
  "interceptedPOSTs": 31
}

- REQ-007-AC01 **passed** 打开ubs-engine PR1600后通过仓库选择器、哈希、侧栏、返回总览或浏览器历史改变上下文，旧详情关闭且旧导出操作不能继续执行。 — checks modal-nav-hash, modal-nav-selector, modal-nav-sidebar, modal-nav-back, modal-nav-history
- REQ-007-AC02 **passed** 详情打开时重新加载快照，旧详情不再引用更新前的PR对象；再次打开时显示新快照数据。 — checks reload-new-entity
- REQ-007-AC03 **passed** 不同仓库具有相同PR编号时，详情标题、批次、原始链接均属于当前明确选择的仓库。 — checks same-number
- REQ-007-AC04 **passed** 正常同一PR的批次展开/收起不导致详情上下文改变。 — checks expand-context
- REQ-008-AC01 **passed** 从ubs-engine PR1600打开的详情导出，CSV仓库列和文件名均标识ubs-engine，不能变为ubs-comm。 — checks real-detail-csv
- REQ-008-AC02 **passed** 模拟上下文变化或相同编号跨仓PR，导出行的仓库、PR、trigger和任务来源仍与该详情实体一致；失效详情不能产生CSV。 — checks modal-nav-hash, modal-nav-selector, modal-nav-sidebar, modal-nav-back, modal-nav-history, same-number
- REQ-008-AC03 **passed** 详情导出覆盖该PR全部批次/任务，不因页级筛选或代表批次而截断；代表标志与同一快照计算一致。 — checks real-detail-csv
- REQ-008-AC04 **failed** 无详情、详情已关闭或旧实体已失效时，按钮或处理函数不会导出上一条PR。 — checks closed-export-race, close-modes
- REQ-016-AC01 **passed** 合成PR共有3批，其中一批event_id不在events，详情显示3批而非2批。 — checks event-missing, event-empty, event-none, event-duplicate
- REQ-016-AC02 **passed** 空event_id、未知非空event_id、无events、重复events场景下，每个批次身份恰好展示一次。 — checks event-missing, event-empty, event-none, event-duplicate
- REQ-016-AC03 **passed** 失配原因与原始批次链接可见；该PR批次CSV包含同一完整集合，不因分组变化丢行。 — checks event-missing, event-empty, event-none, event-duplicate
- REQ-016-AC04 **passed** 代表批次在未知组时仍可标注代表并默认展开；不得为显示完整而伪造事件。 — checks event-missing, event-empty, event-none, event-duplicate
- REQ-036-AC01 **passed** 总览→ubs-engine→选择器ubs-comm→后退，依次回ubs-engine及总览；前进可恢复ubs-comm。 — checks history-select
- REQ-036-AC02 **passed** 侧栏、仓库链接、选择器及返回总览遵循同一用户导航历史规则，无重复hashchange造成的额外条目。 — checks history-select, history-sidebar-back
- REQ-036-AC03 **passed** 旧#repositories/#overview/#prs规范化不制造无意义中间页；未知路由回默认页且不形成循环。 — checks legacy-repositories, legacy-overview, legacy-prs, legacy-quality, legacy-repo-ubs-comm, legacy-repo-ubs-comm-quality, legacy-repo-ubs-comm-method, legacy-unknown
- REQ-036-AC04 **passed** 历史导航触发的视图、标题、高亮和详情清理与当前路由一致。 — checks history-select, modal-nav-hash, modal-nav-selector, modal-nav-sidebar, modal-nav-back, modal-nav-history
- REQ-041-AC01 **unverified** 冻结输入全量203 PR/826批次的代表值、事件时间、任务值及跨仓结果与独立重算一致；x86/ARM/DT有效样本仍为191/203/195。 — checks  — Full raw source and frozen-input validation is owned by root data audit.
- REQ-041-AC02 **passed** E2E相同按trigger编号确定代表；任务缺失或同类关联不唯一留空，不从其他批次补取。 — checks independent-all-metrics, tie-ambiguous-tasks
- REQ-041-AC03 **passed** 当前范围success/partial参与跨仓；失败/过期排除且可解释，合法零PR仓库保留。 — checks cross-summary-export, cross-exclusions
- REQ-041-AC04 **passed** 复合PR主键及批次完整URL唯一；同PR编号跨仓互不污染。新快照验收计算契约，不硬编码旧数量。 — checks same-number, independent-all-metrics
- REQ-042-AC01 **passed** 既有组合筛选的PR身份集合与独立谓词一致，搜索大小写及首尾空格处理保持。 — checks filters-combinations
- REQ-042-AC02 **passed** 完整性按已声明条件选择PR，触发请求按事件身份去重；无关联请求及未知来源批次仍可追踪。 — checks filters-combinations
- REQ-042-AC03 **passed** 图表/表格总耗时、排队、执行切换均取同一PR代表批次；相同PR在不同筛选中的代表URL不变。 — checks tie-ambiguous-tasks, page-metrics
- REQ-042-AC04 **passed** 无结果有清晰提示，重置恢复默认PR集合；空值不补0。 — checks filters-combinations
- REQ-043-AC01 **passed** 仓库P90顺序与独立重算一致；PR三种排序的完整序列及当前页内容正确。 — checks sorting-full-pages, cross-summary-export
- REQ-043-AC02 **passed** 0/1/15/16/30/31条输入显示正确页数和上一/下一页禁用状态；0条时为1/1及无记录。 — checks pages-0, pages-1, pages-15, pages-16, pages-30, pages-31
- REQ-043-AC03 **passed** 筛选缩页回第一页，结果变化导致页码越界时约束到合法页；末页不重复或遗漏记录。 — checks pages-0, pages-1, pages-15, pages-16, pages-30, pages-31
- REQ-043-AC04 **passed** 浏览器导航或耗时类型切换后的页码、排序说明与显示数据一致。 — checks page-metrics
- REQ-044-AC01 **passed** PR导出不受15行分页限制，代表trigger及E2E/三类任务三种耗时字段均正确且单位毫秒；各行包含正确仓库。 — checks filters-combinations, sorting-full-pages
- REQ-044-AC02 **passed** 九仓CSV包含状态、纳入标志、样本与覆盖率；质量CSV数量与当前质量记录一致。 — checks cross-summary-export, quality-export
- REQ-044-AC03 **passed** 批次CSV包含全部任务明细、有效与代表标志，与详情来源绑定一致。 — checks real-detail-csv
- REQ-044-AC04 **passed** 中文、逗号、引号、换行及公式前缀可正确往返解析；本地保存与Pages Blob下载内容一致，失败提示明确且可重试。 — checks csv-special-failure-retry, pages-actual-download
- REQ-045-AC01 **passed** 正常PR详情完整显示所有批次、代表标注和任务时间线；未知关联按REQ-016处理。 — checks real-detail-csv
- REQ-045-AC02 **passed** 最长E2E、历史失败等待和质量记录都打开正确仓库PR与对应批次；后续成功不抹去历史失败。 — checks drilldown-targets
- REQ-045-AC03 **passed** Esc、关闭按钮及外部点击关闭；再次打开其他PR不残留旧内容，源PR/trigger/任务链接对应当前记录。 — checks close-modes
- REQ-045-AC04 **passed** UI分钟显示与毫秒原值一致，精确值可查看；取消终态纳入既有失败等待语义，不作为质量失败的同义词。 — checks minutes-exact-cancelled
- REQ-047-AC01 **passed** 每个仓库单仓和质量深链接直接打开时，数据归属、标题、计数和导航高亮正确。 — checks deep-ubs-engine, deep-ubs-engine-quality, deep-ubs-comm, deep-ubs-comm-quality, deep-ubs-virt, deep-ubs-virt-quality, deep-ubs-io, deep-ubs-io-quality, deep-ubs-mem, deep-ubs-mem-quality, deep-OmniStateStore, deep-OmniStateStore-quality, deep-ham, deep-ham-quality, deep-ubturbo, deep-ubturbo-quality, deep-ubs-atomic, deep-ubs-atomic-quality
- REQ-047-AC02 **passed** #repositories→#ubs；#overview/#prs→ubs-engine单仓；#quality→ubs-engine质量；既有#repo/NAME及method别名按Router契约可达。 — checks legacy-repositories, legacy-overview, legacy-prs, legacy-quality, legacy-repo-ubs-comm, legacy-repo-ubs-comm-quality, legacy-repo-ubs-comm-method, legacy-unknown
- REQ-047-AC03 **passed** 未知路由按默认规则回总览，未知仓库显示未获取或明确无此仓库，不能借其他仓数据。 — checks unknown-repo
- REQ-047-AC04 **unverified** 旧站能力清单每项都有合并位置及代表验证证据；重复视觉模板/长表抽查范围声明准确，不把代表组合称为穷举。 — checks  — Capability mapping and review of sampling claims is owned by root document synthesis.

Failed / unverified

- closed-export-race failed: {"error":"{\"open\":false,\"bound\":true,\"posts\":1,\"name\":\"ubs-engine-pr-1600-batches.csv\"}\n\n1 !== 0\n","stack":["AssertionError [ERR_ASSERTION]: {\"open\":false,\"bound\":true,\"posts\":1,\"name\":\"ubs-engine-pr-1600-batches.csv\"}","","1 !== 0"]}; audit/2026-10-10/screenshots/ubs-038-closed-export-race.png

Only representative filter combinations were reviewed; not an exhaustive Cartesian product. All local CSV POSTs intercepted. Production source/data and prior audit evidence unchanged.
