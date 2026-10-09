from pathlib import Path
import json,re
from datetime import datetime,timezone,timedelta
A=Path(__file__).resolve().parents[1]
report=A/'review-report.md';text=report.read_text(encoding='utf-8')
table=(A/'evidence/scorecard.md').read_text(encoding='utf-8').splitlines()
header='\n'.join(table[:2]);rows=table[2:]
score='## 组件质量与分析稳健性\n\n分母为本次明确盘点的组件、控件或问题单元，不是原始行数；0 / N表示没有观察到剩余缺陷，不表示全部来源已验证。各类别重叠，不能合成准确率。\n\n### 看板用途与质量\n\n'+header+'\n'+'\n'.join(rows[:3])+'\n\n### 分析正确性与稳健性\n\n'+header+'\n'+'\n'.join(rows[3:])+'\n\n'
text=text.replace('## 优先问题与修复清单',score+'## 优先问题与修复清单')
after=json.loads((A/'evidence/protected-files-after.json').read_text(encoding='utf-8'))
text+='\n\n## 保持原文件与可复现性\n\n'+str(after['protected_files'])+'个受保护业务源码、测试、配置及正式数据文件SHA-256复核无变化，见[校验结果](evidence/protected-files-after.json)。审查输出全部位于本目录。\n\n审查结果生成于 '+datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S Asia/Shanghai')+'。原始来源审计缺口和并发历史影响仍标为未验证。\n\n复现入口：`scripts/ubs-browser.cjs`、`scripts/triton-browser.cjs`、`scripts/additional-browser.cjs`、`scripts/data-audit.py`、`scripts/deployment-audit.py`。浏览器脚本要求本机服务18765和已安装Chrome/Edge，所有写入限定在审查目录；不触发collect或deploy。\n'
# Use absolute local targets so the desktop preview can resolve every evidence link.
def absolute(m):
 target=m.group(2)
 if re.match(r'https?://|[A-Za-z]:/|#',target):return m.group(0)
 return m.group(1)+'('+str((A/target).resolve()).replace('\\','/')+')'
text=re.sub(r'(!?\[[^\]]*\])\(([^)]+)\)',absolute,text)
report.write_text(text,encoding='utf-8')
missing=[]
for target in re.findall(r'\]\(([^)]+)\)',text):
 if re.match(r'https?://',target):continue
 if not Path(target).exists():missing.append(target)
evidence_files=[]
for p in (A/'evidence').glob('*.json'):
 try:json.loads(p.read_text(encoding='utf-8-sig'));evidence_files.append(p.name)
 except Exception as e:missing.append(str(p)+': '+str(e))
findings=json.loads((A/'evidence/findings.json').read_text(encoding='utf-8'))
ok=not missing and not after['changed'] and len(findings)==19 and len(re.findall(r'^### F\d+',text,re.M))==19
result={'report_exists':report.exists(),'report_bytes':report.stat().st_size,'findings':len(findings),'json_evidence_files_valid':len(evidence_files),'broken_local_links':missing,'production_changed':after['changed'],'status':'passed' if ok else 'failed'}
(A/'evidence/final-delivery-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False));raise SystemExit(0 if ok else 1)
