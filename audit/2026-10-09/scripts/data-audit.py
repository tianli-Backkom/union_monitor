"""Independent derived-data audit. No network, no production writes."""
import json, math, re, subprocess, sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
OUT=ROOT/'audit'/'2026-10-09'/'evidence'
sys.path.insert(0,str(ROOT))
checks=[]; differences=[]
def read(p): return json.loads((ROOT/p).read_text(encoding='utf-8'))
def equal(a,b):
    if isinstance(a,dict) and isinstance(b,dict): return set(a)==set(b) and all(equal(a[k],b[k]) for k in a)
    if isinstance(a,list) and isinstance(b,list): return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    if isinstance(a,(int,float)) and not isinstance(a,bool) and isinstance(b,(int,float)) and not isinstance(b,bool): return math.isclose(a,b,rel_tol=1e-12,abs_tol=1e-6)
    return a==b
def check(id,label,actual,expected,**extra):
    c=dict(id=id,label=label,state='passed' if equal(actual,expected) else 'failed',actual=actual,expected=expected,**extra);checks.append(c);return c
def stamp(s): return datetime.fromisoformat(s.replace('Z','+00:00')).timestamp() if s else None
def pct(v,q):
    v=sorted(v)
    if not v:return None
    p=(len(v)-1)*q;return v[math.floor(p)]+(v[math.ceil(p)]-v[math.floor(p)])*(p-math.floor(p))
def stats(v):
    v=[x for x in v if isinstance(x,(int,float)) and not isinstance(x,bool) and math.isfinite(x) and x>=0]
    return {'n':len(v),'mean':sum(v)/len(v) if v else None,'p90':pct(v,.9)}
def own_batch(b):
    jobs=[b['trigger']]+b['children']
    status='running' if any(j.get('building') for j in jobs) else 'incomplete' if not b['complete'] or any(j.get('result') is None for j in jobs) else 'failure' if any(j['result']!='SUCCESS' for j in jobs) else 'success' if b['children'] else 'incomplete'
    ends=[j.get('end_ms') for j in jobs];end=max(ends) if ends and all(x is not None for x in ends) and b['complete'] else None
    req=b.get('request_ms');sched=b['trigger'].get('scheduled_ms')
    e2e=end-req if end is not None and req is not None and end>=req else None
    return {'status':status,'cancelled':any(j.get('result') in ['ABORTED','NOT_BUILT'] for j in jobs),'end_ms':end,'e2e_ms':e2e,'jenkins_ms':end-sched if end is not None and sched is not None and end>=sched else None,'eligible':status in ['success','failure'] and e2e is not None}
def representative(p):
    eligible=[b for b in p['batches'] if own_batch(b)['eligible'] and b['e2e_ms']>=0]
    b=max(eligible,key=lambda b:(b['e2e_ms'],int(b['number']),b['url'])) if eligible else None
    m={'representative_batch_url':b['url'] if b else None,'representative_batch_number':b['number'] if b else None,'e2e_ms':b['e2e_ms'] if b else None}
    for k in ['x86','arm','dt']:
        jobs={j['url']:j for j in (b['children'] if b else []) if j['kind']==k and j.get('association_valid') and not j.get('building') and j.get('result') in ['SUCCESS','FAILURE','UNSTABLE']}
        j=next(iter(jobs.values())) if len(jobs)==1 else {}
        m[k]={f+'_ms':j.get(f+'_ms') for f in ['queue','duration','total']};m[k]['url']=j.get('url')
    return m
def aggregate(ms):
    a={'e2e':stats([m['e2e_ms'] for m in ms])}
    for k in ['x86','arm','dt']:a[k]={f:stats([m[k][f+'_ms'] for m in ms]) for f in ['queue','duration','total']}
    return a
index=read('web/data/repositories.json'); all_prs=[]; per_repo=[]; metrics=[]; batches=[]; jobs=[]; keys=[]; urls=[]; counters=Counter()
for entry in index['repositories']:
    s=read('web/data/'+entry['snapshot']);name=entry['name'];ps=s['prs'];ms=[]
    check('D01-'+name,'仓库范围与归属 '+name,[s['meta']['repository'],s['meta']['start_ms'],s['meta']['end_ms']],[entry['repository'],index['start_ms'],index['end_ms']])
    check('D02-'+name,'索引meta与实际快照一致 '+name,entry['meta'],s['meta'])
    for p in ps:
        keys.append((entry['repository'],p['number']));all_prs.append(p);m=representative(p);ms.append(m);metrics.append(m)
        if not equal(m,p['metrics']):differences.append({'repo':name,'pr':p['number'],'type':'representative','expected':m,'actual':p['metrics']})
        ids={e['id'] for e in p['events']};linked={b.get('event_id') for b in p['batches']}
        counters['unlinked_events']+=sum(e['id'] not in linked for e in p['events'])
        for b in p['batches']:
            batches.append(b);urls.append(b['url']);counters['status_'+b['status']]+=1;counters['cancelled']+=bool(b.get('cancelled'));counters['missing_request']+=b.get('request_ms') is None
            counters['orphan_nonempty_event']+=bool(b.get('event_id')) and b['event_id'] not in ids
            v=own_batch(b)
            if not equal(v,{k:b.get(k) for k in v}):differences.append({'repo':name,'pr':p['number'],'batch':b['number'],'type':'batch','expected':v,'actual':{k:b.get(k) for k in v}})
            events=[e for e in p['events'] if e['id']==b.get('event_id')]
            if len(events)==1 and b.get('request_ms')!=events[0].get('time_ms'):differences.append({'repo':name,'pr':p['number'],'type':'request-time'})
            for j in [b['trigger']]+b['children']:
                jobs.append(j)
                if not j.get('building') and j.get('start_ms') is not None and j.get('duration_ms') is not None and j.get('end_ms')!=j['start_ms']+j['duration_ms']:differences.append({'type':'job-end','url':j['url']})
                if j.get('queue_ms') is not None and j.get('duration_ms') is not None and not j.get('building') and j.get('total_ms')!=j['queue_ms']+j['duration_ms']:differences.append({'type':'job-total','url':j['url']})
    per_repo.append({'name':name,'prs':len(ps),'batches':sum(len(p['batches']) for p in ps),'stats':aggregate(ms)})
check('D03','全部 PR 代表值/批次/事件/任务派生一致性',len(differences),0,checked_prs=len(all_prs),checked_batches=len(batches),checked_jobs=len(jobs))
check('D04','复合 PR 主键唯一',len(set(keys)),len(keys));check('D05','批次完整URL唯一',len(set(urls)),len(urls))
expected_aggregate=aggregate(metrics)
node_code="const fs=require('fs'),m=require('./web/core.js'),i=JSON.parse(fs.readFileSync('web/data/repositories.json','utf8'));let p=i.repositories.flatMap(r=>JSON.parse(fs.readFileSync('web/data/'+r.snapshot,'utf8')).prs);console.log(JSON.stringify({metrics:p.map(x=>m.metrics(x.batches)),aggregate:m.aggregate(p)}));"
node=json.loads(subprocess.run(['node','-e',node_code],cwd=ROOT,capture_output=True,text=True,encoding='utf-8',check=True).stdout)
check('D06','独立Python代表值与实际前端算法全部一致',node['metrics'],metrics)
check('D07','跨仓直接汇聚独立重算与前端一致',node['aggregate'],expected_aggregate)
t=read('web/data/triton.json'); tb=t['batches'];tf=[];warnings=[];workflows=[w for b in tb for w in b['workflows']];tj=[j for w in workflows for j in w['jobs']]
values=[b['duration_seconds'] for b in tb if b['status'] in ['success','failure'] and isinstance(b.get('duration_seconds'),(int,float)) and b['duration_seconds']>=0]
summary={'prs':len({b['pr'] for b in tb if b.get('pr')}),'batches':len(tb),'valid':len(values),'median':pct(values,.5),'p90':pct(values,.9),'approximate':sum(bool(b.get('approximate')) for b in tb),'incomplete':sum(bool(b.get('missing')) for b in tb)}
check('D08','Triton 快照汇总独立重算', {k:t['summary'][k] for k in summary},summary)
for b in tb:
    for j in b.get('npu_jobs',[]):
        c=stamp(j.get('created_at'));s=stamp(j.get('started_at'))
        expected=s-c if c is not None and s is not None and s>=c else None
        if s is not None and c is not None and s<c:warnings.append({'batch':b['id'],'job':j['id'],'issue':'inverted source timestamp; queue excluded'})
        if not equal(j.get('wait_seconds'),expected):tf.append({'batch':b['id'],'job':j['id'],'type':'npu-queue','expected':expected,'actual':j.get('wait_seconds')})
    waits=[j['wait_seconds'] for j in b.get('npu_jobs',[]) if j.get('wait_seconds') is not None]
    expected=max(waits) if waits and not b.get('npu_data_missing') else None
    if not equal(b.get('npu_queue_seconds'),expected):tf.append({'batch':b['id'],'type':'npu-max','expected':expected,'actual':b.get('npu_queue_seconds')})
    w=b['workflows'];beg=min(stamp(x['created_at']) for x in w);fin=max(stamp(x['updated_at']) for x in w) if b['status']!='running' else stamp(t['window_end'])
    if b['approximate'] and not equal(b['duration_seconds'],max(0,fin-beg)):tf.append({'batch':b['id'],'type':'e2e-from-retained-workflows','expected':max(0,fin-beg),'actual':b['duration_seconds']})
check('D09','Triton E2E与NPU排队/最大值派生一致性',len(tf),0,checked_batches=len(tb),npu_jobs=sum(len(b.get('npu_jobs',[])) for b in tb))
from triton.dashboard import build_batches,GitHub
from triton.quality import validate
row={'id':1,'name':'Example','head_sha':'abc','created_at':'2026-09-22T00:00:00Z','run_started_at':'2026-09-22T02:00:00Z','updated_at':'2026-09-22T02:05:00Z','status':'completed','conclusion':'success','run_attempt':2,'html_url':'https://github.com/example/actions/runs/1','jobs':[],'jobs_complete':True,'pr':42,'pr_title':'synthetic','pr_url':'https://github.com/example/pull/42','base_branch':'main','trigger_exact':False}
batch=build_batches([row],'2026-09-22T03:00:00Z')[0]
check('S01','重跑只计算本次attempt已观测跨度',batch['duration_seconds'],300,kind='synthetic',input=row,quality=validate([row],{'batches':[batch]}))
bad={**row,'run_attempt':1,'created_at':'2026-09-22T02:00:00Z','updated_at':'2026-09-22T01:00:00Z'};badbatch=build_batches([bad],'2026-09-22T03:00:00Z')[0];q=validate([bad],{'batches':[badbatch]})
check('S02','倒置workflow时间不得作为合法零耗时通过',q['passed'],False,kind='synthetic',input=bad,output=badbatch,quality=q)
api=GitHub.__new__(GitHub);api.get=lambda p:({'unexpected':'schema'},{});rejected=False
try:schema=api.pages('/actions/runs',field='workflow_runs')
except Exception:rejected=True;schema=None
check('S03','缺失workflow_runs字段必须拒绝',rejected,True,kind='synthetic',output=schema)
core_probe="const m=require('./web/triton-core.js');console.log(JSON.stringify(m.chartStats([{status:'success',duration_seconds:null},{status:'failure',duration_seconds:''},{status:'success',duration_seconds:-1}])));"
probe=json.loads(subprocess.run(['node','-e',core_probe],cwd=ROOT,capture_output=True,text=True,check=True).stdout)
check('S04','缺失/空串/负值不得纳入有效完成统计',probe['count'],0,kind='synthetic',output=probe,current_snapshot_has_invalid=False)
minimal=read('tests/fixtures/minimal/triton.json');mv=[b['duration_seconds'] for b in minimal['batches'] if b['status'] in ['success','failure']]
check('S05','最小fixture P90符合线性插值',minimal['summary']['p90'],pct(mv,.9),kind='fixture',values=mv)
missing=[p for p in ['data/raw','data/efficiency.sqlite','data/repositories.json','data/repos','web/data/snapshot.json','evidence/triton','web/data/triton-manifest.json','web/data/triton-batches.csv'] if not (ROOT/p).exists()]
checks.append({'id':'D10','label':'原始平台时间/queue分项/PR身份/重跑历史独立来源审计','state':'unverified','reason':'原始工件缺失；派生一致性不是来源准确性证明','missing':missing})
result={'executed_at':datetime.now(timezone.utc).isoformat(),'scope':'Full retained derived records; synthetic inputs separate; no network or production writes','ubs':{'prs':len(all_prs),'batches':len(batches),'jobs':len(jobs),'per_repository':per_repo,'aggregate':expected_aggregate,'known_gaps':dict(counters),'differences':differences},'triton':{'summary':summary,'workflows':len(workflows),'jobs':len(tj),'npu_jobs':sum(len(b.get('npu_jobs',[])) for b in tb),'npu_points':sum(b.get('npu_queue_seconds') is not None for b in tb),'warnings':warnings,'differences':tf},'checks':checks,'counts':dict(Counter(c['state'] for c in checks))}
(OUT/'data-audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'counts':result['counts'],'ubs_prs':len(all_prs),'ubs_batches':len(batches),'ubs_differences':len(differences),'triton_differences':len(tf),'source_missing':missing},ensure_ascii=False))
