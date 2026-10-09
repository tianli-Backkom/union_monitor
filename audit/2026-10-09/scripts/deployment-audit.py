"""Static publication and legacy feature checks; no workflow runs triggered."""
import json,re,hashlib
from pathlib import Path
from datetime import datetime,timezone
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'audit'/'2026-10-09'/'evidence'
def source(p):return (ROOT/p).read_text(encoding='utf-8')
daily=source('.github/workflows/pages.yml');inc=source('.github/workflows/triton-refresh.yml')
def paths(s):
    m=re.search(r'path: \|\s*\n((?:\s{12}[^\n]+\n)+)',s)
    return [x.strip() for x in m[1].splitlines()] if m else []
checks=[]
def check(id,label,actual,expected,**e):checks.append({'id':id,'label':label,'state':'passed' if actual==expected else 'failed','actual':actual,'expected':expected,**e})
dpaths,ipaths=paths(daily),paths(inc)
check('P01','每日与增量使用同一缓存路径版本',dpaths,ipaths,kind='static-confirmed',references=['https://github.com/actions/cache#cache-version'],impact='同key前缀不足以跨版本恢复；真实缓存命中/回退历史未读取')
check('P02','两个发布流程接入发布后数据指纹校验',[bool(re.search(r'run:.*verify_deployment',x)) for x in [daily,inc]],[True,True],kind='static-confirmed')
check('P03','增量数据恢复检查索引JSON及全部引用快照',bool(re.search(r'validate_multi|validate\.py|json\.load.*\n.*assert',inc)),True,kind='static-confirmed',evidence='Ensure仅检查 -s index；JSON解析失败sys.exit(0)，单仓fetch失败||true；正常单测不验证实际fallback输入')
check('P04','并发配置能保留多个pending运行',bool(re.search(r'queue:\s*max',daily)) and bool(re.search(r'queue:\s*max',inc)),True,kind='documented-risk',references=['https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/control-workflow-concurrency'],impact='当前保护running，不能兑现测试名称queued_runs_never_cancel_daily；真实取消事件未读取')
checks[-1]['state']='unverified'
checks[-1]['reason']='文档确认默认pending替换规则；是否已经影响每日运行未读Actions历史，不把缺少queue:max本身当作新的必需功能。'
vm=source('validate_multi.py');v=source('validate.py')
check('P05','原始时间审计要求非零/完整证据覆盖',bool(re.search(r'assert\s+checked\s*[>=]',vm)) and bool(re.search(r'assert\s+checked\s*[>=]',v)),True,kind='static-confirmed',evidence='raw存在才核对；checked累加后直接写checks_passed=True；queue原始三分项未独立验证')
old=json.loads((OUT/'deployment-oldsite-summary.json').read_text(encoding='utf-8'))
features=[
 {'feature':'UBS跨仓总览/状态/排序/仓库CSV','old':'旧UBS #repositories','merged':'#ubs','state':'retained','evidence':'ubs-browser U01–U04/U31'},
 {'feature':'UBS单仓筛选/PR排序/分页/图表与表格耗时','old':'旧UBS #overview/#prs','merged':'#ubs/repo/NAME','state':'retained','evidence':'ubs-browser U05–U20'},
 {'feature':'UBS全部批次/代表默认展开/质量与CSV','old':'旧UBS详情及#quality','merged':'单仓及quality页','state':'retained-with-defects','evidence':'U24–U30/U34–U37'},
 {'feature':'UBS统计口径/源链接/重新加载','old':'旧UBS #method','merged':'#method和共享顶栏','state':'retained-with-defects','evidence':'U10/A03/F04'},
 {'feature':'Triton E2E/NPU散点与选区统计','old':'旧Triton单页','merged':'#triton','state':'retained','evidence':'T02/T03/T10–T12/A12/A13'},
 {'feature':'Triton分支/独立状态/共享五档时间/拖拽','old':'旧Triton局部联动','merged':'#triton','state':'retained-but-new-contract-unmet','evidence':'T04–T12/T22–T25/T08'},
 {'feature':'Triton关注/全部/搜索/详情/固定悬浮卡片','old':'旧Triton单页','merged':'#triton','state':'retained-with-defects','evidence':'T13–T15/T18–T21/T28/A01'},
 {'feature':'Triton全页时间联动/筛选导出/跨域状态','old':'旧站没有统一跨域预期','merged':'本轮批准的新验收基准','state':'failed','evidence':'T08/T09/T16/T17/A02'},
 {'feature':'新鲜度/近似起点/证据缺口提示','old':'旧Triton单页','merged':'#triton','state':'retained','evidence':'截图与D08/D09；66近似批次/9倒置警告如实保留'},
]
result={'executed_at':datetime.now(timezone.utc).isoformat(),'checks':checks,'cache_paths':{'daily':dpaths,'incremental':ipaths},'legacy_features':features,'legacy_sources':old['sources'],'unverified':['真实Actions冷/暖缓存命中与跨日部署历史','实际多pending取消事件','原始工件到已发布页面fingerprint','CI Python3.12/Node22运行兼容性'], 'scope':'Static audit plus official documentation and captured public legacy source; no refresh/deploy'}
(OUT/'deployment-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
lines=['# 旧站功能对照','', '| 能力 | 合并后位置 | 结果 | 证据 |','|---|---|---|---|']
for f in features:lines.append('|'+ '|'.join([f['feature'],f['merged'],f['state'],f['evidence']])+'|')
lines.extend(['','对照的是公开源代码、控件清单与合并版浏览器行为；两个旧站没有重新进行全部交互验收。Triton旧站为内嵌数据单页，外部 web/triton-core.js 探测404不代表旧页缺少核心函数。'])
(OUT/'baseline-comparison.md').write_text('\n'.join(lines),encoding='utf-8')
print(json.dumps({'checks':len(checks),'failed':sum(c['state']=='failed' for c in checks),'cache_paths':result['cache_paths']},ensure_ascii=False))
