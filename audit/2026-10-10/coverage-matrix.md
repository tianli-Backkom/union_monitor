# 本轮需求验收覆盖矩阵

HEAD：4cfff7d49052734cfb9b3c3c2f03187d01c92108。51项需求、195条验收。结论：不能完整交付；以下为证据支持范围，未验证不等于失败。

| 状态 | AC数 |
|---|---:|
| passed | 88 |
| failed | 21 |
| partial | 36 |
| unverified | 50 |
| not_applicable | 0 |

矩阵整理本身未执行新测试；所引用专项审查已实际执行浏览器、对抗输入及目标版本测试。passed要求逐项证据，partial保留未覆盖条件；原始来源、真实并发、正式发布缺证据使用unverified。新快照数量变化不判缺陷。

规则级缺口另列：A06为Triton一直pending阻塞已返回UBS；A14为无合法采集窗标ok。两者不扩展混判其他具体AC输入。fault-adversarial新增12个检查全部通过，对应具体场景结果已接入。

## REQ-001 · Triton分支与时间窗全页联动

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-001-AC01 | partial | 使用冻结审查快照选择6/12/24/48/72小时，页级批次数分别为1/13/64/66/66；两图仅显示G内各自适用的批次，不能让顶部或列表继续使用完整快照。 | [triton-adversarial.json#/checks/FROZEN-G-6](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json)；[triton-adversarial.json#/checks/FROZEN-G-12](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json)；[triton-adversarial.json#/checks/FROZEN-G-24](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json)；[triton-adversarial.json#/checks/FROZEN-G-48](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json)；[triton-adversarial.json#/checks/FROZEN-G-72](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) 原Triton冻结输入五档页级与列表计数1/13/64/66/66已证明；冻结场景未完整比对两图全部身份集合，当前G场景只能作为部分图集合证据。 |
| REQ-001-AC02 | failed | 选择单分支、多分支、清除分支，再分别选择时间档；汇总、图表与列表中的每个批次均满足相同分支及时间谓词。 | [triton-adversarial.json#/checks/G-6](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json)；[triton-adversarial.json#/checks/G-12](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json)；[triton-adversarial.json#/checks/G-24](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json)；[triton-adversarial.json#/checks/G-48](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json)；[triton-adversarial.json#/checks/G-72](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json)；[triton-adversarial.json#/checks/BRANCH-PROTOTYPE](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) 普通分支/时间路径正常，但合法Git分支__proto__不可选择；不能把普通分支结果扩展为全部合法分支。 |
| REQ-001-AC03 | partial | 切换E2E局部状态不改变NPU图、顶部及列表；NPU局部状态同理。搜索不改变顶部或两图。 | [triton-adversarial.json#/checks/LOCAL-E2E](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json)；[triton-adversarial.json#/checks/SEARCH-STRATEGY](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) E2E局部按钮不影响顶部、NPU与列表已验证；反向NPU局部状态及搜索全部组件不变未逐项证明。 |
| REQ-001-AC04 | unverified | G为空时，批次/PR计数为0，耗时统计显示无样本，列表与图表给出明确空态；不得回退为全量数据。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |

## REQ-002 · 耗时偏长采用页级集合的P90

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-002-AC01 | partial | 冻结快照6小时选区的阈值为290秒，点击“耗时偏长”包含该290秒终态批次，不再显示0点。 | [triton-adversarial.json#/checks/SLOW](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) 当前快照选区P90及偏长点数一致；该证据P90=6370秒，不是原冻结6小时290秒的完整断言。 |
| REQ-002-AC02 | unverified | 改变分支或时间窗时重算阈值；改变搜索、E2E/NPU局部状态时，阈值数值不变。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-002-AC03 | partial | 零个有效完成样本时阈值为空，不补0；单样本P90等于该样本值，明确显示样本数及样本不足。 | [data-adversarial.json#/cases/numeric-boundaries-node](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 数值零/缺值与统计样本边界已核对，单样本阈值及UI样本不足说明未完整验证。 |
| REQ-002-AC04 | unverified | 图内针对局部状态的平均/P50/P90与异常判断阈值可不同，标签或说明必须区分二者的范围。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |

## REQ-003 · Triton CSV遵循页级筛选与列表搜索

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-003-AC01 | partial | 冻结快照选择6小时并搜索PR2475，CSV仅1条数据行；不能导出66条。 | [triton-adversarial.json#/checks/EXPORT](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) 当前快照搜索PR2476导出集合已核对，未直接重放原冻结6小时PR2475仅1行场景。 |
| REQ-003-AC02 | partial | 分支多选、时间窗和搜索组合下，CSV批次身份集合与独立计算的匹配集合完全相同，重复PR的不同批次分别保留。 | [triton-adversarial.json#/checks/EXPORT](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) 当前时间与搜索组合的导出身份一致；多分支及同PR不同批次全部组合未完整证明。 |
| REQ-003-AC03 | unverified | 切换两图状态或关注/全部模式，不改变相同页级筛选下的CSV集合；清除搜索后恢复G的全量批次。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-003-AC04 | unverified | 本地保存与Pages浏览器下载产生相同字段和记录；中文、引号、换行、公式前缀处理正确，空匹配仍提供带表头的CSV。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |

## REQ-004 · 跨域返回保留各域会话筛选

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-004-AC01 | passed | 设置Triton分支、6小时、搜索PR2475、E2E失败、NPU状态及全部模式，进入UBS再返回，各项状态和结果与离开前一致。 | [triton-adversarial.json#/checks/NAV-STATE](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) 同一页面运行期正常跨域返回保留分支、时间、搜索、两图状态及列表模式；使用当前可用PR2476调查输入。 |
| REQ-004-AC02 | unverified | 设置UBS状态、搜索、完整性、触发方式及排序/耗时选择，进入Triton后不影响Triton状态，返回时UBS状态可恢复。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-004-AC03 | unverified | 前进/后退和导航返回使用同一域状态恢复规则；首次进入某域仍使用已声明默认值。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-004-AC04 | passed | 本需求的会话为同一页面运行期；浏览器整页刷新、跨标签页或应用重启的持久化不作为本轮必需能力。 | [audit/2026-10-09/requirements.md#统一术语与已确认规则](D:/ubs_core_monitor/audit/2026-10-09/requirements.md) 本条为已明确的会话范围约束：同一页面运行期，不要求跨标签页/重启持久化；不据此推断那些范围的实现。 |

## REQ-005 · 重新加载快照保留当前有效操作状态

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-005-AC01 | failed | Triton选择12小时后重新加载相同范围快照，时间窗仍为12小时，分支、搜索、图状态和列表模式保持。 | [triton-adversarial.json#/checks/RELOAD-STATE](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json)；[triton-adversarial.json#/checks/EMPTY-RESTORE](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) 正常同范围reload保留状态，但同窗合法零批次payload会擦除此前分支、时间、搜索及图状态；后续恢复未保留原调查上下文。 |
| REQ-005-AC02 | unverified | UBS刷新后状态/搜索/完整性/触发方式/排序和耗时选择保留；仅在当前分页超出新结果页数时调整分页。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-005-AC03 | unverified | 刷新成功后的指标、图、列表和导出来自同一新快照，不保留旧DOM数值或混用两次加载的记录。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-005-AC04 | failed | 刷新失败给出错误状态和当前显示快照的时间；失败不得被提示为已更新成功。 | [triton-adversarial.json#/checks/INVALID-WINDOW](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) 非法采集窗payload被判ok并显示无数据，未按读取格式失败给出正确错误状态。 |

## REQ-006 · 新快照与已选状态的边界恢复

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-006-AC01 | failed | 新快照移除已选分支，页面保留其筛选标识、结果为空，并提供清除操作；不得自动扩展到其他分支。 | [triton-adversarial.json#/checks/EMPTY-RESTORE](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) 合法空批次新快照导致已选main及搜索等状态清空，违反保留失效选择并显示空匹配。 |
| REQ-006-AC02 | unverified | 原选区与新采集窗交集达到m时保留该交集；完全覆盖且原选区合法时保留原起止。标签、图表和统计使用同一范围。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-006-AC03 | partial | 无交集或交集小于m时，使用新窗末尾长度L的选区并提示原因。新采集窗不足30分钟时取其全窗；原选区短于新m时扩到m，不能产生越界或不足最小长度的选区。 | [triton-adversarial.json#/checks/RELOAD-STATE](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) 正常同窗重新加载恢复已有范围已证明；合法交集小于m、短于30分钟的新窗及L公式数值边界未实际重放。无合法窗口错误属规则级A14及REQ-010-AC04，不混判本条具体数值边界失败。 |
| REQ-006-AC04 | unverified | 搜索无匹配保留搜索词并显示空态；若新数据使分页越界，将页码约束到合法范围且不改变筛选。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |

## REQ-007 · 导航或刷新关闭失效PR详情

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-007-AC01 | passed | 打开ubs-engine PR1600后通过仓库选择器、哈希、侧栏、返回总览或浏览器历史改变上下文，旧详情关闭且旧导出操作不能继续执行。 | [ubs-adversarial.json#/checks/modal-nav-hash](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/modal-nav-selector](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/modal-nav-sidebar](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/modal-nav-back](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/modal-nav-history](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-007-AC02 | passed | 详情打开时重新加载快照，旧详情不再引用更新前的PR对象；再次打开时显示新快照数据。 | [ubs-adversarial.json#/checks/reload-new-entity](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-007-AC03 | passed | 不同仓库具有相同PR编号时，详情标题、批次、原始链接均属于当前明确选择的仓库。 | [ubs-adversarial.json#/checks/same-number](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-007-AC04 | passed | 正常同一PR的批次展开/收起不导致详情上下文改变。 | [ubs-adversarial.json#/checks/expand-context](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |

## REQ-008 · 详情CSV绑定详情自身来源

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-008-AC01 | passed | 从ubs-engine PR1600打开的详情导出，CSV仓库列和文件名均标识ubs-engine，不能变为ubs-comm。 | [ubs-adversarial.json#/checks/real-detail-csv](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-008-AC02 | passed | 模拟上下文变化或相同编号跨仓PR，导出行的仓库、PR、trigger和任务来源仍与该详情实体一致；失效详情不能产生CSV。 | [ubs-adversarial.json#/checks/modal-nav-hash](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/modal-nav-selector](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/modal-nav-sidebar](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/modal-nav-back](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/modal-nav-history](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/same-number](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-008-AC03 | passed | 详情导出覆盖该PR全部批次/任务，不因页级筛选或代表批次而截断；代表标志与同一快照计算一致。 | [ubs-adversarial.json#/checks/real-detail-csv](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-008-AC04 | failed | 无详情、详情已关闭或旧实体已失效时，按钮或处理函数不会导出上一条PR。 | [ubs-adversarial.json#/checks/closed-export-race](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/close-modes](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) 专项真实浏览器反例：关闭详情后仍可触发旧PR导出；对应closed-export-race。 |

## REQ-009 · 刷新请求按最后一次操作提交结果

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-009-AC01 | partial | 两次刷新，第一请求延迟450ms、第二先返回，最终页面和导出使用第二次结果；collected_at不被第一响应改回。 | [fault-adversarial.json#/cases/reload lateFirstSuccess](D:/ubs_core_monitor/audit/2026-10-10/evidence/fault-adversarial.json) 两次reload第一迟到成功后最终页面collected_at保持第二次值已证明；该场景未同时比较CSV身份，故整AC仍部分覆盖。 |
| REQ-009-AC02 | passed | 第一代次迟到的失败响应不能覆盖第二代次已成功的状态或隐藏视图。 | [fault-adversarial.json#/cases/reload lateFirstFailure](D:/ubs_core_monitor/audit/2026-10-10/evidence/fault-adversarial.json) 第一迟到失败未覆盖第二次成功状态与页面；保留当前成功collected_at。 |
| REQ-009-AC03 | partial | 两域响应完成顺序不同，均按其当前代次提交，不混用新旧加载的索引与单仓快照。 | [fault-adversarial.json#/cases/reload lateFirstSuccess](D:/ubs_core_monitor/audit/2026-10-10/evidence/fault-adversarial.json)；[fault-adversarial.json#/cases/reload lateFirstFailure](D:/ubs_core_monitor/audit/2026-10-10/evidence/fault-adversarial.json) 重复刷新两域最终状态与最新代次一致；未穷尽两域响应交错及索引/引用快照的身份组合。 |
| REQ-009-AC04 | partial | 连续多次点击后，加载提示、按钮状态、视图数据和新鲜度均与最终代次一致；无额外错误或重复监听器。 | [fault-adversarial.json#/cases/reload lateFirstSuccess](D:/ubs_core_monitor/audit/2026-10-10/evidence/fault-adversarial.json)；[fault-adversarial.json#/cases/reload lateFirstFailure](D:/ubs_core_monitor/audit/2026-10-10/evidence/fault-adversarial.json) 两次连续reload的最终数据/状态有实际证据；多次点击、所有加载按钮和定时器/监听器数量未完整验证。 |

## REQ-010 · UBS与Triton读取故障隔离

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-010-AC01 | passed | UBS索引404或坏JSON时，直接打开#triton仍请求Triton快照、挂载两图并能筛选和导出。 | [fault-adversarial.json#/cases/UBS 404 healthyTriton](D:/ubs_core_monitor/audit/2026-10-10/evidence/fault-adversarial.json)；[fault-adversarial.json#/cases/UBS badJSON healthyTriton](D:/ubs_core_monitor/audit/2026-10-10/evidence/fault-adversarial.json) UBS索引404及坏JSON时实际#triton为ok、两图挂载且导出被本地拦截成功；具体健康域路径已执行。 |
| REQ-010-AC02 | passed | Triton404、坏JSON或合法空批次时，UBS九仓总览及可用单仓页仍可使用，Triton呈现与错误类型相符的状态。 | [fault-adversarial.json#/cases/Triton 404 healthyUBS](D:/ubs_core_monitor/audit/2026-10-10/evidence/fault-adversarial.json)；[fault-adversarial.json#/cases/Triton badJSON healthyUBS](D:/ubs_core_monitor/audit/2026-10-10/evidence/fault-adversarial.json)；[fault-adversarial.json#/cases/Triton empty healthyUBS](D:/ubs_core_monitor/audit/2026-10-10/evidence/fault-adversarial.json) Triton404、坏JSON及合法空批次三场景，UBS状态ok并显示九仓；Triton故障与合法空状态区分。一直pending的独立读取规则缺口另记A06，不当作本AC三个具体场景失败。 |
| REQ-010-AC03 | unverified | ubs-engine快照404或归属不匹配时，该仓标为失败/不可用，其他仓不借用其数据，健康域继续工作。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-010-AC04 | failed | 加载中、合法零数据、未获取、失败和过期数据有不同含义的提示，不能以零值替代读取失败。 | [triton-adversarial.json#/checks/INVALID-WINDOW](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) 非法采集时间窗被标ok及合法空态，读取失败与合法零数据没有正确区分。 |

## REQ-011 · 统计口径页独立于快照读取

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-011-AC01 | partial | 分别注入UBS索引404、Triton404及两域同时失败，#method正常显示两域统计定义。 | [fault-adversarial.json#/cases/UBS 404 healthyTriton method](D:/ubs_core_monitor/audit/2026-10-10/evidence/fault-adversarial.json)；[fault-adversarial.json#/cases/UBS badJSON healthyTriton method](D:/ubs_core_monitor/audit/2026-10-10/evidence/fault-adversarial.json)；[fault-adversarial.json#/cases/method bothFailed](D:/ubs_core_monitor/audit/2026-10-10/evidence/fault-adversarial.json) UBS索引404/坏JSON及双域失败时口径两域定义可见；单独Triton404后访问口径场景未单列直接证据。 |
| REQ-011-AC02 | passed | 直接打开#method，在快照请求尚未返回时不隐藏口径正文。 | [fault-adversarial.json#/cases/method bothPending](D:/ubs_core_monitor/audit/2026-10-10/evidence/fault-adversarial.json) 直接#method两域请求仍pending时正文立即可见，请求返回后仍可见。 |
| REQ-011-AC03 | passed | 从故障页进入口径再返回数据页，故障状态保留，不能误显示成功或陈旧占位内容。 | [fault-adversarial.json#/cases/method return preservesUBSFailure](D:/ubs_core_monitor/audit/2026-10-10/evidence/fault-adversarial.json) 双失败状态从口径返回UBS仍为failed，不把故障状态变成成功或旧占位。 |

## REQ-012 · 每日与增量流程共享可兼容UBS快照

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-012-AC01 | passed | 配置检查证明共享UBS缓存的路径和影响版本的选项一致，或提供明确的替代快照工件版本协议。仅key前缀一致不能作为通过依据。 | [delivery-evidence-review.json#/acceptance_review/REQ-012-AC01](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Both workflows now use identical ordered shared paths and versioned ubs-snapshots-v1 keys; collection evidence cache is separated. |
| REQ-012-AC02 | failed | 每日生成快照B后，增量流程能恢复B的索引及全部被引用仓库快照，内容指纹与B一致。 | [delivery-evidence-review.json#/acceptance_review/REQ-012-AC02](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Warm daily generation cannot stamp bundle B while restored A manifest remains: --write-manifest exits 1 before stamping even if only generated_at changed. |
| REQ-012-AC03 | failed | 索引与单仓快照来自同一工件版本，不能把旧索引与新单仓或相反组合发布。 | [delivery-evidence-review.json#/acceptance_review/REQ-012-AC03](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) The manifest files table is not checked against computed digests: truncating it to index-only still yields verified, losing the promised complete artifact binding. |
| REQ-012-AC04 | partial | 缓存缺失、版本不兼容或证据无法取得时，日志准确标记命中/未命中和回退来源，不虚称共享成功。 | [delivery-evidence-review.json#/acceptance_review/REQ-012-AC04](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Per-file fallback and cache-present logs exist, but file presence is labelled cache hit without binding it to actions/cache-hit/cache-matched-key outputs; warm daily failure remains. |

## REQ-013 · 冷热缓存与跨日更新链路验收

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-013-AC01 | failed | 使用内容不同的A/B快照：暖缓存A→每日更新B→Triton增量发布，最终UBS索引及引用快照为B，不能回到A。 | [delivery-evidence-review.json#/acceptance_review/REQ-013-AC01](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Existing warm-chain test constructs B in a fresh directory, skipping the production condition of a restored A manifest in the daily workspace. Real --write-manifest rejects that condition. |
| REQ-013-AC02 | passed | 无缓存冷启动时，从规定回退站点恢复的文件可通过完整性及一致性检查后再发布；缺文件不能以索引非空判成功。 | [delivery-evidence-review.json#/acceptance_review/REQ-013-AC02](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Local replay extracts production Ensure UBS data script and checks cold fallback plus missing/empty references through the bundle gate; historical chain log is available. |
| REQ-013-AC03 | passed | 缓存命中但工件无效时，该次发布被阻断或明确恢复到可验证的完整工件，不能发布混合版本。 | [delivery-evidence-review.json#/acceptance_review/REQ-013-AC03](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Mixed cached snapshot is rejected by manifest/range verification in local tests. |
| REQ-013-AC04 | partial | 交付测试输入、流程次序、缓存命中/回退日志及每一步UBS指纹；真实Actions验收另附隔离工作流运行ID，静态配置检查不替代链路证据。 | [delivery-evidence-review.json#/acceptance_review/REQ-013-AC04](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Local A/B fingerprints and source logs exist, but the SUMMARY explicitly says isolated Actions run IDs are still missing. |

## REQ-014 · 重跑E2E使用本次attempt的可证明起点

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-014-AC01 | passed | 合成输入：原run00:00、attempt2可信触发02:00、最后结束02:05，E2E为300秒，而非7500秒。 | [data-adversarial.json#/cases/trusted-attempt-trigger](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 数据专项逐AC合成/纯函数检查支持该计算与输入契约；不扩展为原始来源或真实运行历史准确性。 |
| REQ-014-AC02 | passed | 只提供attempt2开始02:00、结束02:05时，可展示300秒已观测近似跨度，必须注明起点来源与approximate；不能称为已经证明的真实提交E2E。 | [data-adversarial.json#/cases/attempt-start-proxy](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 数据专项逐AC合成/纯函数检查支持该计算与输入契约；不扩展为原始来源或真实运行历史准确性。 |
| REQ-014-AC03 | passed | 没有任何本次起点证据时，不从原run创建时间或时间接近猜起点；保持批次和workflow明细可见，E2E为空且不参与完成耗时统计。 | [data-adversarial.json#/cases/no-current-attempt-start](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 数据专项逐AC合成/纯函数检查支持该计算与输入契约；不扩展为原始来源或真实运行历史准确性。 |
| REQ-014-AC04 | partial | 批次起点、图表、详情、汇总和CSV使用同一时间来源与近似标记；真实历史影响只有完成REQ-038后才可下结论。 | [data-adversarial.json#/cases/attempt-csv-source-and-unknown-value](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) CSV时间来源/近似与未知值有纯数据证据；图、详情、汇总的全链一致性未完整验证，真实历史影响仍未验证。 |

## REQ-015 · attempt独立身份与历史明细保留

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-015-AC01 | failed | 同一run的attempt1、attempt2输入后，两次历史身份及其各自jobs均保留，不能只剩最新attempt；重复采集同一attempt不会重复计数。 | [data-adversarial.json#/cases/explicit-attempt-history-and-dedup](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/collector-still-enumerates-only-current-attempt](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 数据专项可复现反例：collector-still-enumerates-only-current-attempt。合成边界缺陷不证明已发生真实线上损害。 |
| REQ-015-AC02 | failed | 采集窗口内实际触发的重跑即使原run首次创建在窗口外也能被识别；窗口外证据只用于关联时不得误计入当前窗口。 | [data-adversarial.json#/cases/provided-old-run-current-attempt](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/collector-old-run-beyond-lookback-is-lost](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 数据专项可复现反例：collector-old-run-beyond-lookback-is-lost。合成边界缺陷不证明已发生真实线上损害。 |
| REQ-015-AC03 | passed | 相同SHA的辅助workflow保持既有初次批次聚合，独立重跑不并回初次提交，也不与别的run/attempt串用任务。 | [data-adversarial.json#/cases/explicit-attempt-history-and-dedup](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 数据专项逐AC合成/纯函数检查支持该计算与输入契约；不扩展为原始来源或真实运行历史准确性。 |
| REQ-015-AC04 | partial | 无法可靠关联PR时，按run/attempt隔离并明示缺证据；不能按标题或时间接近猜PR。真实历史核验保留各attempt原始输入。 | [data-adversarial.json#/cases/unresolved-run-attempt-isolation](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 无法关联PR时run/attempt隔离的合成输入通过；真实历史原始attempt输入未提供。 |

## REQ-016 · 事件关联失配批次完整下钻

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-016-AC01 | passed | 合成PR共有3批，其中一批event_id不在events，详情显示3批而非2批。 | [ubs-adversarial.json#/checks/event-missing](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/event-empty](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/event-none](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/event-duplicate](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-016-AC02 | passed | 空event_id、未知非空event_id、无events、重复events场景下，每个批次身份恰好展示一次。 | [ubs-adversarial.json#/checks/event-missing](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/event-empty](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/event-none](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/event-duplicate](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-016-AC03 | passed | 失配原因与原始批次链接可见；该PR批次CSV包含同一完整集合，不因分组变化丢行。 | [ubs-adversarial.json#/checks/event-missing](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/event-empty](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/event-none](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/event-duplicate](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-016-AC04 | passed | 代表批次在未知组时仍可标注代表并默认展开；不得为显示完整而伪造事件。 | [ubs-adversarial.json#/checks/event-missing](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/event-empty](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/event-none](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/event-duplicate](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |

## REQ-017 · Triton数值有效性统一过滤

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-017-AC01 | passed | 成功null、失败空串、成功-1秒三条输入的有效完成count为0，平均/P50/P90为空。 | [data-adversarial.json#/cases/numeric-boundaries-node](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/numeric-boundaries-python](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 数据专项逐AC合成/纯函数检查支持该计算与输入契约；不扩展为原始来源或真实运行历史准确性。 |
| REQ-017-AC02 | partial | 真实数值0作为合法0保留；无值与合法0在展示、图表和CSV中可区分。 | [data-adversarial.json#/cases/attempt-csv-source-and-unknown-value](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/mixed-validity-node](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 合法零与缺值的算法及CSV区分通过；图表与页面各状态的视觉区分未完整证明。 |
| REQ-017-AC03 | passed | 混合有效/无效样本的分母只包含适用状态下的有效数值，独立重算平均与分位数完全一致。 | [data-adversarial.json#/cases/mixed-validity-node](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 数据专项逐AC合成/纯函数检查支持该计算与输入契约；不扩展为原始来源或真实运行历史准确性。 |
| REQ-017-AC04 | partial | 运行中与取消仍可按有效已观测值展示，但不成为成功/失败完成E2E统计样本；无效点不得静默画在0位置。 | [data-adversarial.json#/cases/mixed-validity-node](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 运行/取消不计完成样本的算法通过；无效点不画在0位置的DOM图表行为未完整核验。 |

## REQ-018 · GitHub响应字段与分页契约校验

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-018-AC01 | passed | workflow_runs字段缺失、为null或非数组时明确报错，不能返回合法空列表。 | [data-adversarial.json#/cases/workflow-schema-missing](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/workflow-schema-null](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/workflow-schema-object](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 数据专项逐AC合成/纯函数检查支持该计算与输入契约；不扩展为原始来源或真实运行历史准确性。 |
| REQ-018-AC02 | passed | 合法workflow_runs=[]可以表示零数据；其结果与缺字段失败在状态和报告中明确区分。 | [data-adversarial.json#/cases/legal-zero-page](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 数据专项逐AC合成/纯函数检查支持该计算与输入契约；不扩展为原始来源或真实运行历史准确性。 |
| REQ-018-AC03 | failed | 重复分页记录、分页缺失及声明数量与实际记录不符时能识别异常，不静默截断或重复计数。 | [data-adversarial.json#/cases/duplicate-page-id](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/declared-count-missing-page](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/declared-count-changes-hide-truncation](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/duplicate-records-without-id](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 数据专项可复现反例：declared-count-changes-hide-truncation、duplicate-records-without-id。合成边界缺陷不证明已发生真实线上损害。 |
| REQ-018-AC04 | unverified | 采集契约失败时本次不发布，旧有效快照保持；错误报告指明来源、响应问题及受影响范围，不包含凭证。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |

## REQ-019 · workflow与批次时间异常门禁

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-019-AC01 | failed | completed workflow updated_at早于其适用起点时，不能通过截成0秒使quality.passed为true。 | [data-adversarial.json#/cases/baseline-quality-control](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/rerun-end-before-start](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/other-workflow-masks-inverted-applicable-start](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 数据专项可复现反例：other-workflow-masks-inverted-applicable-start。合成边界缺陷不证明已发生真实线上损害。 |
| REQ-019-AC02 | failed | 缺失、不可解析、结束早于起点、完成时间超出适用as_of等边界有明确检查结果；不伪造精确E2E。 | [data-adversarial.json#/cases/completed-after-as-of](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/invalid-as-of-missing](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/invalid-as-of-invalid](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/quality-duration-negative](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/quality-duration-null](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/quality-duration-bool](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/quality-duration-string](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/quality-duration-wrong-span](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/quality-contradictory-summary](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 数据专项可复现反例：invalid-as-of-missing、invalid-as-of-invalid、quality-duration-negative、quality-duration-null、quality-duration-bool、quality-duration-string、quality-duration-wrong-span、quality-contradictory-summary。合成边界缺陷不证明已发生真实线上损害。 |
| REQ-019-AC03 | failed | 运行中只有已观测跨度，as_of和起点可追溯；没有合法完成时间的批次不作为完成样本。 | [data-adversarial.json#/cases/invalid-as-of-missing](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/invalid-as-of-invalid](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/running-nan-observed-span](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 数据专项可复现反例：invalid-as-of-missing、invalid-as-of-invalid、running-nan-observed-span。合成边界缺陷不证明已发生真实线上损害。 |
| REQ-019-AC04 | passed | 源NPU时间倒置继续写warning并留空排队值；合法跳过或取消前未启动不能误判为已完成时间缺失。 | [data-adversarial.json#/cases/npu-inverted-source-warning](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/npu-unstarted-skipped](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/npu-unstarted-cancelled](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 数据专项逐AC合成/纯函数检查支持该计算与输入契约；不扩展为原始来源或真实运行历史准确性。 |

## REQ-020 · 恢复UBS工件的完整性校验

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-020-AC01 | passed | 坏JSON、缺少repositories必要结构、引用单仓下载失败、空文件均产生恢复失败结果，不能只凭index非空继续上传。 | [delivery-evidence-review.json#/acceptance_review/REQ-020-AC01](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Malformed/empty index and referenced snapshot failures are covered by the actual bundle gate and local controlled tests. |
| REQ-020-AC02 | passed | 索引引用的全部快照都可读取、解析并确认仓库归属；未引用/明确无快照的pending或首次failed仓库显示未获取，不能造空成功数据。 | [delivery-evidence-review.json#/acceptance_review/REQ-020-AC02](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Every referenced snapshot is parsed and repository ownership checked; pending/first-failed entries without snapshots remain distinct. |
| REQ-020-AC03 | passed | 命中缓存与从站点回退两种路径执行同一完整性检查，错误报告包含具体缺失引用及恢复来源。 | [delivery-evidence-review.json#/acceptance_review/REQ-020-AC03](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Both workflow paths call the same validate_bundle gate; local chain tests name missing references and restore sources. |
| REQ-020-AC04 | passed | 恢复不完整时不会覆盖上一份已发布的有效页面；失败后的重试只在完整性通过后进入发布前检查。 | [delivery-evidence-review.json#/acceptance_review/REQ-020-AC04](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Build gate precedes cache save/upload and deploy needs build. Controlled negative tests cover failed restore; actual online rollback is not claimed. |

## REQ-021 · 发布前跨文件一致性门禁

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-021-AC01 | passed | 成功/部分成功且纳入跨仓的单仓，其repository及时间范围必须与索引一致；跨仓汇总只纳入满足既有条件的PR。 | [delivery-evidence-review.json#/acceptance_review/REQ-021-AC01](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Success/partial snapshots must match index repository and start/end window; repositoryRows applies the current/included rule. |
| REQ-021-AC02 | passed | 失败、过期保留快照及合法零PR成功快照有不同标识；过期/失败不混入跨仓指标，空仓仍展示。 | [delivery-evidence-review.json#/acceptance_review/REQ-021-AC02](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Failed/stale/pending/zero-PR scopes have distinct inclusion and display rules with controlled tests. |
| REQ-021-AC03 | passed | 将其他仓库JSON置于当前引用路径、混合索引版本或修改关键字段，门禁失败并说明原因。 | [delivery-evidence-review.json#/acceptance_review/REQ-021-AC03](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Repository/range/manifest mismatches are blocked with explicit reasons in existing tests. |
| REQ-021-AC04 | partial | Triton JSON、CSV、manifest和构建输入的批次身份、统计范围、采集时间可追溯一致；检查通过后才上传当前工件。 | [delivery-evidence-review.json#/acceptance_review/REQ-021-AC04](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Triton JSON/CSV/manifest/output-evidence consistency is checked, but dashboard-data.json is itself written from the final payload; verify_artifacts does not read or recompute enriched-runs.json build inputs. |

## REQ-022 · 部署后公开数据指纹校验

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-022-AC01 | unverified | 受控构建到部署提供manifest、工件及实际URL证据；每个被校验数据文件的身份和SHA-256/稳定JSON指纹与构建一致。 | [delivery-evidence-review.json#/acceptance_review/REQ-022-AC01](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json)；[delivery-evidence-review.json#/probes/truncated_manifest_files](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) 缺少真实受控构建/正式部署/公开URL对应记录，故不能验证正式链路。另有index-only manifest被接受的实现反例，已在REQ-012-AC03记录失败；不以缺正式证据本身判线上失败。 |
| REQ-022-AC02 | passed | Triton验证读取实际/data/triton.json入口，不能仅对合成内嵌HTML验证后宣称真实部署通过。 | [delivery-evidence-review.json#/acceptance_review/REQ-022-AC02](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Production verify_triton reads /data/triton.json; fresh controlled tests verify that route. |
| REQ-022-AC03 | passed | 公开URL仍返回旧数据或篡改数据时，限定重试后workflow失败，并在运行摘要指出不一致文件；不得显示部署验证成功。 | [delivery-evidence-review.json#/acceptance_review/REQ-022-AC03](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Bounded retry and failure summary/no-rollback behavior are exercised by fresh controlled mismatch/fetch-error tests and wired into both workflows. |
| REQ-022-AC04 | unverified | 成功结果记录构建/运行ID、URL、校验时刻与指纹；失败不会被宣称已自动回滚，除非另有真实回滚证据。 | [delivery-evidence-review.json#/acceptance_review/REQ-022-AC04](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) record_success can emit run IDs/URL/time/fingerprints in real CI, but all retained examples are synthetic example.github.io records with null IDs; artifact evidence declares actual deployment unverified. |

## REQ-023 · 原始来源审计覆盖率与缺失清单

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-023-AC01 | passed | raw为空但有应核验的完成任务时，来源覆盖为0且状态未验证，不能报告来源全部通过。 | [delivery-evidence-review.json#/acceptance_review/REQ-023-AC01](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Raw-empty applicable jobs remain source-unverified with checks_passed false in fresh integration tests. |
| REQ-023-AC02 | failed | 覆盖计数满足“已验证一致+已发现差异+缺证据=适用总数”，可追溯到任务/批次身份；原始行数不冒充组件准确率。 | [delivery-evidence-review.json#/acceptance_review/REQ-023-AC02](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Derived-only object yields applicable=1 but verified+difference+missing=0; duplicate applicable identities can yield verified with denominator2/verified1/missing0. The stated three-term accounting invariant is violated. |
| REQ-023-AC03 | passed | 只补齐一部分原始证据时，报告保持分项覆盖和缺失清单，不因为存在任意raw文件就转为完整通过。 | [delivery-evidence-review.json#/acceptance_review/REQ-023-AC03](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Partial independent evidence is kept partial and task missing identities are retained in fresh tests. |
| REQ-023-AC04 | passed | 没有适用对象时写N/A或无样本及原因，不能用0/0或100%表示来源准确。 | [delivery-evidence-review.json#/acceptance_review/REQ-023-AC04](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) No-applicable-object result is N/A with a reason and no accuracy percentage. |

## REQ-024 · 排队原始分项独立核验

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-024-AC01 | passed | 原始分项12/5/3毫秒时queue为20毫秒；与快照queue、total及有效统计样本一致。 | [delivery-evidence-review.json#/acceptance_review/REQ-024-AC01](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) 12/5/3 component sum and queue/total/statistical propagation are covered by fresh integrated source tests. |
| REQ-024-AC02 | failed | 任一分项缺失或非法时queue与total保持未知，已知duration可保留；未知不得补0。 | [delivery-evidence-review.json#/acceptance_review/REQ-024-AC02](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) queue_from_raw accepts bool, negative values, NaN and infinity as components; invalid parts do not remain unknown. |
| REQ-024-AC03 | passed | 篡改raw分项而保留派生总和值自洽时，独立核验能发现差异并给出任务完整URL及字段。 | [delivery-evidence-review.json#/acceptance_review/REQ-024-AC03](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Controlled raw-only component tampering is detected with full job URL and components in the existing fresh tests. |
| REQ-024-AC04 | partial | 报告区分原始queue已验证、派生queue自洽及缺证据三种情况，并给出适用对象覆盖。 | [delivery-evidence-review.json#/acceptance_review/REQ-024-AC04](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Verified/derived/missing categories exist, but derived-only evidence is removed from missing denominator and duplicate identities break complete coverage accounting. |

## REQ-025 · 审计总体状态和分项通过语义

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-025-AC01 | partial | 派生通过而原始工件缺失时，报告明确“派生通过、来源未验证、覆盖Partial”，不能写成来源正确。 | [delivery-evidence-review.json#/acceptance_review/REQ-025-AC01](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Job time/queue source states are separated from derived consistency, but source PR identity and attempt-history sections promised by the requirement are omitted/deferred. |
| REQ-025-AC02 | failed | 真实比对发现差异标失败；仅缺权限或文件标未验证；不适用必须解释，不将未验证伪装为失败或通过。 | [delivery-evidence-review.json#/acceptance_review/REQ-025-AC02](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) failure_report(FileNotFoundError) yields overall_status=failed, contradicting missing-file=unverified distinction required by AC02. |
| REQ-025-AC03 | passed | 过程退出码0只代表执行完成时，不作为未执行审计通过的证据；实际审计异常保留错误与受影响范围。 | [delivery-evidence-review.json#/acceptance_review/REQ-025-AC03](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Unexpected exceptions retain error and affected_scope and are re-raised; runtime evidence correctly records raw-audit exit1 rather than wrapper success. |
| REQ-025-AC04 | partial | 报告和命令/CI结果的总体状态一致；只有所声明必需来源分项完成且无差异时，才可宣称该范围来源验证通过。 | [delivery-evidence-review.json#/acceptance_review/REQ-025-AC04](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Exit/report consistency is covered for the two implemented categories; omitted PR/attempt scopes and derived coverage accounting prevent a full declared-scope source verdict. |

## REQ-026 · 关注分组与小样本说明统一

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-026-AC01 | passed | 冻结快照搜索PR2455时，不因仅搜索命中1条就将全局策略改成“耗时最长”；组名和提示仍依据G样本数。 | [triton-adversarial.json#/checks/SEARCH-STRATEGY](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) 原冻结PR2455搜索不改变基于G有效样本的分组策略，已由实际浏览器断言证明。 |
| REQ-026-AC02 | unverified | 构造G有效样本9和10两种输入，分别使用前5最长与P90偏长策略，说明标明同一个样本分母。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-026-AC03 | unverified | 搜索0/1/多条、切换关注/全部时，组名、组内数量与记录一致；失败与偏长组可重叠，不能将组计数相加当唯一批次数。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-026-AC04 | unverified | CSV仍导出G经搜索后的完整记录集合，不被前5或关注组约束。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |

## REQ-027 · 时间滑块键盘与范围语义

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-027-AC01 | partial | 只用Tab可到达滑块/边界，方向键可移动窗口或调整对应边界；Home/End可到达允许边界，操作后两图和页级范围联动。 | [triton-adversarial.json#/checks/KEY-SLIDER](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) 实际键盘改变滑块范围通过；Tab覆盖所有入口、左右边界及Home/End未逐项证明。 |
| REQ-027-AC02 | partial | aria-valuemin/max/now或等价范围语义与实际时间同步更新，不能只有role=slider。 | [triton-adversarial.json#/checks/KEY-ARIA](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json)；[triton-adversarial.json#/checks/KEY-SLIDER](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) slider最小/最大/当前ARIA值存在；全部键盘/边界操作后的同步及可读时间语义未完整核验。 |
| REQ-027-AC03 | unverified | 键盘操作不越过采集窗，保持至少30分钟窗口（采集窗本身更短时以可用窗为限）；可见焦点不会因重绘丢失。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-027-AC04 | unverified | 同一输入的指针、触屏与键盘结果采用同一时间约束；既有快捷时间档仍可用。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |

## REQ-028 · 批次行键盘展开与关闭

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-028-AC01 | unverified | Tab可到达每个批次展开入口，Enter和Space可展开/收起，aria-expanded与实际内容可见性一致。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-028-AC02 | unverified | 展开后的PR、Actions和job链接可继续用键盘访问；焦点顺序不会跳到隐藏明细。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-028-AC03 | unverified | 筛选/重绘移除当前记录时，焦点回到合理的仍可见控件，不悬留在已删除DOM。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-028-AC04 | unverified | 正常点击展开行为与键盘显示同一批次、同一workflow和任务明细。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |

## REQ-029 · 散点详情的等价键盘访问

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-029-AC01 | partial | 键盘能定位并打开指定批次的E2E/NPU详情，信息、近似标记和链接与该散点卡片一致。 | [triton-adversarial.json#/checks/KEY-TIP](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) 键盘固定详情通过；E2E/NPU全部信息、近似标志及链接与对应散点的等价比较未完整完成。 |
| REQ-029-AC02 | partial | 固定详情内链接可聚焦，Esc或明确关闭入口可退出，焦点返回发起控件；悬浮卡片不能遮住且阻断键盘目标。 | [triton-adversarial.json#/checks/KEY-TIP](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) 键盘固定与退出详情通过；链接焦点、返回发起控件及遮挡情况未完整证明。 |
| REQ-029-AC03 | unverified | 取消固定后不留下不可见的焦点陷阱；点击外部和触屏卡片行为继续正确。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |

## REQ-030 · 手机顶栏动作完整显示

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-030-AC01 | passed | 390×844下reload控件及其文字/图标可见区域落在顶栏边界内，不出现上沿-23.5px、下沿86.5px越出64px容器的状态。 | [triton-adversarial.json#/checks/MOBILE-HEADER](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) 390px实际浏览器几何证明reload可见区域在顶栏内，页面宽度390px。 |
| REQ-030-AC02 | unverified | UBS总览、单仓、质量、Triton和口径页顶栏均可操作，无动作与时间文字重叠或整页横向溢出。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-030-AC03 | unverified | 动作采用图标时，具有可识别名称与可访问提示；点击或触屏触发的仍是同一重新加载功能。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |

## REQ-031 · 小屏趋势横轴自适应刻度

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-031-AC01 | partial | 390px视口下，两图相邻横轴标签不重叠，首末可见标签不被裁切；6/12/24/48/72小时均检查。 | [triton-adversarial.json#/checks/RESPONSIVE-EVIDENCE](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json)；[triton-adversarial.json#/checks/MOBILE-HEADER](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) Chrome390/1024/1440及五档时间窗已保存实际截图/坐标；人工阅读、所有21视图或旋转/尺寸变化的完整验收尚未完成。 |
| REQ-031-AC02 | partial | 1024和1440px视口保留足够时间信息；首末标签、选区文字与真实窗口一致。 | [triton-adversarial.json#/checks/RESPONSIVE-EVIDENCE](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json)；[triton-adversarial.json#/checks/MOBILE-HEADER](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) Chrome390/1024/1440及五档时间窗已保存实际截图/坐标；人工阅读、所有21视图或旋转/尺寸变化的完整验收尚未完成。 |
| REQ-031-AC03 | partial | 缩放/旋转/容器尺寸变化后重新布局刻度，散点对应时间与完整时间详情不变。 | [triton-adversarial.json#/checks/RESPONSIVE-EVIDENCE](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json)；[triton-adversarial.json#/checks/MOBILE-HEADER](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) Chrome390/1024/1440及五档时间窗已保存实际截图/坐标；人工阅读、所有21视图或旋转/尺寸变化的完整验收尚未完成。 |

## REQ-032 · 图标导航的视觉可识别性

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-032-AC01 | unverified | 390px图标侧栏中，用户能确认九仓总览、单仓、质量、Triton与口径入口；不能只有font-size:0的隐藏文本且无视觉说明。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-032-AC02 | unverified | 通过悬浮/焦点或触屏等价方式可获得入口名称，当前入口有清晰高亮，说明不遮住点击目标。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-032-AC03 | unverified | 辅助技术仍可读取正确名称；本需求不将现有DOM文字保留的情况错误描述为已证实无屏幕阅读器名称。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |

## REQ-033 · 共享顶栏分支表达跟随域

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-033-AC01 | unverified | Triton选main时显示main；全选语义显示全部目标分支；多选显示数量或明确多分支，并可查看所选分支。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-033-AC02 | unverified | Triton不因为从UBS进入就遗留master徽标；UBS仍按实际仓库meta显示master或实际值。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-033-AC03 | unverified | 切域、切分支、重新加载及直接深链接打开后，分支表达与当前数据集合一致。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |

## REQ-034 · 当前域代码仓链接正确

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-034-AC01 | passed | 从任一UBS仓库进入Triton，代码仓链接指向triton-lang/triton-ascend，不指向gitcode.com。 | [triton-adversarial.json#/checks/CODE-LINK](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) 实际Triton代码仓链接为triton-lang/triton-ascend，未残留GitCode UBS来源。 |
| REQ-034-AC02 | unverified | UBS切仓后链接repository标识与页面仓库一致，不能借用其他仓库链接。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-034-AC03 | unverified | 直接打开Triton和浏览器前进/后退后链接仍正确；链接名称/提示能区分跨仓总览参考链接与单仓来源。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |

## REQ-035 · 当前域页脚统计与元数据正确

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-035-AC01 | unverified | UBS总览进入Triton后，不遗留9 REPOSITORIES/203 PR等UBS统计；显示的PR/批次/采集时间来自Triton当前定义范围。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-035-AC02 | unverified | 分支和时间窗改变后，标为当前筛选范围的页脚数量与G一致；若展示完整快照元信息必须明确标为快照范围。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-035-AC03 | unverified | 直接入口、返回、失败/空数据及reload时不会显示上一域的页脚数值。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |

## REQ-036 · 用户仓库导航保留逐步历史

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-036-AC01 | passed | 总览→ubs-engine→选择器ubs-comm→后退，依次回ubs-engine及总览；前进可恢复ubs-comm。 | [ubs-adversarial.json#/checks/history-select](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-036-AC02 | passed | 侧栏、仓库链接、选择器及返回总览遵循同一用户导航历史规则，无重复hashchange造成的额外条目。 | [ubs-adversarial.json#/checks/history-select](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/history-sidebar-back](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-036-AC03 | passed | 旧#repositories/#overview/#prs规范化不制造无意义中间页；未知路由回默认页且不形成循环。 | [ubs-adversarial.json#/checks/legacy-repositories](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/legacy-overview](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/legacy-prs](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/legacy-quality](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/legacy-repo-ubs-comm](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/legacy-repo-ubs-comm-quality](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/legacy-repo-ubs-comm-method](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/legacy-unknown](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-036-AC04 | passed | 历史导航触发的视图、标题、高亮和详情清理与当前路由一致。 | [ubs-adversarial.json#/checks/history-select](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/modal-nav-hash](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/modal-nav-selector](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/modal-nav-sidebar](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/modal-nav-back](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/modal-nav-history](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |

## REQ-037 · 最小fixture遵循当前统计契约

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-037-AC01 | passed | [600,600,900]三条完成样本的线性插值P90为840秒，fixture不能保存900。 | [data-adversarial.json#/cases/fixture-triton.json](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/fixture-triton-zero.json](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/fixture-triton-single.json](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 数据专项逐AC合成/纯函数检查支持该计算与输入契约；不扩展为原始来源或真实运行历史准确性。 |
| REQ-037-AC02 | passed | fixture kind符合当前initial/rerun语义，必要summary均由同一输入独立重算一致。 | [data-adversarial.json#/cases/fixture-triton.json](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/fixture-kinds-triton.json](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/fixture-triton-zero.json](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/fixture-kinds-triton-zero.json](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/fixture-triton-single.json](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/fixture-kinds-triton-single.json](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 数据专项逐AC合成/纯函数检查支持该计算与输入契约；不扩展为原始来源或真实运行历史准确性。 |
| REQ-037-AC03 | partial | 最小数据、合法零数据、单样本、缺值及重跑fixture均可加载；测试直接核对结果，不只检查字段存在。 | [data-adversarial.json#/cases/fixture-triton.json](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/fixture-triton-zero.json](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/fixture-triton-single.json](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 最小/零/单样本fixture的派生数值已核对；缺值与重跑fixture全部页面加载未完整证明。 |

## REQ-038 · 原始工件补齐及历史影响核验

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-038-AC01 | passed | 提供工件清单、来源、采集时刻/窗口、SHA-256及与冻结快照的关联；缺失项目继续明确标为未验证。 | [delivery-evidence-review.json#/acceptance_review/REQ-038-AC01](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Inventory lists current frozen artifact hashes/windows and honestly marks eight missing categories; this satisfies inventory transparency, not source completion. |
| REQ-038-AC02 | unverified | 原始时间、queue三项、PR身份及attempt历史分别完成独立比对，并给出一致/差异/缺证据数量与身份明细。 | [delivery-evidence-review.json#/acceptance_review/REQ-038-AC02](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Independent verified_consistent is zero in all four artifact categories; payload/CSV self-consistency is derived evidence and original timestamp/queue/identity/attempt proof remains missing. |
| REQ-038-AC03 | unverified | 用同一真实run的多个attempt证据比较原规则和REQ-014/015规则，输出历史受影响批次数及差异；合成300秒例子不能证明历史真实E2E。 | [delivery-evidence-review.json#/acceptance_review/REQ-038-AC03](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Seven rerun batches have no same-run multiple-attempt raw records or persisted attempt starts; bounds and a synthetic 300-second example do not establish actual affected batches. |
| REQ-038-AC04 | unverified | 真实构建、部署工件和公开JSON的对应关系通过REQ-022核验；本地Pages模拟下载或旧站公开源码抓取不能替代此证据。 | [delivery-evidence-review.json#/acceptance_review/REQ-038-AC04](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) No real controlled merged build/deploy/public JSON correspondence is available; retained report explicitly states unverified. |

## REQ-039 · 并发调度策略与运行证据一致

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-039-AC01 | unverified | 运行中每日任务A、随后pending B及C的受控序列中，记录A是否被取消及B/C实际排队/替换结果，并提供隔离工作流运行ID/事件记录。 | [delivery-evidence-review.json#/acceptance_review/REQ-039-AC01](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Controlled running A/pending B/C real event sequence and isolated workflow run IDs are absent; only a future protocol exists. |
| REQ-039-AC02 | passed | 文档明确cancel-in-progress:false保护running，不能声称默认保留所有pending；测试不得以YAML字面值断言queued任务永不取消。 | [delivery-evidence-review.json#/acceptance_review/REQ-039-AC02](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) README/test naming now distinguish running protection from pending replacement; current static checks agree. |
| REQ-039-AC03 | unverified | 读取可取得的真实运行历史并记录是否影响每日全量更新；没有历史证据时仍标未验证，不推断已线上发生。 | [delivery-evidence-review.json#/acceptance_review/REQ-039-AC03](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Actual workflow history is not read; report honestly remains unverified. Lack of a local remote alone cannot prove a repository was never pushed. |
| REQ-039-AC04 | passed | 本轮不强制启用queue:max；如果以后要求保留所有排队任务，需形成明确的新运行策略及对应验收。 | [delivery-evidence-review.json#/acceptance_review/REQ-039-AC04](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) queue:max is explicitly deferred with a documented future decision; the requirement does not force enabling it. |

## REQ-040 · CI目标运行时兼容性验证

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-040-AC01 | passed | 记录精确Python/Node版本、命令、退出码、失败数及完整日志；相关测试全部通过。 | [python-tests-ci.log](D:/ubs_core_monitor/audit/2026-10-10/evidence/python-tests-ci.log)；[node-tests-ci.log](D:/ubs_core_monitor/audit/2026-10-10/evidence/node-tests-ci.log) root确认当前HEAD同版本WSL重跑Python3.12.3及Node22.23.3；日志记录425 tests OK(skipped=1)、Node122 pass。仅证明目标运行时相关测试执行与结果，1项skip不扩展为该范围通过，不用于推断其他AC。 |
| REQ-040-AC02 | passed | 原有Python79/79与Node34/34只作为原环境基线，不替代3.12/22结果；新增测试数量不受原数量限制。 | [delivery-evidence-review.json#/acceptance_review/REQ-040-AC02](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Original79/34 baseline is labelled historical rather than used as the target-version result. |
| REQ-040-AC03 | passed | 有完整工件时原始审计在目标运行时运行；工件缺失不能因wrapper退出0而报审计通过。 | [delivery-evidence-review.json#/acceptance_review/REQ-040-AC03](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Raw audit failures due to missing artifacts are recorded as not_passed/failed_missing_artifacts, not converted to passed from gate exit0. |
| REQ-040-AC04 | passed | CI工作流声明版本、文档支持版本和交付验证结果一致。 | [python-tests-ci.log](D:/ubs_core_monitor/audit/2026-10-10/evidence/python-tests-ci.log)；[node-tests-ci.log](D:/ubs_core_monitor/audit/2026-10-10/evidence/node-tests-ci.log)；[delivery-evidence-review.json#/acceptance_review/REQ-040-AC04](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) 声明/支持版本为3.12/22；root已确认当前HEAD在Python3.12.3/Node22.23.3重跑，替代专项报告中较早无HEAD绑定的255条历史运行证据。 |

## REQ-041 · UBS代表值和跨仓算法保持正确

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-041-AC01 | unverified | 冻结输入全量203 PR/826批次的代表值、事件时间、任务值及跨仓结果与独立重算一致；x86/ARM/DT有效样本仍为191/203/195。 | [data-adversarial.json#/real/frozen_ubs_original_203_826_status](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[delivery-evidence-review.json#/additional_review](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) 原UBS203PR/826批全量冻结输入未提供，无法重放原事件/任务/代表值全断言。当前193PR/800批重算一致是新输入正确性，数量变化本身不是缺陷。 |
| REQ-041-AC02 | passed | E2E相同按trigger编号确定代表；任务缺失或同类关联不唯一留空，不从其他批次补取。 | [ubs-adversarial.json#/checks/independent-all-metrics](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/tie-ambiguous-tasks](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-041-AC03 | passed | 当前范围success/partial参与跨仓；失败/过期排除且可解释，合法零PR仓库保留。 | [ubs-adversarial.json#/checks/cross-summary-export](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/cross-exclusions](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-041-AC04 | passed | 复合PR主键及批次完整URL唯一；同PR编号跨仓互不污染。新快照验收计算契约，不硬编码旧数量。 | [ubs-adversarial.json#/checks/same-number](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/independent-all-metrics](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |

## REQ-042 · UBS筛选保持PR集合及代表批次

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-042-AC01 | passed | 既有组合筛选的PR身份集合与独立谓词一致，搜索大小写及首尾空格处理保持。 | [ubs-adversarial.json#/checks/filters-combinations](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-042-AC02 | passed | 完整性按已声明条件选择PR，触发请求按事件身份去重；无关联请求及未知来源批次仍可追踪。 | [ubs-adversarial.json#/checks/filters-combinations](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-042-AC03 | passed | 图表/表格总耗时、排队、执行切换均取同一PR代表批次；相同PR在不同筛选中的代表URL不变。 | [ubs-adversarial.json#/checks/tie-ambiguous-tasks](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/page-metrics](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-042-AC04 | passed | 无结果有清晰提示，重置恢复默认PR集合；空值不补0。 | [ubs-adversarial.json#/checks/filters-combinations](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |

## REQ-043 · UBS排序与分页边界保持正确

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-043-AC01 | passed | 仓库P90顺序与独立重算一致；PR三种排序的完整序列及当前页内容正确。 | [ubs-adversarial.json#/checks/sorting-full-pages](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/cross-summary-export](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-043-AC02 | passed | 0/1/15/16/30/31条输入显示正确页数和上一/下一页禁用状态；0条时为1/1及无记录。 | [ubs-adversarial.json#/checks/pages-0](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/pages-1](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/pages-15](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/pages-16](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/pages-30](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/pages-31](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-043-AC03 | passed | 筛选缩页回第一页，结果变化导致页码越界时约束到合法页；末页不重复或遗漏记录。 | [ubs-adversarial.json#/checks/pages-0](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/pages-1](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/pages-15](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/pages-16](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/pages-30](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/pages-31](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-043-AC04 | passed | 浏览器导航或耗时类型切换后的页码、排序说明与显示数据一致。 | [ubs-adversarial.json#/checks/page-metrics](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |

## REQ-044 · UBS四类CSV内容与格式保持正确

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-044-AC01 | passed | PR导出不受15行分页限制，代表trigger及E2E/三类任务三种耗时字段均正确且单位毫秒；各行包含正确仓库。 | [ubs-adversarial.json#/checks/filters-combinations](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/sorting-full-pages](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-044-AC02 | passed | 九仓CSV包含状态、纳入标志、样本与覆盖率；质量CSV数量与当前质量记录一致。 | [ubs-adversarial.json#/checks/cross-summary-export](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/quality-export](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-044-AC03 | passed | 批次CSV包含全部任务明细、有效与代表标志，与详情来源绑定一致。 | [ubs-adversarial.json#/checks/real-detail-csv](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-044-AC04 | passed | 中文、逗号、引号、换行及公式前缀可正确往返解析；本地保存与Pages Blob下载内容一致，失败提示明确且可重试。 | [ubs-adversarial.json#/checks/csv-special-failure-retry](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/pages-actual-download](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |

## REQ-045 · UBS正常详情与下钻能力保持

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-045-AC01 | passed | 正常PR详情完整显示所有批次、代表标注和任务时间线；未知关联按REQ-016处理。 | [ubs-adversarial.json#/checks/real-detail-csv](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-045-AC02 | passed | 最长E2E、历史失败等待和质量记录都打开正确仓库PR与对应批次；后续成功不抹去历史失败。 | [ubs-adversarial.json#/checks/drilldown-targets](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-045-AC03 | passed | Esc、关闭按钮及外部点击关闭；再次打开其他PR不残留旧内容，源PR/trigger/任务链接对应当前记录。 | [ubs-adversarial.json#/checks/close-modes](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-045-AC04 | passed | UI分钟显示与毫秒原值一致，精确值可查看；取消终态纳入既有失败等待语义，不作为质量失败的同义词。 | [ubs-adversarial.json#/checks/minutes-exact-cancelled](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |

## REQ-046 · Triton统计及数据边界保持真实

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-046-AC01 | partial | 冻结输入的38 PR/66批、65完成样本、48NPU排队点及summary独立重算一致；两图选区样本/平均/P50/P90与适用集合重算一致。 | [data-adversarial.json#/cases/original-triton-freeze-summary](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/current-triton-summary](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[triton-adversarial.json#/checks/FROZEN-G-6](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) 原Triton38PR/66批/65完成/48NPU及当前44PR/80批独立重算通过；两图全部选区平均/P50/P90尚无完整逐项浏览器证据。quality接受篡改summary的反例归REQ-019-AC02，不能把新数量本身判失败。 |
| REQ-046-AC02 | passed | 全部66个近似起点标记仍如实可见；9条NPU时间倒置涉及5批的排队未知及warning保留，不删除记录或补0来消除缺陷。 | [data-adversarial.json#/cases/current-triton-npu-and-boundaries](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/current-triton-quality-retains-warnings](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/original-triton-freeze-queue-warning-preservation](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 数据专项逐AC合成/纯函数检查支持该计算与输入契约；不扩展为原始来源或真实运行历史准确性。 |
| REQ-046-AC03 | partial | UBS的12个无trigger请求、6批无唯一请求、17不完整、2运行中、16取消边界继续可追踪；两域粒度及取消统计区别明确。 | [data-adversarial.json#/real/ubs_gaps](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 当前UBS12无trigger、6无唯一请求、17不完整、16取消仍可重算追踪，运行中为1；原203/826输入缺失，不能完整重放原2运行中及所有UI披露。数量变化不是缺陷。 |
| REQ-046-AC04 | partial | 合法零NPU、零批次、单样本和缺值分别表达；新数据按契约计算，不固定未来数量为旧快照值。 | [data-adversarial.json#/cases/fixture-triton-zero.json](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json)；[data-adversarial.json#/cases/fixture-triton-single.json](D:/ubs_core_monitor/audit/2026-10-10/evidence/data-adversarial.json) 零/单样本与当前新数据派生通过；全部页面缺值与零NPU区别未完整核验。 |

## REQ-047 · 全部视图与旧链接可达性保持

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-047-AC01 | passed | 每个仓库单仓和质量深链接直接打开时，数据归属、标题、计数和导航高亮正确。 | [ubs-adversarial.json#/checks/deep-ubs-engine](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/deep-ubs-engine-quality](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/deep-ubs-comm](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/deep-ubs-comm-quality](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/deep-ubs-virt](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/deep-ubs-virt-quality](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/deep-ubs-io](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/deep-ubs-io-quality](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/deep-ubs-mem](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/deep-ubs-mem-quality](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/deep-OmniStateStore](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/deep-OmniStateStore-quality](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/deep-ham](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/deep-ham-quality](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/deep-ubturbo](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/deep-ubturbo-quality](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/deep-ubs-atomic](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/deep-ubs-atomic-quality](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-047-AC02 | passed | #repositories→#ubs；#overview/#prs→ubs-engine单仓；#quality→ubs-engine质量；既有#repo/NAME及method别名按Router契约可达。 | [ubs-adversarial.json#/checks/legacy-repositories](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/legacy-overview](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/legacy-prs](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/legacy-quality](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/legacy-repo-ubs-comm](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/legacy-repo-ubs-comm-quality](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/legacy-repo-ubs-comm-method](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json)；[ubs-adversarial.json#/checks/legacy-unknown](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-047-AC03 | passed | 未知路由按默认规则回总览，未知仓库显示未获取或明确无此仓库，不能借其他仓数据。 | [ubs-adversarial.json#/checks/unknown-repo](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) UBS专项逐AC结果及对应浏览器/合成检查已执行，支持本项完整条件。 |
| REQ-047-AC04 | unverified | 旧站能力清单每项都有合并位置及代表验证证据；重复视觉模板/长表抽查范围声明准确，不把代表组合称为穷举。 | [ubs-adversarial.json#/acceptance/REQ-047-AC04](D:/ubs_core_monitor/audit/2026-10-10/evidence/ubs-adversarial.json) Capability mapping and review of sampling claims is owned by root document synthesis. |

## REQ-048 · 多浏览器与指针触屏操作保持

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-048-AC01 | partial | Chrome 1440×1000、1024×768、390×844下21主要视图可访问，整页无意外横向溢出；宽表可在自身滚动容器内滚动。 | [triton-adversarial.json#/checks/RESPONSIVE-EVIDENCE](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json)；[triton-adversarial.json#/checks/MOBILE-HEADER](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) Chrome390/1024/1440及五档时间窗已保存实际截图/坐标；人工阅读、所有21视图或旋转/尺寸变化的完整验收尚未完成。 |
| REQ-048-AC02 | unverified | 时间窗口整体/左右边界拖拽、空白跳转及五档快捷选择正确且不越界；触屏拖动不被页面滚动错误抢占。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-048-AC03 | partial | 散点悬浮、点击固定、外部取消、触屏卡片、批次点击展开及源链接继续工作。 | [triton-adversarial.json#/checks/KEY-TIP](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) 键盘固定与关闭详情有直接证据；全部悬浮/外部取消/触屏卡片/批次展开及源链接未在本轮完整核验。 |
| REQ-048-AC04 | partial | Edge两图挂载、时间选择、跨域导航及浏览器历史回归通过，运行日志无新增页面脚本错误。 | [triton-adversarial.json#/checks/EDGE-UBS](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json)；[triton-adversarial.json#/checks/EDGE-TRITON](D:/ubs_core_monitor/audit/2026-10-10/evidence/triton-adversarial.json) Edge九仓总览与Triton6h14批通过；跨域导航及前进/后退全部路径未完整证明。 |

## REQ-049 · 新鲜度与异常/空态表达保持

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-049-AC01 | unverified | Triton按北京时间08:00/13:00/18:00/20:00计划及90分钟宽限判断；旧08:17快照在13:00槽位到14:30仍未更新时显示延迟。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-049-AC02 | unverified | 提醒表达最后成功快照及应检查Actions，不把数据延迟直接说成已证明采集失败；采集时间和数据窗口分别显示。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-049-AC03 | unverified | 导出HTTP500后提示具体失败并恢复按钮；无匹配、零NPU、脚本/数据读取失败不显示同一伪造零值。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |
| REQ-049-AC04 | unverified | 跨域返回或重复刷新不积累定时器/监听器，当前域提示与最后有效数据一致。 |  本轮允许读取的专项证据未证明此验收标准的全部条件；未验证不代表失败。 |

## REQ-050 · 需求验收记录与证据闭环

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-050-AC01 | failed | 每个REQ及AC都有通过/失败/未验证/N/A状态、版本、输入和证据；截图生成或测试进程退出0本身不能替代验收。 | [delivery-evidence-review.json#/acceptance_review/REQ-050-AC01](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) The ledger derives all AC statuses from commit names and blindly copies each REQ status; hollow evidence, hidden associated tests and a missing delivering commit still produce195 AC passed. |
| REQ-050-AC02 | passed | F01–F19和D10/P04等未验证结论全部映射，无源问题遗漏；19组问题拆分为多条需求不被误计成新增审查问题。 | [delivery-evidence-review.json#/acceptance_review/REQ-050-AC02](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) F01-F19, D10/P04 mapping, fixed counts and source hashes are structurally verified. |
| REQ-050-AC03 | partial | 修复后的相关失败检查转通过并保持正确能力；不得删除记录、补零或放宽验收使结果通过。 | [delivery-evidence-review.json#/acceptance_review/REQ-050-AC03](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Frozen failed checks are preserved, but no per-AC post-fix re-evaluation links every old failure to actual proof; fresh counterexamples remain despite all-commit pass. |
| REQ-050-AC04 | failed | 真实快照、合成输入、静态规则、真实部署证据分别标注；238项检查不能直接合成来源准确率。 | [delivery-evidence-review.json#/acceptance_review/REQ-050-AC04](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Input kinds are hardcoded by REQ/type; REQ040 is labelled real deployment although its records are local target-runtime tests and actual deployment is absent. Hollow evidence is accepted. |

## REQ-051 · 完整需求文档的版本与可追溯交付

| AC | 状态 | 验收条件 | 证据与判断 |
|---|---|---|---|
| REQ-051-AC01 | passed | 文档51个REQ编号连续唯一，每项至少3条带唯一AC编号的可验证验收标准；所有源结论有追踪表。 | [delivery-evidence-review.json#/acceptance_review/REQ-051-AC01](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Document has51 unique consecutive requirements and195 uniquely numbered ACs with the required structure and tracking. |
| REQ-051-AC02 | passed | 明确37条整改、3条补证、9条保持、2条交付的分类；“保持”是已有正确能力，“补证”不是已确认线上故障。 | [delivery-evidence-review.json#/acceptance_review/REQ-051-AC02](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) 37 remediation/3 evidence/9 preservation/2 delivery classifications are explicit and structurally checked. |
| REQ-051-AC03 | passed | 需求来源文件SHA-256可核验，原审查报告、证据、业务文件未改变；所有本地文档链接有效。 | [delivery-evidence-review.json#/acceptance_review/REQ-051-AC03](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) Frozen source hashes and document baseline match; existing document validation covers local links and attribution; this audit does not change frozen evidence. |
| REQ-051-AC04 | failed | 总体验收结论只有必需目标与证据均完成时才标完成，缺原始证据/真实历史仍保留未验证。 | [delivery-evidence-review.json#/acceptance_review/REQ-051-AC04](D:/ubs_core_monitor/audit/2026-10-10/evidence/delivery-evidence-review.json) check_overall demands51 passed/zero unverified while source evidence is incomplete; truthfully markingREQ038/039 unverified is rejected. Document overall verified is a structural result, not delivery completion. |

运行时说明：当前HEAD目标版本Python3.12.3/Node22.23.3重跑记录支持REQ-040运行时AC；425 tests OK(skipped=1)/122 pass不用于推断其他验收。

此矩阵只修改本轮矩阵文件；旧需求、旧证据与业务代码均保持不变。源审查实际执行了对应验证，矩阵整理没有额外触发采集、部署、浏览器或其他测试。
