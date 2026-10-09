"""Assemble audit evidence and coverage; never write outside this audit folder."""
import json,hashlib,re
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];AUDIT=ROOT/'audit'/'2026-10-09';E=AUDIT/'evidence'
files=['triton-browser.json','triton-browser-supplement.json','ubs-browser.json','additional-browser.json','data-audit.json','deployment-audit.json','visual-review.json']
data={f:json.loads((E/f).read_text(encoding='utf-8')) for f in files}
checks={}
for f in files:
 for c in data[f]['checks']:
  if c['id']=='triton-real-controls':continue # initial harness error superseded by complete supplement
  checks[c['id']]={**c,'evidence_file':'evidence/'+f}
(E/'all-checks.json').write_text(json.dumps({'checks':list(checks.values()),'counts':dict(Counter(c['state'] for c in checks.values()))},ensure_ascii=False,indent=2),encoding='utf-8')
findings=[
 ('F01','P1','Triton时间筛选与偏长阈值使用不同集合','真实快照/浏览器','T08-6,T08-12,T08-24,T09','web/triton-view.js:165-176,306-319,396-405,458-491','选6小时，再点“查看全部批次”与“耗时偏长”。','图、汇总、列表应同属选区；阈值取该选区完成批次P90。','6小时图1点，汇总/列表66批；选区P90=290秒但偏长图0点（应有1点）。','使用者会把整个72小时统计解释为所选时段；异常分类也与选区不符。','建立统一分支+时间集合；顶部、列表及阈值都引用它，局部状态只影响各图。'),
 ('F02','P1','Triton筛选导出仍输出全量快照','真实快照/浏览器','T16','web/triton-view.js:417-431','选6小时，搜索PR2475，导出批次CSV。','导出当前分支、时间及列表搜索后的全部匹配记录。','应1行，实际66行；本地与Pages下载均可触发。','导出数据与读者选定范围不一致。','导出复用页级分支+时间+搜索集合，排除分页/关注分组限制及图表局部状态。'),
 ('F03','P1','返回或重新加载会清空Triton会话状态','真实快照/浏览器','T17,A02','web/triton-view.js:37-47,160-163; web/app.js:29,59,82','选分支、6小时、搜索、失败及全部列表；切UBS再返回，或重新加载。','各域分别保留会话内筛选与时间选择。','分支清空、时间回72小时、搜索清空、状态回all、列表回关注；reload也重置时间。','连续调查中已选上下文丢失；UBS却保留输入，体验不一致。','将状态独立于视图挂载保存；有效新快照下恢复，失效选项明确提示并按新窗口约束。'),
 ('F04','P1','旧PR详情在切仓后被导出为新仓库','真实快照/浏览器','U34,U35','web/app.js:31-61,72,81','打开ubs-engine PR1600详情，通过哈希切到ubs-comm，点详情导出。','关闭旧详情或保留其原始仓库上下文，CSV归属必须正确。','详情仍为PR1600，但首列为openeuler/ubs-comm，文件名也使用新仓库。','跨仓同编号场景可能把错误来源用于分析或问题定位。','导航时关闭/清空详情；详情实体同时保存仓库和快照标识，导出使用详情自身上下文。'),
 ('F05','P1','连续刷新较旧响应覆盖较新快照','故障注入/浏览器','F04','web/app.js:82-83','两次触发reload，先请求延迟450ms，后请求先返回。','最后一次刷新结果胜出。','响应顺序2→1，最终collected_at从10月9日回退到10月8日。','指标和新鲜度可能回退到旧数据。','增加加载代次或AbortController；只有当前代次可提交数据与渲染状态。'),
 ('F06','P1','UBS索引失败导致Triton与口径页也不可用','故障注入/浏览器','F01-ubs-index-404','web/app.js:82','打开#triton，拦截UBS索引为404。','单域故障隔离，Triton快照和静态口径仍可访问。','全部视图被隐藏，Triton请求甚至不执行。','UBS故障扩大成整个合并看板不可用。','两域独立读取/验证并分别呈现错误；静态口径不依赖数据加载成功。'),
 ('F07','P1','每日与增量缓存路径版本不一致','静态配置已确认/线上影响未验证','P01','.github/workflows/pages.yml:32-45; .github/workflows/triton-refresh.yml:36-46,131-139','对比两流程cache.path，再按官方缓存版本规则核对。','能够恢复每日更新后的UBS数据。','每日7条路径，增量4条；同key前缀不能跨不同缓存版本命中。','增量可能恢复自身旧UBS缓存并重新发布；实际发生次数未读取Actions历史。','统一共享缓存的路径集合与顺序，或单独发布带版本的UBS工件；增加跨日冷热缓存集成验证。'),
 ('F08','P1','Triton重跑使用原run创建时间且只取当前attempt','合成复现/真实历史影响未验证','S01','triton/dashboard.py:190-209,404-425','输入attempt2：原run00:00创建、本attempt02:00开始、02:05结束。','重跑应保留独立身份、可证明的本次起点，并说明近似边界。','输出7500秒；本attempt已观测跨度为300秒，quality通过；采集只请求最新attempt jobs。','可能把两次运行间隔计为本次耗时，且无法保留此前attempt的完整历史。','保存attempt级证据和历史；优先本次触发事件，否则以可证明的attempt起点近似并标注，不能沿用原run创建时间。300秒是示例已观测跨度，不是已验证的真实提交E2E。'),
 ('F09','P2','详情漏掉非空但失配的事件批次','合成边界/当前真实数据未触发','U37','web/app.js:72','令某批次event_id非空且不在PR.events中，打开详情。','全部批次仍展示，未知关联单独分组。','3批只显示2批；当前826批中这类失配为0。','证据不完整时反而隐藏需要调查的记录。','按已渲染批次集合补齐所有剩余批次，失配关联归入明确的未知事件组。'),
 ('F10','P2','缺失/空串/负耗时被Triton统计当有效样本','合成边界/当前真实数据未触发','S04','web/triton-core.js:53-76,108-116','传入成功null、失败空串、成功-1秒三条。','无效值排除，未知不补零。','有效count为3（应0），null和空串被Number转换成0；当前65个完成样本无此异常。','异常快照可能污染平均值和分位数。','要求原始值是有限非负number，再参与汇总和少样本判断。'),
 ('F11','P2','采集质量门禁放行缺字段或倒置workflow时间','合成边界','S02,S03','triton/dashboard.py:225,297-313; triton/quality.py:12-63','workflow_runs字段缺失，或completed run updated_at早于created_at。','缺字段拒绝；倒置时间作为异常排除/阻断发布。','缺字段返回合法空列表；倒置耗时截成0，quality仍通过。','可能把源异常当合法零数据覆盖旧快照。','验证API必要字段和分页契约；在批次门禁核对起止、状态、观测参照与汇总。'),
 ('F12','P2','发布工件完整性和部署后校验未接入','静态配置已确认','P02,P03','.github/workflows/triton-refresh.yml:90-118; 两流程deploy job; README.md:182','检查fallback错误处理、no-deploy guard及deploy后的步骤。','引用快照齐全且范围可解释；部署后指纹核对兑现文档。','坏索引枚举退出0，单仓下载失败被吞，最后只检查index非空；两个deploy均无verify_deployment。','不完整或混合快照可进入部署，旧数据发布不能被承诺的校验发现。','部署前验证JSON/引用/归属/时间范围；上传并核对构建manifest，部署后使用实际/data/triton.json入口校验。'),
 ('F13','P2','来源审计允许原始证据覆盖为零','静态审计已确认/本地无法完整运行','P05,D10','validate.py:40-44,69; validate_multi.py:98-110','核对raw存在时才比对的分支及最终checks_passed。','结果区分派生一致性与原始来源覆盖。','checked可为0仍写checks_passed=True，queue三项也未独立验证；本地原始工件缺失。','容易将内部一致性误称为来源准确性。','输出证据覆盖率/缺失清单及分项结果，来源校验不足时不得整体宣称通过。'),
 ('F14','P2','搜索后的关注分组说明与实际退化策略矛盾','真实快照/浏览器','A01','web/triton-view.js:396-405; web/triton-core.js:108-116','搜索PR2455后回关注列表。','少样本提示与实际组名/策略一致。','组名“耗时最长1”，旁注仍写“优先显示超过P90”。','用户无法判断列表是异常样本还是少样本中的最长项。','搜索只筛选全局关注集合或说明当前退化策略；组名、阈值和样本说明使用同一上下文。'),
 ('F15','P2','键盘不能操作Triton滑块和批次展开入口','浏览器/DOM','T26,T27','web/triton-view.js:92,362-371,405,472-493','使用Tab/方向键/Enter访问时间滑块、散点、批次行。','关键交互可聚焦并能通过键盘操作，slider值可读。','slider无tabindex及aria值，行是不可聚焦div，仅pointer/click绑定。','键盘用户无法完成下钻和时间选择；触屏拖动本身通过。','补可聚焦语义和键盘事件，正确维护范围ARIA值与焦点；散点提供等价列表入口。'),
 ('F16','P2','手机顶栏裁切、横轴拥挤及导航缺视觉说明','截图人工确认/浏览器几何','A10,M01,V-mobile-nav-label','web/style.css:521-529,557-565; web/triton-view.js:202-205,245-248','390×844打开Triton，查看顶栏及两图横轴。','动作文字在顶栏内，日期刻度不重叠，图标导航易识别。','reload上沿-23.5px/下沿86.5px越过64px顶栏；7个完整时间刻度重叠并裁边；导航font-size:0且无title。','小屏读取时间和识别动作受影响；DOM保留导航文字，不等同于屏幕阅读器没有名称。','顶栏小屏换行/收起或图标按钮加标签；刻度数量随宽度调整，端点对齐；导航提供可见说明或tooltip。'),
 ('F17','P2','Triton共享顶栏和仓库链接仍指向UBS','真实快照/浏览器','A03','web/index.html:40-41; web/app.js:45-59','先看UBS总览，再进入Triton。','分支、代码仓链接和页脚属于当前域或明确标注为共享信息。','顶栏仍master、代码仓链接GitCode UBS；页脚残留9 REPOSITORIES/203 PR。','容易误读当前仓库、分支与统计粒度。','按domain更新共享外壳的分支、源链接和页脚；多分支时明确表达。'),
 ('F18','P2','仓库选择器替换历史使后退跳过上一仓库','真实快照/浏览器','A05','web/app.js:28,83','总览点击ubs-engine，用选择器切ubs-comm，再后退。','浏览器后退逐步返回上一仓库。','直接回#ubs，ubs-engine历史已被replaceState覆盖。','跨仓比较时后退行为与普通侧栏链接不同。','用户导航用pushState或标准hash跳转，仅旧链接规范化用replaceState，并回归前进/后退。'),
 ('F19','P3','最小fixture的P90与实际统计契约不一致','测试fixture','S05','tests/fixtures/minimal/triton.json:225','重算三条完成样本[600,600,900]。','线性插值P90=840秒。','fixture summary写900秒；真实快照summary重算正确。','开发最小数据可能掩盖统计不一致或导致误验收。','更正fixture派生值并验证fixture与当前kind/统计契约。')
]
findings=[dict(zip(['id','priority','title','evidence_kind','check_ids','location','steps','expected','actual','impact','proposed_fix'],x)) for x in findings]
(E/'findings.json').write_text(json.dumps(findings,ensure_ascii=False,indent=2),encoding='utf-8')
matrix=['# 审查覆盖矩阵','','正常路径覆盖独立视图和控件；边界与故障输入另列。重复ID采用最终补充检查，最初的审查脚本错误已被完整重跑替代。计数是检查项数量，不是准确率。','', '| ID | 检查 | 结果 | 输入/证据 |','|---|---|---|---|']
for c in checks.values():matrix.append('|'+ '|'.join([c['id'],c.get('label','').replace('|','/'),{'passed':'通过','failed':'失败','unverified':'未验证'}.get(c['state'],c['state']),c.get('kind','当前快照/代码/截图')+'；['+c['evidence_file']+']('+c['evidence_file']+')'])+'|')
(AUDIT/'coverage-matrix.md').write_text('\n'.join(matrix),encoding='utf-8')
# Component-based ten-category record; scenario rows do not define denominators.
cats=[('usefulness','看板用途与完整性'),('clarity','分析表达清晰度'),('visual','视觉与交互一致性'),('authority','来源权威与置信度'),('accuracy','数值与计算准确性'),('within','图内数值与说明一致'),('details','完整来源详情'),('cross','跨组件与导出一致'),('quality','数据质量保护'),('conclusion','结论支持')]
categories=[{'id':i,'label':label,'applicable':i!='conclusion','assessment':'详见审查报告及覆盖矩阵。',**({'reason':'看板没有提出因果或决策性结论；记录的是实际耗时、状态与样本。'} if i=='conclusion' else {})} for i,label in cats]
rev=hashlib.sha256((E/'protected-files-before.json').read_bytes()).hexdigest();units=[]
def unit(id,label,kind,categories_ids,ids):
 categories_data={}
 for cat in categories_ids:
  cs=[]
  for cid in ids:
   c=checks[cid];cs.append({'id':cid,'state':c['state'],'revision':rev,'evidence':[c['evidence_file']+'#'+cid] if c['state']!='unverified' else []})
  categories_data[cat]={'checks':cs,'findings':[{'id':f['id'],'status':'open','checkIds':[c for c in f['check_ids'].split(',') if c in ids and checks[c]['state']=='failed']} for f in findings if any(c in ids and checks[c]['state']=='failed' for c in f['check_ids'].split(','))]}
 units.append({'id':id,'label':label,'kind':kind,'revision':rev,'categories':categories_data})
unit('ubs-overview','UBS九仓总览','component',['usefulness','accuracy','visual'],['U01','U02-all','U04-name','D07','M02'])
for e in data['deployment-audit.json']['legacy_sources']:
 pass
idx=json.loads((ROOT/'web/data/repositories.json').read_text(encoding='utf-8'))
for e in idx['repositories']:
 n=e['name'];unit('ubs-'+n,'单仓 '+n,'component',['usefulness','accuracy'],['U05-'+n,'U07-'+n,'D01-'+n,'D02-'+n]);unit('quality-'+n,'数据质量 '+n,'component',['usefulness','quality'],['U08-'+n,'U09-'+n])
unit('method','统计口径','component',['usefulness','clarity'],['U10-method','M02'])
unit('triton','Triton趋势与全局上下文','component',['usefulness','clarity','visual','cross'],['T01','T08-6','T09','T17','A02','A01','A03'])
unit('ubs-calcs','UBS代表值与批次任务值','claim',['accuracy','quality'],['D03','D04','D05','D06'])
unit('triton-e2e','Triton E2E散点与统计','component',['accuracy','within'],['T02','A12-e2e-all','A13-e2e','D08','D09'])
unit('triton-npu','NPU散点与排队统计','component',['accuracy','within','quality'],['T03','A12-npu-all','A13-npu','D09'])
unit('ubs-detail','UBS详情完整性与归属','component',['visual','details','cross'],['U24','U25','U34','U35','U37','M03'])
unit('triton-detail','Triton悬浮与批次明细','component',['visual','details'],['T18','T19','T20','T21','T28'])
unit('ubs-export','UBS四种CSV与安全转义','comparison',['cross'],['U21','U22','U23','U26','U29','U31','U38','A11'])
unit('triton-export','Triton CSV筛选对应','comparison',['cross'],['T16','T29'])
unit('reload','共享重新加载/故障隔离','control',['visual','quality'],['F04','F01-ubs-index-404','F01-triton-404','F03-triton-404'])
unit('source','原始来源和历史attempt证据','question',['authority','details'],['D10'])
unit('collector-gate','采集质量门禁边界','control',['quality'],['S01','S02','S03','S04'])
unit('publish-gate','缓存与发布工件一致性','control',['quality','authority'],['P01','P02','P03','P05'])
unit('mobile','手机布局与刻度','component',['visual','clarity'],['V-mobile-triton','V-mobile-nav-label','A10','M01'])
unit('keyboard','键盘关键控件','control',['visual'],['T26','T27'])
unit('history','仓库历史导航','control',['visual'],['A05','A06'])
unit('search-note','关注列表样本说明','component',['clarity','within'],['A01'])
for c in categories:
 if c['applicable']:c['assessment']={'usefulness':'21个主要视图均有入口与数据验证；Triton全页时间联动未达标。','clarity':'口径主要定义保留；选区、搜索提示、共享外壳与手机显示存在已复现偏差。','visual':'Chrome三种宽度截图和Edge关键路径已检查；键盘、手机和跨域状态存在问题。长表重复行采用抽查。','authority':'当前提供的是派生快照；原始平台和历史attempt证据缺失。发布配置不能替代真实部署历史验证。','accuracy':'203 PR、826批次及Triton66批派生值全量重算一致；该结论不证明原始来源准确。','within':'正常选区的两图统计与独立重算一致；搜索分组说明有偏差。','details':'正常详情可追溯至原始链接；失配事件合成边界漏批，原始证据未提供。','cross':'UBS正常导出通过；Triton过滤/导出、跨域状态和切仓详情存在不一致。','quality':'缺值/故障/合成时间边界暴露门禁和发布保护不足。','conclusion':''}[c['id']]
(E/'coverage.json').write_text(json.dumps({'version':1,'artifact':{'identity':'ubs-triton-merged-dashboard','revision':rev,'view':'21 major views; named shared controls and metric groups'},'categories':categories,'units':units},ensure_ascii=False,indent=2),encoding='utf-8')
counts=dict(Counter(c['state'] for c in checks.values()));d=data['data-audit.json'];pc=Counter(f['priority'] for f in findings)
lines=['# UBS × Triton 合并看板审查报告','', '**结论：需要修订（Needs revision）。** 本地合并版的主要视图与现有派生数据已完成审查，但交互逻辑未达到本轮确认的验收预期。发现 '+str(len(findings))+' 组问题/风险（P1 '+str(pc['P1'])+'、P2 '+str(pc['P2'])+'、P3 '+str(pc['P3'])+'）；没有修改业务代码、正式快照或部署。','', '**完整性：已完成当前目录可支持的视图、控件、派生数据及静态链路审查；原始来源与真实部署历史验证为 Partial。** 长表重复行、相同模板的重复视觉内容采用抽查，未穷举全部筛选组合。','', '## 基准与证据','', '- 验收按README及用户确认：时间/分支全页联动、图状态局部、搜索仅列表、选区P90、按当前筛选导出、两域会话状态分别保留。','- Chrome实际运行桌面1440×1000、平板1024×768、手机390×844；Edge补做挂载、时间筛选与跨域导航。触屏拖动和触屏卡片通过；键盘关键路径有缺陷。','- 独立浏览器和请求拦截用于故障/边界；本地POST导出被拦截保存到审查目录，Pages Blob下载使用本地资产模拟Pages origin；没有向公开站点写入。','- [覆盖矩阵](coverage-matrix.md)、[全量检查结果](evidence/all-checks.json)、[数据重算](evidence/data-audit.json)、[旧站能力对照](evidence/baseline-comparison.md)、[截图总览](screenshots/contact-sheet.png)。','- 检查项计数：'+str(counts.get('passed',0))+'通过、'+str(counts.get('failed',0))+'失败、'+str(counts.get('unverified',0))+'未验证。检查项不是组件准确率；同一个问题可使多项检查失败。','- 计划阶段现有单测Python79/79、Node34/34通过，当前业务文件保持相同版本；这些测试不覆盖完整DOM交互。','', '## 数据结论','', '| 域 | 覆盖 | 结果 |','|---|---|---|','| UBS | 九仓、203 PR、826批次 | 全部代表值、跨仓汇总、批次与任务派生值重算一致；任务样本x86=191、ARM=203、DT=195 |','| Triton | 38 PR、66批、434 workflow、593 job、142 NPU job | summary及E2E/NPU派生重算一致；65完成样本、48排队点 |','| 原始来源 | raw/SQLite/evidence/manifest缺失 | 未验证；内部一致性不能替代源时间、queue三分项或历史attempt正确性 |','', 'UBS已知缺口如实保留：12个请求无trigger、6批无唯一请求、17批不完整、2批运行中、16批取消。Triton全部66批使用近似起点；9条NPU时间倒置记录涉及5批，排队值留空。上述属于已明示的数据边界，不直接当作新缺陷。','', '## 优先问题与修复清单','']
for f in findings:
 lines.extend(['### '+f['id']+' · '+f['priority']+' · '+f['title'],'','- 位置：`'+f['location']+'`；证据类型：'+f['evidence_kind']+'。','- 复现：'+f['steps'],'- 预期：'+f['expected'],'- 实际：'+f['actual'],'- 影响：'+f['impact'],'- **修复建议：** '+f['proposed_fix'],'- 证据检查ID：`'+f['check_ids']+'`，见[覆盖矩阵](coverage-matrix.md)。',''])
lines.extend(['## 截图与范围限制','','![桌面与平板视图总览](screenshots/contact-sheet.png)','','![手机时间刻度拥挤](screenshots/mobile-triton-charts-crop.png)','','优先复现截图：[六小时时间窗](screenshots/triton-six-hour-mismatch.png)、[切仓旧详情](screenshots/ubs-cross-repo-wrong-detail.png)、[索引失败阻断Triton](screenshots/failure-ubs-index-blocks-triton.png)、[手机顶栏](screenshots/visual-mobile-triton-viewport.png)。','','原始平台数据、历史重跑attempt和真实Actions执行历史没有补采；冷/暖缓存与跨日发布的实际结果、实际部署fingerprint以及CI Python3.12/Node22兼容性仍未验证。没有触发采集或部署。静态链路问题与合成缺陷不能证明当前线上数据已经遭受对应影响。','','发布风险依据：[Actions缓存版本](https://github.com/actions/cache#cache-version)说明路径参与版本；[Actions并发规则](https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency)说明默认仅保留一个pending。两流程cancel-in-progress:false保护运行中的任务，但不保证所有排队任务均保留；这项记为运行风险，未计入19组已确认问题。','','## 修复与回归顺序','','1. 优先统一Triton页级数据集合和状态保存，同时修正筛选导出与P90阈值（F01–F03）。','2. 修正详情归属、刷新代次、两域故障隔离（F04–F06），用本次同样的故障/导航输入回归。','3. 完成缓存/attempt证据/发布完整性与原始来源覆盖保护（F07–F13），补真实工件验证后再判断来源准确性。','4. 修正搜索说明、键盘、小屏及共享外壳/历史导航/fixture（F14–F19）。','','修复后的通过标准：所有相关失败检查转为通过，原始证据缺口仍需保留；不得通过删除记录、补零或放宽预期让检查通过。'])
(AUDIT/'review-report.md').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps({'checks':counts,'findings':dict(pc),'report':str(AUDIT/'review-report.md'),'units':len(units)},ensure_ascii=False))
