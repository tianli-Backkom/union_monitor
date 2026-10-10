#!/usr/bin/env python3
"""Current-code adversarial audit; no live collection and audit-only output."""
import sys
sys.dont_write_bytecode = True
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
import copy, csv, hashlib, io, json, math, re, subprocess
from collections import Counter
from datetime import datetime, timezone
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from triton import dashboard as d
from triton.quality import validate
import metrics

OUT = ROOT / 'audit/2026-10-10/evidence'
R = {'head': subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
     'recorded_at': datetime.now(timezone.utc).isoformat(), 'cases': [], 'inputs': [],
     'real': {}, 'limits': [], 'requirements': []}

def read(rel):
    raw=(ROOT/rel).read_bytes()
    R['inputs'].append({'path':rel,'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
    return json.loads(raw.decode('utf-8-sig'))

def safe(v):
    if isinstance(v,float) and not math.isfinite(v): return str(v)
    if isinstance(v,dict): return {k:safe(x) for k,x in v.items()}
    if isinstance(v,list): return [safe(x) for x in v]
    return v

def equal(expected,actual):
    if isinstance(expected,dict):
        return isinstance(actual,dict) and all(k in actual and equal(v,actual[k]) for k,v in expected.items())
    if isinstance(expected,list):
        return isinstance(actual,list) and len(expected)==len(actual) and all(equal(a,b) for a,b in zip(expected,actual))
    if type(expected) in (float,int) and type(actual) in (float,int):
        return math.isclose(expected,actual,rel_tol=1e-12,abs_tol=1e-6)
    return type(expected)==type(actual) and expected==actual

def case(name,acs,expected,actual,location='',scope='synthetic',severity='P2'):
    R['cases'].append({'id':name,'acs':acs.split(), 'scope':scope,'expected':safe(expected),'actual':safe(actual),
                       'passed':equal(expected,actual),'location':location,'severity':severity})

def row(attempt=1,**kw):
    x={'id':1,'event':'pull_request','head_sha':'abc','created_at':'2026-10-08T00:00:00Z',
       'run_started_at':'2026-10-08T02:00:00Z','updated_at':'2026-10-08T02:05:00Z',
       'run_attempt':attempt,'status':'completed','conclusion':'success','jobs_complete':True,'jobs':[],
       'pr':23,'pr_url':'https://github.com/triton-lang/triton-ascend/pull/23','pr_title':'Synthetic',
       'base_branch':'main','trigger_at':None,'trigger_exact':False,
       'pr_evidence':{'method':'synthetic','run_id':1,'pr':23,'resolved_head_sha':'abc'}}
    x.update(kw)
    if x['id']!=1:x['pr_evidence']={**x['pr_evidence'],'run_id':x['id']}
    return x

def payload(rows,end='2026-10-09T00:00:00Z',start='2026-10-07T00:00:00Z'):
    return d.build_payload(copy.deepcopy(rows),start,end,end)

def batch_fields(b):
    return {k:b.get(k) for k in ['duration_seconds','start_at','start_source','approximate','complete','missing']}

def gate(rows,p):
    try:return validate(rows,p)
    except Exception as e:return {'passed':False,'exception':type(e).__name__+': '+str(e)}

def attempt_cases():
    exact=row(2,trigger_at='2026-10-08T02:00:00Z',trigger_exact=True)
    case('trusted-attempt-trigger','REQ-014-AC01',{'duration_seconds':300,'start_source':'trigger_event','approximate':False},batch_fields(payload([exact])['batches'][0]))
    approx=row(2)
    case('attempt-start-proxy','REQ-014-AC02',{'duration_seconds':300,'start_source':'attempt_start','approximate':True},batch_fields(payload([approx])['batches'][0]))
    missing=row(2,run_started_at=None)
    mp=payload([missing]); mb=mp['batches'][0]
    case('no-current-attempt-start','REQ-014-AC03',{'duration_seconds':None,'start_at':None,'complete':False,'valid':0,'workflow_count':1},
         {**batch_fields(mb),'valid':mp['summary']['valid'],'workflow_count':len(mb['workflows'])})
    class MemoryText(io.StringIO):
        def close(self):pass
    buffer=MemoryText()
    cp=payload([exact,row(2,id=2),row(2,id=3,run_started_at=None)])
    with patch('pathlib.Path.open',return_value=buffer):d.export_csv(cp)
    exported=list(csv.DictReader(io.StringIO(buffer.getvalue())))
    case('attempt-csv-source-and-unknown-value','REQ-014-AC04 REQ-017-AC02',
         [{'start_source':'','approximate':'False','duration_seconds':''},
          {'start_source':'trigger_event','approximate':'False','duration_seconds':'300.0'},
          {'start_source':'attempt_start','approximate':'True','duration_seconds':'300.0'}],
         [{k:r[k] for k in ['start_source','approximate','duration_seconds']} for r in exported],
         scope='synthetic in-memory CSV; UI alignment belongs to browser reviewer')
    first=row(1,run_started_at='2026-10-08T00:00:00Z',updated_at='2026-10-08T00:05:00Z',jobs=[{'id':11,'name':'CPU'}])
    second=row(2,jobs=[{'id':22,'name':'CPU'}])
    bp=payload([first,second,copy.deepcopy(second)])
    case('explicit-attempt-history-and-dedup','REQ-015-AC01 REQ-015-AC03',{'attempts':[1,2],'job_ids':[11,22]},
         {'attempts':sorted(w['attempt'] for b in bp['batches'] for w in b['workflows']),
          'job_ids':sorted(j['id'] for b in bp['batches'] for w in b['workflows'] for j in w['jobs'])})
    out=row(2,created_at='2026-09-01T00:00:00Z',run_started_at='2026-10-08T02:00:00Z')
    case('provided-old-run-current-attempt','REQ-015-AC02',{'count':1,'duration_seconds':300},
         {'count':len(payload([out])['batches']),'duration_seconds':payload([out])['batches'][0]['duration_seconds']})
    unknown=[row(1,pr=None),row(2,pr=None),row(2,id=2,pr=None)]
    ub=payload(unknown)['batches']
    case('unresolved-run-attempt-isolation','REQ-015-AC04',{'count':3,'unique_ids':3,'missing_pr':3},
         {'count':len(ub),'unique_ids':len({b['id'] for b in ub}),'missing_pr':sum('未可靠关联 PR' in b['missing'] for b in ub)})

    # All collector I/O is mocked; no directory, response cache or network is used.
    class MemoryPath:
        def mkdir(self,*a,**kw):pass
        def __truediv__(self,other):return self
        def __str__(self):return 'memory-only'
        def __fspath__(self):return 'memory-only'
    def collect_mock(source_rows):
        calls=[];writes=[]
        class API:
            def __init__(self):self.calls=0
            def get(self,path):
                q=parse_qs(urlsplit(path).query)['created'][0].split('..')
                matches=[] if 'event=pull_request_target' in path else [x for x in source_rows if d.dt(q[0])<=d.dt(x['created_at'])<=d.dt(q[1])]
                return {'total_count':len(matches)},{}
            def pages(self,path,field=None):
                calls.append(path)
                if field=='jobs':return [{'id':100+int(re.search(r'/attempts/(\d+)',path)[1]),'name':'CPU'}]
                if 'event=pull_request_target' in path:return []
                q=parse_qs(urlsplit(path).query)['created'][0].split('..')
                return [copy.deepcopy(x) for x in source_rows if d.dt(q[0])<=d.dt(x['created_at'])<=d.dt(q[1])]
        def resolve(self,x):return {k:x[k] for k in ['pr','pr_url','pr_title','base_branch','head_sha','pr_evidence']}
        with patch.object(d,'GitHub',API),patch.object(d,'EVIDENCE',MemoryPath()),patch.object(d,'_write_json',side_effect=lambda p,v:writes.append(copy.deepcopy(v))),patch('triton.pr_identity.PRResolver.resolve',resolve):
            p=d.collect(72,'2026-10-09T00:00:00Z')
        return {'attempts':sorted(w['attempt'] for b in p['batches'] for w in b['workflows']),
                'job_calls':[c for c in calls if '/jobs' in c],'batches':len(p['batches'])}
    case('collector-still-enumerates-only-current-attempt','REQ-015-AC01',{'attempts':[1,2,3]},collect_mock([row(3)]),
         'triton/dashboard.py:470-491',severity='P1')
    case('collector-old-run-beyond-lookback-is-lost','REQ-015-AC02',{'attempts':[2],'batches':1},
         collect_mock([row(2,created_at='2026-09-18T00:00:00Z')]),'triton/dashboard.py:192,457-471',severity='P1')

def pagination_cases():
    def pages(responses,field='workflow_runs'):
        with patch.object(d.GitHub,'get',side_effect=[(x,{}) for x in responses]):
            try:return {'rejected':False,'count':len(d.GitHub().pages('/actions/runs',field))}
            except Exception as e:return {'rejected':True,'error':str(e)}
    for label,value in [('missing',{}),('null',{'workflow_runs':None}),('object',{'workflow_runs':{}})]:
        case('workflow-schema-'+label,'REQ-018-AC01',{'rejected':True},pages([value]))
    case('legal-zero-page','REQ-018-AC02',{'rejected':False,'count':0},pages([{'total_count':0,'workflow_runs':[]}]))
    first=[{'id':i} for i in range(100)]
    case('duplicate-page-id','REQ-018-AC03',{'rejected':True},pages([{'total_count':101,'workflow_runs':first},{'total_count':101,'workflow_runs':[{'id':0}]}]))
    case('declared-count-missing-page','REQ-018-AC03',{'rejected':True},pages([{'total_count':101,'workflow_runs':first},{'total_count':101,'workflow_runs':[]}]))
    case('declared-count-changes-hide-truncation','REQ-018-AC03',{'rejected':True},pages([{'total_count':150,'workflow_runs':first},{'total_count':100,'workflow_runs':[]}]),'triton/dashboard.py:362-373')
    case('duplicate-records-without-id','REQ-018-AC03',{'rejected':True},pages([{'total_count':200,'workflow_runs':[{'name':'same'}]*100},{'total_count':200,'workflow_runs':[{'name':'same'}]*100},{'total_count':200,'workflow_runs':[]}]),'triton/dashboard.py:364-369')

def quality_cases():
    good=row(2); gp=payload([good])
    case('baseline-quality-control','REQ-019-AC01',{'passed':True},gate([good],gp))
    inverted=row(2,updated_at='2026-10-08T01:00:00Z')
    case('rerun-end-before-start','REQ-019-AC01',{'passed':False},gate([inverted],payload([inverted])))
    late=row(2,updated_at='2026-10-09T01:00:00Z')
    case('completed-after-as-of','REQ-019-AC02',{'passed':False},gate([late],payload([late])))
    bad=row(1,trigger_at='2026-10-08T02:00:00Z',trigger_exact=True,updated_at='2026-10-08T01:00:00Z')
    aux=row(1,id=2,trigger_at='2026-10-08T00:30:00Z',trigger_exact=True,updated_at='2026-10-08T03:00:00Z')
    p=payload([bad,aux])
    case('other-workflow-masks-inverted-applicable-start','REQ-019-AC01',{'passed':False},gate([bad,aux],p),'triton/quality.py:28-38; triton/dashboard.py:231-248')
    for label,value in [('missing',None),('invalid','not-a-date')]:
        p=copy.deepcopy(gp);p['window_end']=value
        case('invalid-as-of-'+label,'REQ-019-AC02 REQ-019-AC03',{'passed':False},gate([good],p),'triton/quality.py:15-18')
    for label,value in [('negative',-1),('null',None),('bool',True),('string','300'),('wrong-span',999)]:
        p=copy.deepcopy(gp);p['batches'][0]['duration_seconds']=value
        case('quality-duration-'+label,'REQ-019-AC02',{'passed':False},
             {**gate([good],p),'input_duration':safe(value),'stored_summary':p['summary'],'independent_summary':d.summary_of(p['batches'])},'triton/quality.py:77-89')
    p=copy.deepcopy(gp);p['summary']['valid']=99;p['summary']['p90']=999
    case('quality-contradictory-summary','REQ-019-AC02 REQ-046-AC01',{'passed':False},
         {**gate([good],p),'stored_summary':p['summary'],'independent_summary':d.summary_of(p['batches'])},'triton/quality.py:13-92')
    running=row(2,status='in_progress',conclusion=None,updated_at='2026-10-08T02:30:00Z')
    p=payload([running]);p['batches'][0]['duration_seconds']=float('nan')
    case('running-nan-observed-span','REQ-019-AC03',{'passed':False},gate([running],p),'triton/quality.py:85-89')
    job={'id':8,'name':'integration-tests-ascend (linux-amd64-a5-2, py3.12)','status':'completed','conclusion':'success',
         'created_at':'2026-10-08T02:02:00Z','started_at':'2026-10-08T02:01:00Z','completed_at':'2026-10-08T02:04:00Z'}
    x=row(2,jobs=[job]);p=payload([x]);q=gate([x],p)
    case('npu-inverted-source-warning','REQ-019-AC04',{'passed':True,'warnings':1,'queue':None},
         {'passed':q['passed'],'warnings':len(q['warnings']),'queue':p['batches'][0]['npu_queue_seconds']})
    for state in ['skipped','cancelled']:
        j={**job,'conclusion':state,'started_at':None,'completed_at':None};x=row(2,jobs=[j]);p=payload([x])
        case('npu-unstarted-'+state,'REQ-019-AC04',{'passed':True},gate([x],p))

def ref_stats(values):
    a=sorted(v for v in values if type(v) in (int,float) and math.isfinite(v) and v>=0)
    def pct(q):
        if not a:return None
        p=(len(a)-1)*q;l=math.floor(p);h=math.ceil(p)
        return a[l]+(a[h]-a[l])*(p-l)
    return {'n':len(a),'mean':sum(a)/len(a) if a else None,'p50':pct(.5),'p90':pct(.9)}

def ubs_aggregate(prs):
    values=[rep(p) for p in prs]
    def s(a):return {k:v for k,v in ref_stats(a).items() if k!='p50'}
    return {'e2e':s([m['e2e_ms'] for m in values]),
            **{k:{f:s([m[k][f+'_ms'] for m in values]) for f in ['queue','duration','total']} for k in ['x86','arm','dt']}}

def rep(p):
    a=[b for b in p['batches'] if b.get('eligible') and type(b.get('e2e_ms')) in (int,float) and math.isfinite(b['e2e_ms']) and b['e2e_ms']>=0]
    b=max(a,key=lambda b:(b['e2e_ms'],int(b['number']),b['url']),default=None)
    m={'representative_batch_url':b['url'] if b else None,'representative_batch_number':b['number'] if b else None,'e2e_ms':b['e2e_ms'] if b else None}
    for k in ['x86','arm','dt']:
        js={j['url']:j for j in (b['children'] if b else []) if j['kind']==k and j.get('association_valid') and not j.get('building') and j.get('result') in ['SUCCESS','FAILURE','UNSTABLE']}
        j=next(iter(js.values())) if len(js)==1 else {}
        m[k]={f+'_ms':j.get(f+'_ms') for f in ['queue','duration','total']};m[k]['url']=j.get('url')
    return m

def real_audit():
    idx=read('web/data/repositories.json');prs=[];bs=[];diff=[];snapshots={}
    for e in idx['repositories']:
        s=read('web/data/'+e['snapshot']);snapshots[e['name']]=s
        if s['meta']!=e['meta']:diff.append({'repo':e['name'],'field':'meta'})
        for p in s['prs']:
            prs.append(p);bs.extend(p['batches'])
            if not equal(rep(p),p['metrics']):diff.append({'repo':e['name'],'pr':p['number'],'expected':rep(p),'actual':p['metrics']})
            events={x['id']:x for x in p['events']}
            for b in p['batches']:
                js=[b['trigger']]+b['children']
                if b.get('request_ms') is not None and events.get(b['event_id'],{}).get('time_ms')!=b['request_ms']:diff.append({'batch':b['url'],'field':'request_time'})
                if b['eligible'] and max(j['end_ms'] for j in js)-b['request_ms']!=b['e2e_ms']:diff.append({'batch':b['url'],'field':'e2e'})
                for j in js:
                    if j.get('total_ms') is not None and j['total_ms']!=j['queue_ms']+j['duration_ms']:diff.append({'job':j['url'],'field':'total'})
    counts={'prs':len(prs),'batches':len(bs),'x86':sum(rep(p)['x86']['total_ms'] is not None for p in prs),
            'arm':sum(rep(p)['arm']['total_ms'] is not None for p in prs),'dt':sum(rep(p)['dt']['total_ms'] is not None for p in prs)}
    case('current-ubs-independent-values','REQ-041-AC01 REQ-041-AC04',{'differences':[]},{'counts':counts,'differences':diff},scope='real current snapshots; not original 203/826 freeze')
    case('current-ubs-identities','REQ-041-AC04',{'duplicate_prs':0,'duplicate_batches':0},
         {'duplicate_prs':len(prs)-len({(p['repository'],p['number']) for p in prs}),'duplicate_batches':len(bs)-len({b['url'] for b in bs})},scope='real preserved snapshots')
    gaps={'unlinked_requests':sum(not e.get('batch_urls') for p in prs for e in p['events']),
          'missing_request':sum(b.get('request_ms') is None for b in bs),'incomplete':sum(b['status']=='incomplete' for b in bs),
          'running':sum(b['status']=='running' for b in bs),'cancelled':sum(b['cancelled'] for b in bs)}
    R['real']['current_ubs_boundary_counts']=gaps
    t=read('web/data/triton.json');f=read('tests/fixtures/triton-audit-freeze.json')
    values=[b['duration_seconds'] for b in t['batches'] if b['status'] in ['success','failure'] and d.valid_seconds(b['duration_seconds'])]
    stats=ref_stats(values);summary={'prs':len({b['pr'] for b in t['batches'] if b['pr']}),'batches':len(t['batches']),'valid':len(values),'median':stats['p50'],'p90':stats['p90'],
               'approximate':sum(b['approximate'] for b in t['batches']),'incomplete':sum(bool(b['missing']) for b in t['batches'])}
    case('current-triton-summary','REQ-046-AC01',summary,t['summary'],scope='real current snapshots')
    inverted=[];npu_diff=[]
    for b in t['batches']:
        waits=[]
        for j in b['npu_jobs']:
            a=d.dt(j.get('created_at'));z=d.dt(j.get('started_at'))
            wait=(z-a).total_seconds() if a and z and z>=a else None
            if a and z and z<a:inverted.append({'batch':b['id'],'job':j['id'],'queue':j['wait_seconds'],'error':j.get('measurement_error')})
            if wait!=j['wait_seconds']:npu_diff.append({'job':j['id'],'expected':wait,'actual':j['wait_seconds']})
            if wait is not None:waits.append(wait)
        expected=max(waits) if waits and not b['npu_data_missing'] else None
        if expected!=b['npu_queue_seconds']:npu_diff.append({'batch':b['id'],'expected':expected,'actual':b['npu_queue_seconds']})
    case('current-triton-npu-and-boundaries','REQ-046-AC01 REQ-046-AC02',{'inverted_jobs':9,'inverted_batches':5,'differences':[]},
         {'npu_points':sum(b['npu_queue_seconds'] is not None for b in t['batches']),'approximate':summary['approximate'],'inverted_jobs':len(inverted),
          'inverted_batches':len({x['batch'] for x in inverted}),'differences':npu_diff},scope='real preserved snapshots')
    reconstructed=[{**w,'pr_title':b['title'],'base_branch':b['base_branch']} for b in t['batches'] for w in b['workflows']]
    gate_result=gate(reconstructed,t)
    case('current-triton-quality-retains-warnings','REQ-046-AC02',{'passed':True,'warnings':9},{'passed':gate_result['passed'],'warnings':len(gate_result.get('warnings',[]))},scope='derived reconstruction, not raw source')
    R['real']={'ubs_counts':counts,'ubs_gaps':gaps,'triton_summary':summary,'frozen_equal':t==f,'npu_warnings':inverted,'reconstructed_quality':gate_result,
               'independent_ubs_aggregate':ubs_aggregate(prs),
               'frozen_ubs_original_203_826_status':'unverified: original full UBS frozen corpus is not available in this workspace'}
    fs=d.summary_of(f['batches']);fq=gate([{**w,'pr_title':b['title'],'base_branch':b['base_branch']} for b in f['batches'] for w in b['workflows']],f)
    case('original-triton-freeze-summary','REQ-046-AC01',{'prs':38,'batches':66,'valid':65,'median':1580,'p90':3620.2,'approximate':66,'incomplete':0},fs,scope='real original frozen fixture')
    case('original-triton-freeze-queue-warning-preservation','REQ-046-AC01 REQ-046-AC02',{'npu_points':48,'warnings':9,'passed':True},
         {'npu_points':sum(b.get('npu_queue_seconds') is not None for b in f['batches']),'warnings':len(fq.get('warnings',[])),'passed':fq['passed']},scope='real original frozen fixture')
    R['real']['frozen_triton_quality']=fq
    for name in ['triton.json','triton-zero.json','triton-single.json']:
        x=read('tests/fixtures/minimal/'+name);expected=d.summary_of(x['batches'])
        case('fixture-'+name,'REQ-037-AC01 REQ-037-AC02 REQ-037-AC03 REQ-046-AC04',expected,x['summary'],scope='fixture')
        case('fixture-kinds-'+name,'REQ-037-AC02',True,all(b['kind'] in ['initial','rerun'] for b in x['batches']),scope='fixture')

NODE=r"""
const fs=require('fs'),root=process.argv[1],m=require(root+'/web/core.js'),t=require(root+'/web/triton-core.js');
const bad=[{status:'success',duration_seconds:null},{status:'failure',duration_seconds:''},{status:'success',duration_seconds:-1}];
const mix=[...bad,{status:'success',duration_seconds:0},{status:'success',duration_seconds:600},{status:'failure',duration_seconds:900},{status:'running',duration_seconds:1000},{status:'cancelled',duration_seconds:1200}];
const shapes=[{events:[{id:'create'}],batches:[{url:'a',event_id:'create'},{url:'b',event_id:'ghost'},{url:'c',event_id:null}]},{events:[{id:'create'},{id:'create'}],batches:[{url:'a',event_id:'create'},{url:'b',event_id:'ghost'}]},{events:[],batches:[{url:'a',event_id:'ghost'},{url:'b',event_id:null}]}];
const groups=shapes.map(p=>m.detailGroups(p).flatMap(g=>g.batches).map(b=>b.url));
const idx=JSON.parse(fs.readFileSync(root+'/web/data/repositories.json','utf8')),s={};for(const e of idx.repositories)s[e.name]=JSON.parse(fs.readFileSync(root+'/web/data/'+e.snapshot,'utf8'));
const all=m.repositoryRows(idx,s).flatMap(r=>r.prs);
const edge=[{eligible:true,e2e_ms:300,number:1,url:'old',children:[{kind:'x86',url:'task1',association_valid:true,result:'SUCCESS',building:false,queue_ms:1,duration_ms:9,total_ms:10}]},{eligible:true,e2e_ms:300,number:2,url:'new',children:[]}];
const duplicate=JSON.parse(JSON.stringify(edge));duplicate[1].children=[{kind:'x86',url:'t1',association_valid:true,result:'SUCCESS',queue_ms:1,duration_ms:9,total_ms:10},{kind:'x86',url:'t2',association_valid:true,result:'SUCCESS',queue_ms:2,duration_ms:8,total_ms:10}];
const smallidx={start_ms:1,end_ms:2,repositories:['success','partial','failed','stale','zero'].map(name=>({name,status:name==='stale'?'success':name==='zero'?'success':name}))};
const small={};for(const e of smallidx.repositories)small[e.name]={meta:{start_ms:e.name==='stale'?0:1,end_ms:2},prs:e.name==='zero'?[]:[{number:1,repository:e.name,batches:edge}]};
const selected=m.repositoryRows(smallidx,small).map(r=>({name:r.name,included:r.included,count:r.prs.length}));
console.log(JSON.stringify({bad:t.chartStats(bad),mix:t.chartStats(mix),groups,aggregate:m.aggregate(all),tie:m.metrics(edge),ambiguous:m.metrics(duplicate),selected}));
"""
def node_cases():
    a=json.loads(subprocess.check_output(['node','-e',NODE,str(ROOT)],cwd=ROOT,text=True,encoding='utf8'))
    case('numeric-boundaries-node','REQ-017-AC01',{'count':0,'average':None,'p50':None,'p90':None},a['bad'])
    bad=[{'status':s,'duration_seconds':v,'pr':23,'approximate':False,'missing':[]} for s,v in [('success',None),('failure',''),('success',-1)]]
    case('numeric-boundaries-python','REQ-017-AC01',{'valid':0,'median':None,'p90':None},d.summary_of(bad))
    z=ref_stats([0,600,900]);case('mixed-validity-node','REQ-017-AC02 REQ-017-AC03 REQ-017-AC04',{'count':3,'average':z['mean'],'p50':z['p50'],'p90':z['p90']},a['mix'])
    case('all-unmatched-group-shapes','REQ-016-AC01 REQ-016-AC02',[['a','b','c'],['a','b'],['a','b']],a['groups'])
    case('ubs-tie-same-batch-no-fallback','REQ-041-AC02',{'representative_batch_number':2,'representative_batch_url':'new','x86':{'url':None,'total_ms':None}},a['tie'])
    case('ubs-ambiguous-category-no-fallback','REQ-041-AC02',{'representative_batch_number':2,'x86':{'url':None,'total_ms':None}},a['ambiguous'])
    case('ubs-cross-repo-status-stale-zero','REQ-041-AC03',[
         {'name':'success','included':True,'count':1},{'name':'partial','included':True,'count':1},
         {'name':'failed','included':False,'count':0},{'name':'stale','included':False,'count':0},
         {'name':'zero','included':True,'count':0}],a['selected'])
    case('current-ubs-independent-cross-repo-aggregate','REQ-041-AC01',R['real']['independent_ubs_aggregate'],a['aggregate'],scope='real current snapshots')
    R['real']['node_ubs_aggregate']=a['aggregate']

def main():
    model=read('audit/2026-10-09/evidence/requirements-model.json')
    ids=['REQ-014','REQ-015','REQ-016','REQ-017','REQ-018','REQ-019','REQ-037','REQ-041','REQ-046']
    R['requirements']=[r for r in model['requirements'] if r['id'] in ids]
    attempt_cases();pagination_cases();quality_cases();real_audit();node_cases()
    R['limits']=['No live API, collector cache writes, refresh, migration or deployment occurred; collect() is called only with all I/O mocked.',
                 'Current frozen snapshots are preserved inputs; their agreement cannot establish real source pagination or complete attempt history.',
                 'Full raw source evidence is not present; source accuracy and historical impact are unverified.',
                 'REQ-014 AC04/REQ-016 AC03-04 UI/CSV checks belong to browser reviewer; these cases only establish pure data behavior.',
                 'audit/2026-10-09 is read only; .playwright-mcp is untouched. Root coordinates the required commit.']
    R['source_evidence']=[{'path':str(p),'exists':(ROOT/p).exists(),'source_accuracy':'unverified'} for p in ['data/raw','data/efficiency.sqlite','evidence/triton/runs.json','evidence/triton/enriched-runs.json','evidence/triton/jobs','web/data/triton-manifest.json']]
    R['ac_coverage']={ac['id']:{'cases':[c['id'] for c in R['cases'] if ac['id'] in c['acs']],
                              'failed_cases':[c['id'] for c in R['cases'] if ac['id'] in c['acs'] and not c['passed']]}
                      for req in R['requirements'] for ac in req['acceptance']}
    test_file=Path(__file__).with_name('data-adversarial-tests.py')
    test_run=subprocess.run([sys.executable,'-B','-X','utf8',str(test_file)],cwd=ROOT,capture_output=True,text=True,encoding='utf8')
    R['audit_regression_suite']={'returncode':test_run.returncode,'tests':10,'explicit_expected_failures':6,
                                  'output':test_run.stdout+test_run.stderr,
                                  'interpretation':'Expected failures document unmet acceptance criteria; they are not proof those ACs pass.'}
    R['script_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    R['regression_script_sha256']=hashlib.sha256(test_file.read_bytes()).hexdigest()
    R['counts']={'cases':len(R['cases']),'passed':sum(c['passed'] for c in R['cases']),'failed':sum(not c['passed'] for c in R['cases'])}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/'data-adversarial.json').write_text(json.dumps(safe(R),ensure_ascii=False,indent=2)+'\n',encoding='utf8')
    lines=['# Current data adversarial audit','',f"HEAD: {R['head']}",'',f"Cases: {R['counts']}",'','## Confirmed current-code failures','']
    for c in R['cases']:
        if not c['passed']:lines.extend([f"- {c['severity']} {c['id']} ({', '.join(c['acs'])})",f"  Expected: `{json.dumps(c['expected'],ensure_ascii=False)}`",f"  Actual: `{json.dumps(c['actual'],ensure_ascii=False)}`",f"  Code: {c['location']}"])
    lines.extend(['','## Evidence limits','']+['- '+x for x in R['limits']])
    (OUT/'data-adversarial.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print(json.dumps({'counts':R['counts'],'failures':[c['id'] for c in R['cases'] if not c['passed']]},ensure_ascii=False))

if __name__=='__main__':main()
