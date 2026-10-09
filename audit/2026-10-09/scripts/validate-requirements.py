"""Structural and traceability QA for the requested requirements artifact."""
from pathlib import Path
import hashlib,json,re
from collections import Counter
A=Path(__file__).resolve().parents[1];ROOT=A.parents[1];E=A/'evidence'
m=json.loads((E/'requirements-model.json').read_text(encoding='utf-8'))
doc=(A/'requirements.md').read_text(encoding='utf-8');rs=m['requirements'];by={r['id']:r for r in rs}
fs=json.loads((E/'findings.json').read_text(encoding='utf-8'))
cs={c['id'] for c in json.loads((E/'all-checks.json').read_text(encoding='utf-8'))['checks']}
errors=[]
def need(value,msg):
 if not value:errors.append(msg)
need(len(rs)==len(by)==51,'requirement IDs must be unique and total 51')
need(list(by)==[f'REQ-{i:03}' for i in range(1,52)],'IDs must be continuous')
ac=[];covered=set()
for r in rs:
 need(bool(r['goal'].strip()) and bool(r['rule'].strip()),r['id']+' needs goal/rule')
 need(len(r['acceptance'])>=3,r['id']+' needs >=3 acceptance criteria')
 for c in r['acceptance']:
  ac.append(c['id']);need(c['id'].startswith(r['id']+'-AC'),c['id']+' invalid owner');need(bool(c['text'].strip()),c['id']+' empty')
 covered.update(r['source_findings'])
 need(all(x in cs for x in r['evidence_checks']),r['id']+' unknown evidence ID: '+str([x for x in r['evidence_checks'] if x not in cs]))
 need(all(x in by for x in r['dependencies']),r['id']+' unknown dependency')
need(len(ac)==len(set(ac))==195,'acceptance IDs must be unique and total 195')
need(covered=={f['id'] for f in fs},'all original findings must be covered exactly as a source set')
visiting=set();done=set()
def visit(k):
 if k in visiting:errors.append('cyclic dependency at '+k);return
 if k in done:return
 visiting.add(k)
 for x in by[k]['dependencies']:
  if x in by:visit(x)
 visiting.remove(k);done.add(k)
for k in by:visit(k)
need(Counter(r['kind'] for r in rs)==Counter({'整改':37,'补证':3,'保持':9,'交付':2}),'type counts mismatch')
need(len(re.findall(r'^### REQ-\d{3} ·',doc,re.M))==51,'document headings incomplete')
need(not re.search(r'\bTODO\b|\bTBD\b',doc),'document has unresolved placeholders')
for target in re.findall(r'\]\(([^)]+)\)',doc):
 if not target.startswith(('http://','https://','#')):need(Path(target).exists(),'broken local link '+target)
changed=[]
for s in m['sources']:
 actual=hashlib.sha256((A/s['path']).read_bytes()).hexdigest()
 if actual!=s['sha256']:changed.append(s['path'])
need(not changed,'audit sources changed '+str(changed))
protected=json.loads((E/'protected-files-before.json').read_text(encoding='utf-8-sig'))
production_changed=[x['path'] for x in protected if not (ROOT/x['path']).exists() or hashlib.sha256((ROOT/x['path']).read_bytes()).hexdigest().upper()!=x['sha256']]
business_changed=[x for x in production_changed if x!='.gitignore']
need(not business_changed,'business source/snapshot files changed '+str(business_changed))
result={'status':'passed' if not errors else 'failed','requirements':len(rs),'acceptance_criteria':len(ac),'findings_covered':len(covered),'type_counts':dict(Counter(r['kind'] for r in rs)),'dependencies_acyclic':not any('cyclic' in x for x in errors),'audit_sources_unchanged':not changed,'business_source_and_snapshots_unchanged':not business_changed,'prior_audit_baseline_differences':production_changed,'warnings':['.gitignore与上轮审查基线不同，当前含.omo/与.codegraph/忽略项，文档生成工具没有写该文件；保留当前版本。'] if '.gitignore' in production_changed else [],'errors':errors}
(E/'requirements-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(result,ensure_ascii=False));raise SystemExit(0 if not errors else 1)
