/* Generate the review from independent evidence; never mutate the product or frozen audit. */
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const ROOT=path.resolve(__dirname,'../../..'),OUT=path.resolve(__dirname,'..'),E=OUT+'/evidence';
const read=n=>JSON.parse(fs.readFileSync(E+'/'+n+'.json','utf8'));
const head=read('tracked-before').head;
const findings=[];
function add(id,p,reqs,title,location,repro,expected,actual,impact,fix,evidence,kind='合成输入或内存反例'){
 findings.push({id,priority:p,reqs,title,location,reproduction:repro,expected,actual,impact,recommendation:fix,evidence,input_kind:kind,status:'confirmed'});
}
add('A01','P1',['REQ-050','REQ-051'],'验收台账由提交名称推断全部AC通过','scripts/verify_acceptance.py:530',
 ['运行 delivery-probes.py 的 baseline_acceptance。','分别清空证据详情仅保留顶层状态、从内存清单隐藏五个相关测试、移除REQ-051提交映射；再运行验收工具。','将REQ-038/039如实设为未验证后，检查REQ-051总体校验。'],
 '每条AC必须有实际验收证据；缺失证据保持未验证，整体验收允许如实表达未完成。','三次反例仍为 verified、195个AC passed；如实填入未验证却被总体工具拒绝。',
 '需求实现提交与验收通过被混为一谈，错误的全部交付结论掩盖真实缺口。','按AC读取具体输入、命令、预期/实际和证据；检查缺证据及反例；文档结构验证与业务交付状态分别输出。',
 ['delivery-evidence-review.json#probes.erase_all_evidence_details_keep_expected_status_only','delivery-evidence-review.json#probes.truthful_unverified_req038_req039_rejected_by_req051']);
add('A02','P1',['REQ-012','REQ-013'],'每日暖缓存恢复后合法新版本无法重写manifest','validate_bundle.py:180',
 ['以当前有效UBS快照及旧manifest模拟恢复缓存A。','仅推进索引generated_at，保持新数据结构合法。','调用生产 main(--write-manifest) 模拟每日重新盖章。'],
 '合法的新采集包B通过内容检查后生成B的清单；增量复用A时仍严格验证A清单。','先用旧A指纹校验B而退出1，manifest_written=false。现有暖链测试从空B目录创建清单，遗漏恢复旧清单的条件。',
 '正常每日更新可能被自身的旧指纹阻断，后续缓存保存和发布不能进行；真实Actions影响未验证。','区分新版本生成和旧版本恢复验证，先完成B内容一致性检查再生成B清单；增加保留A清单的暖链回归。',
 ['delivery-evidence-review.json#probes.daily_refresh_existing_manifest']);
add('A03','P1',['REQ-012','REQ-022'],'缺文件的manifest可通过门禁及发布后验证','validate_bundle.py:171',
 ['将有效manifest.files在内存缩为仅repositories.json，保留原fingerprint。','对完整本地包执行verify。','用该清单调用verify_ubs并记录抓取URL。'],
 '清单文件集合与索引引用、计算指纹完全一致；发布后获取九个仓库的实际快照。','本地计算10个文件、清单记录1个仍verified；发布验证只抓索引便成功，九份快照未校验。',
 '清单损坏可使发布校验遗漏实际页面引用的数据，不能证明上传与公开内容一致。','比对完整files键集合和每项digest，复算清单指纹；部署核验从索引推导所有必需文件，不仅遍历声明清单。',
 ['delivery-evidence-review.json#probes.truncated_manifest_files']);
add('A04','P1',['REQ-015'],'采集入口只获取最新attempt，遗漏历史attempt的jobs','triton/dashboard.py:470',
 ['模拟API返回run_attempt=3。','调用生产collect并记录jobs URL及构建批次。'],
 'attempt1/2/3历史身份及各自jobs均保留，重复采集不重复计数。','只请求 /actions/runs/1/attempts/3/jobs，得到1个批次。聚合器支持attempt身份，但采集入口没有枚举历史。',
 '同一run重跑历史在进入聚合之前已经丢失；影响真实哪些批次仍缺原始工件。','采集各有效attempt及其jobs，保留attempt起点与来源证据；增加从collect入口开始的多attempt测试。',
 ['data-adversarial.json#collector-still-enumerates-only-current-attempt']);
add('A05','P1',['REQ-015'],'固定14天回看遗漏窗口内的旧run重跑','triton/dashboard.py:457',
 ['构造首次创建9月18日、10月8日再次触发的run，当前窗口包含10月8日。','模拟APIcreated过滤并执行生产collect。'],
 '按本次attempt触发时间识别窗口内重跑，即使首次run创建在窗口外。','固定14天created回看找不到该run；批次、attempt和jobs均为0。',
 '扩大短期回看不能保证任意旧run的重跑完整性；真实遗漏规模未验证。','采用可证明覆盖attempt活动的查询或持久化run索引；关联用的窗口外证据不计入窗口批次。',
 ['data-adversarial.json#collector-old-run-beyond-lookback-is-lost']);
add('A06','P1',['REQ-010'],'Triton请求挂起使已完成的UBS持续加载','web/app.js:114',
 ['Chrome直接打开#ubs，拦截Triton JSON并暂不返回。','等待九个UBS仓库响应全部完成。','检查ubsStatus、repositoryIndex及总览行数，再释放被拦截请求。'],
 '独立读取规则要求已完成的健康域可提交并显示数据。','九个UBS响应完成后，ubsStatus仍loading、索引未提交、总览0行；load的Promise.all包含Triton。',
 '慢请求或悬挂请求会跨域阻塞健康数据。该反例针对REQ-010独立读取规则；AC02列举的404/坏JSON另行验收。','按域提交当前generation的结果；设置合理超时和对应提示，保留代次保护。',
 ['triton-adversarial.json#DOMAIN-HANG','../screenshots/triton-triton-hang-blocks-ubs.png'],'真实Chrome＋合成延迟响应');
add('A07','P2',['REQ-018'],'API分页数量漂移及无ID重复页未拒绝','triton/dashboard.py:362',
 ['分页声明total_count由150变100，第二页为空。','另构造无id的重复页。'],
 '数量或身份契约异常应明确失败，不能静默截断或重复计数。','第一种返回100条且未拒绝；无ID重复页返回200条且未拒绝。',
 '缺页或重复结果可进入派生数据；现有缺字段和重复有ID的测试不足以覆盖这些边界。','固定首个total_count并核对后续页、实际数量及必要身份字段；拒绝重复页与身份缺失。',
 ['data-adversarial.json#declared-count-changes-hide-truncation','data-adversarial.json#duplicate-records-without-id']);
add('A08','P2',['REQ-019'],'同SHA辅助workflow掩盖另一workflow时间倒置','triton/quality.py:28',
 ['同SHA提供两条workflow：一条可信触发02:00但01:00已结束，另一条合法开始00:30结束03:00。','构建批次并运行quality门禁。'],
 '逐workflow按其适用起点判断倒置并拒绝异常。','quality.passed=true，errors与warnings均为空；共享起点掩盖单条倒置。',
 '异常workflow能进入通过质量门禁的批次。','逐条核验适用起点，之后再聚合；辅助workflow不能改变另一条的起点证明。',
 ['data-adversarial.json#other-workflow-masks-inverted-applicable-start']);
add('A09','P2',['REQ-019'],'quality未核对as_of、有效耗时和汇总契约','triton/quality.py:15',
 ['分别移除/破坏window_end；提供负数、null、bool、字符串或与起止不符的duration。','修改summary.valid/P90，或给running批次提供NaN观测跨度。','逐个运行质量门禁并独立重算。'],
 '时间边界可解析，完成样本及观测跨度合法，汇总与有效记录一致。','上述输入均可quality.passed=true；例如duration=-1仍summary.valid=1，独立合法样本数为0；错误summary.valid=99同样通过。',
 '前后端有效值过滤已改进，但质量门禁不能阻断矛盾派生数据。Python内存NaN反例不声称浏览器接受非法JSON。','门禁复用严格有限非负数判断，核对起止/as_of和summary；保留取消、未启动、运行中的不同语义。',
 ['data-adversarial.json#invalid-as-of-missing','data-adversarial.json#quality-duration-negative','data-adversarial.json#quality-contradictory-summary','data-adversarial.json#running-nan-observed-span']);
add('A10','P2',['REQ-023','REQ-024'],'来源覆盖分母不满足要求，重复身份可误判verified','source_coverage.py:83',
 ['登记一个适用对象，仅record_derived，然后result。','登记两次相同identity，仅record_verified一次，然后result。'],
 '适用分母与独立已验证、差异、缺证据恒等；重复身份不能破坏分母或误判完整验证。','派生对象分母1，三项合计0；重复身份分母2、verified1、missing0仍status=verified。代码新增的derived桶不满足原三项要求。',
 '覆盖完整程度的数量与状态互相矛盾；派生一致不能排除原始证据缺失。','按唯一适用身份记账；派生一致作为缺来源证据的附加属性，或经明确需求变更后采用可验证的四桶契约。',
 ['delivery-evidence-review.json#probes.derived_without_independent_raw','delivery-evidence-review.json#probes.duplicate_source_identity']);
add('A11','P2',['REQ-024'],'原始排队分项接受bool、负数和非有限数','source_coverage.py:13',
 ['对waitingTimeMillis/blockedTimeMillis/buildableTimeMillis分别注入bool、负数、NaN、Infinity。','调用queue_from_raw并检查返回值。'],
 '非法或缺失原始分项保持未知，不作为有效排队秒数。','isinstance(int,float)接受以上输入，仍返回分项与求和结果。',
 '原始排队核验自身缺少有效值契约；当前真实快照是否受影响未验证。','三项均使用有限、非bool、非负数校验；保留原始分项与拒绝原因。',
 ['delivery-evidence-review.json#probes.invalid_raw_queue_components']);
add('A12','P2',['REQ-025'],'缺原始文件被统一记为failed而非unverified','source_coverage.py:38',
 ['调用failure_report(FileNotFoundError("raw artifact unavailable"))。','核对overall_status与REQ-025-AC02缺证据语义。'],
 '缺工件为unverified；差异和异常分别明确标识，并保留非通过退出/发布保护。','overall_status=failed，所有中止范围共用该分类。',
 '来源缺失与已经发现数据错误混淆，影响补证和修复工作的分流。','单独处理预期缺证据异常；保留error/affected_scope，不能把未知变为通过。',
 ['delivery-evidence-review.json#probes.missing_file_failure_classification']);
add('A13','P2',['REQ-005','REQ-006'],'合法零批次响应清空会话选择','web/triton-view.js:63',
 ['选择main/6小时/搜索/失败状态。','reload得到合法batches=[]，然后reload恢复原合法快照。'],
 '选中但新快照暂不存在的分支及搜索仍保留，结果为空并能清除；恢复后采用原会话选择。','空数据时提前destroy/return，随后恢复为全部分支、72小时、空搜索及all状态。',
 '短暂无数据会悄然扩展用户查询范围并丢失上下文；同范围正常刷新通过。','会话状态独立于已挂载视图持有；空态也渲染选择标识和恢复提示，不能销毁唯一状态。',
 ['triton-adversarial.json#EMPTY-RESTORE','../screenshots/triton-empty-erases-context.png'],'真实Chrome＋合成空/恢复响应');
add('A14','P2',['REQ-006','REQ-010'],'无效采集窗被当成成功空数据','web/app.js:111',
 ['保留合法批次数组，仅令window_start="invalid-date"。','直接打开Triton并检查状态和正文。'],
 '按REQ-006规则：无合法新窗应作为加载失败处理，区别于合法零批次。','tritonStatus=ok，视图显示暂无数据；加载入口仅检查batches为数组。',
 '损坏时间边界被隐瞒成空结果，用户不能区分失败与零数据。','在提交payload前核验有限有序采集窗及必要数据字段，错误进入failed。',
 ['triton-adversarial.json#INVALID-WINDOW','../screenshots/triton-invalid-window-marked-ok.png'],'真实Chrome＋合成坏字段');
add('A15','P2',['REQ-001'],'合法__proto__分支没有筛选入口','web/triton-view.js:406',
 ['git check-ref-format refs/heads/__proto__返回0。','在响应内保留一个合法批次并令base_branch=__proto__。','打开Triton分支选择。'],
 '每个合法分支可在单选/多选谓词中明确选择。','branchOptions的input数组为空，使用普通对象计数触发原型键行为。',
 '该分支数据可显示却不能选择；当前正式快照未发现此分支。','使用Map或Object.create(null)计数，补充原型属性名称的分支测试。',
 ['triton-adversarial.json#BRANCH-PROTOTYPE','../screenshots/triton-prototype-branch-missing.png'],'真实Chrome＋合法Git分支合成输入');
add('A16','P2',['REQ-008'],'弹窗同步关闭后处理函数仍可导出旧PR','web/app.js:108',
 ['打开ubs-engine PR1600详情。','同一JavaScript任务执行 dialog.close(); exportBatches();，拦截导出POST。'],
 'REQ-008-AC04要求已关闭详情的按钮或处理函数不能导出上一PR。','dialog.open=false，但旧detailPR仍绑定；发出一个ubs-engine-pr-1600-batches.csv。close事件随后才清引用。',
 '属于同步处理函数边界；正常导航清理和等待close事件后的导出保护通过，不声称普通切仓存在错仓导出。','导出入口检查弹窗有效打开及绑定上下文，关闭入口同步失效引用。',
 ['ubs-adversarial.json#closed-export-race','../screenshots/ubs-038-closed-export-race.png'],'真实Chrome＋同步关闭边界');
fs.writeFileSync(E+'/findings.json',JSON.stringify({head,generated_at:new Date().toISOString(),findings},null,2)+'\n');
const before=read('tracked-before');const changed=[],missing=[];
for(const f of before.files){const p=path.join(ROOT,f.path);if(!fs.existsSync(p)){missing.push(f.path);continue;}const hash=crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');if(hash!==f.sha256)changed.push(f.path);}
fs.writeFileSync(E+'/protected-files-verification.json',JSON.stringify({head,tracked_files:before.files.length,changed,missing,unchanged:!changed.length&&!missing.length,executed_at:new Date().toISOString()},null,2)+'\n');
let matrix;try{matrix=read('acceptance-matrix');}catch(e){console.log('Findings and protected-file check saved; waiting for coverage matrix.');process.exit(0);}
const tr=read('triton-adversarial'),ub=read('ubs-adversarial'),da=read('data-adversarial');
const local=(label,rel)=>`[${label}](D:/ubs_core_monitor/audit/2026-10-10/${rel})`;
let s=`# UBS × Triton：51项需求交付对抗审查\n\n审查日期：2026-10-10。对象：${head}，本地服务 http://127.0.0.1:8765/#ubs。验收基准为冻结的51项独立需求及195条AC。\n\n**结论：完整交付尚未成立，需整改并补证。** 发现${findings.length}项可重复代码/验收工具缺陷；提交名称及单元测试通过不能替代逐AC验收。原始来源、历史attempt、真实并发和正式部署证据仍缺失。\n\n## 验收范围与证据\n\n${local('逐REQ/AC覆盖矩阵','coverage-matrix.md')}覆盖全部51项、195条标准；${local('机器可读矩阵','evidence/acceptance-matrix.json')}记录每条结果和理由。通过仅表示对应记录和操作已满足标准；部分完成和未验证均不计完整交付。矩阵汇总：\n\n\`\`\`json\n${JSON.stringify(matrix.summary||matrix.counts||{},null,2)}\n\`\`\`\n\n- 当前数据为UBS 193 PR/800批、Triton 44 PR/80批，独立重算未发现计算差异；新旧数量变化本身不是缺陷。\n- 原Triton冻结38 PR/66批fixture可重放，五档窗口1/13/64/66/66、65有效完成、48排队点等核验通过。原UBS203 PR/826批的完整事件/任务输入未保留，不能仅凭历史哈希和报告完成REQ-041-AC01。\n- UBS真实Chrome检查${ub.summary.checks}项：${ub.summary.passed}通过、${ub.summary.failed}失败；九个仓库及质量页深链接、筛选代表值、排序分页、详情分组、四类CSV已检查。CSV的31次POST均拦截，Blob真实下载与POST原始字节对比，不写正式导出目录。\n- Triton真实Chrome检查${tr.checks.length}项：${JSON.stringify(tr.counts)}。覆盖冻结及当前五档时间、局部状态、搜索策略、刷新/跨域、空数据恢复、键盘及Edge代表路径；响应式检查保留截图/坐标，完整旋转与21视图所有宽度不凭代表图声明通过。\n- Python数据对抗${da.counts.cases}个case：${da.counts.passed}满足、${da.counts.failed}反例。测试入口I/O均模拟；真实历史影响与代码反例分开。\n- 本轮CI目标版本Python3.12.3：425项，失败/错误0，跳过1；Node22.23.3：122项全部通过。日志${local('Python','evidence/python-tests-ci.log')}、${local('Node','evidence/node-tests-ci.log')}。Windows直接运行的cache-chain shell shim有7项环境失败；同代码在WSL目标环境通过，未把跨平台测试环境错误当作生产缺陷。\n\n数据回归脚本的10项结果为4通过、6显式expectedFailure，六项记录未满足的AC；不计为六个功能通过。审查文档、证据和保护文件校验另见${local('审查产物验证','evidence/audit-validation.json')}。\n\n## 已确认问题\n\n下列问题按独立原因分组。同一缺陷的多种输入不会重复算为多个需求。P1优先修复；P2在对应需求验收前关闭。\n\n`;
for(const f of findings){s+=`### ${f.id} · ${f.priority} · ${f.title}\n\n- **需求/位置：** ${f.reqs.join('、')}；[${f.location}](D:/ubs_core_monitor/${f.location})。\n- **输入类型：** ${f.input_kind}。\n- **复现：** ${f.reproduction.map((x,i)=>`${i+1}. ${x}`).join(' ')}\n- **预期：** ${f.expected}\n- **实际：** ${f.actual}\n- **影响：** ${f.impact}\n- **修复建议：** ${f.recommendation}\n- **证据：** ${f.evidence.map(x=>{const [file,key]=x.split('#');return local(file+(key?' → '+key:''),'evidence/'+file)}).join('；')}。JSON后的标识是检查ID或对象路径。\n\n`;}
s+=`## 尚未满足的补证与复验\n\n|需求|缺口|关闭条件|\n|---|---|---|\n|REQ-038|SQLite、原始缓存、PR/任务来源、同run多attempt及真实构建链路没有齐全独立输入|补齐清单和可重放原始输入，计算真实影响；不能用派生一致证明来源准确|\n|REQ-039|真实running A/pending B/C序列和可信工作流历史未核对|提供运行ID/日志及逐事件验证；当前需求不强制启用queue:max|\n|REQ-022、REQ-038|没有当前构建到实际公开JSON的完整部署记录|在授权的隔离链路取得构建、清单、公开URL和所有文件指纹一致证据|\n|REQ-041-AC01|原UBS203/826全量输入不可重放|恢复当时全部事件、批次、任务输入后重算；当前193/800通过可保留|\n|矩阵中其余部分/未验证条目|组合、交互或环境证据不足以覆盖整条标准|按矩阵具体缺口补足；不以已有提交批量赋passed|\n\n先关闭A01并修正真实验收状态，再处理P1采集、发布和域隔离反例；每项修复应从本报告输入复跑并保留对应AC证据。报告未修复业务代码、刷新采集或触发部署。\n\n## 复现与保护\n\n浏览器脚本使用本机Chrome/Edge和bundled Playwright，均只写本审查目录；collector/API/manifest反例通过模拟或内存篡改产生，未改正式快照。${local('原文件保护校验','evidence/protected-files-verification.json')}核对审查前${before.files.length}个受跟踪文件；变动${changed.length}、缺失${missing.length}。\n\n\`\`\`powershell\n# 在仓库根目录使用Python3.12执行；只生成今日审计证据\npython -B audit/2026-10-10/scripts/data-adversarial.py\npython -B audit/2026-10-10/scripts/data-adversarial-tests.py\npython -B audit/2026-10-10/scripts/delivery-finalize.py\nnode audit/2026-10-10/scripts/ubs-adversarial.cjs\nnode audit/2026-10-10/scripts/triton-adversarial.cjs\nnode audit/2026-10-10/scripts/fault-adversarial.cjs\nnode audit/2026-10-10/scripts/compose-report.cjs\npython -B audit/2026-10-10/scripts/test_audit_artifacts.py\n\`\`\`\n\n补充${local('故障和乱序响应检查','evidence/fault-adversarial.json')}12项全部通过、页面脚本错误0：UBS索引404/坏JSON时Triton两图和导出可用；Triton404/坏JSON/合法空数据时UBS可用；口径页在双失败或双pending时可见；第一代次迟到成功/失败均未覆盖第二代次。A06专指仍未完成请求导致的跨域阻塞，不将这些已通过的明确故障条件混记为失败。${local('目标运行时记录','evidence/runtime-evidence.json')}绑定当前审查HEAD及测试日志哈希。\n\n冻结上一轮证据、业务源文件、正式JSON及用户已有.playwright-mcp均保留。浏览器合成故障、原始工件缺失和线上实际影响分别记录；未执行新的外网采集或部署。\n`;
fs.writeFileSync(OUT+'/adversarial-review.md',s);console.log('Wrote findings, review, and protected-file evidence.');
