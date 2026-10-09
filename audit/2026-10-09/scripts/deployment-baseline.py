"""Read-only public baseline capture. Writes only audit/2026-10-09 artifacts."""
import concurrent.futures, hashlib, json, platform, re, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
AUDIT=ROOT/'audit'/'2026-10-09'
OUT=AUDIT/'evidence'
TARGETS={
 'ubs-index': 'https://tianli-backkom.github.io/ubs_core_monitor/',
 'ubs-app': 'https://tianli-backkom.github.io/ubs_core_monitor/app.js',
 'ubs-core': 'https://tianli-backkom.github.io/ubs_core_monitor/core.js',
 'ubs-repositories': 'https://tianli-backkom.github.io/ubs_core_monitor/data/repositories.json',
 'ubs-snapshot': 'https://tianli-backkom.github.io/ubs_core_monitor/data/snapshot.json',
 'triton-index': 'https://tianli-backkom.github.io/Triton-Ascend_monitor/index.html',
 'triton-core': 'https://tianli-backkom.github.io/Triton-Ascend_monitor/web/triton-core.js',
}
def fetch(item):
 name,url=item
 row={'id':name,'requested_url':url,'retrieved_at':datetime.now(timezone.utc).isoformat()}
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'ubs-triton-read-only-audit/1.0'})
  with urllib.request.urlopen(req,timeout=25) as response:
   raw=response.read(); row.update(status=response.status,final_url=response.url,bytes=len(raw),headers={key:response.headers.get(key) for key in ['Content-Type','Last-Modified','ETag']})
  row['sha256']=hashlib.sha256(raw).hexdigest()
  source=raw.decode('utf-8','replace')
  embedded=re.search(r'<script[^>]*id=[\"\']data[\"\'][^>]*>(.*?)</script>',source,re.S)
  payload=None
  if embedded: payload=json.loads(embedded.group(1))
  elif name.endswith(('repositories','snapshot')): payload=json.loads(source)
  if payload is not None:
   row['payload_summary']={'keys':list(payload),'meta':payload.get('meta'),'collected_at':payload.get('collected_at'),'window_start':payload.get('window_start'),'window_end':payload.get('window_end'),'summary':payload.get('summary'),'prs':len(payload.get('prs',[])),'batches':len(payload.get('batches',[])),'repositories':len(payload.get('repositories',[]))}
   if 'repositories' in payload: row['payload_summary']['repositories_summary']=[{'name':x.get('name'),'status':x.get('status'),'snapshot':x.get('snapshot')} for x in payload['repositories']]
  if embedded:
   source=source[:embedded.start(1)]+'/* Embedded payload omitted; see deployment-oldsite-summary.json for counts and original response hash. */'+source[embedded.end(1):]
  if not name.endswith(('repositories','snapshot')):
   ext='html' if name.endswith('index') else 'js'
   target=OUT/('deployment-oldsite-'+name+'.'+ext)
   target.write_text(source,encoding='utf-8')
   row['saved_source']=str(target.relative_to(ROOT)).replace('\\','/')
  return row
 except Exception as exc:
  row.update(error=type(exc).__name__+': '+str(exc)); return row
if __name__=='__main__':
 OUT.mkdir(parents=True,exist_ok=True)
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool: rows=list(pool.map(fetch,TARGETS.items()))
 report={'schema_version':1,'scope':'Read-only public legacy sites; no collector or deployment invoked; large JSON summarized rather than saved','runtime':sys.version,'captured_at':datetime.now(timezone.utc).isoformat(),'sources':rows}
 target=OUT/'deployment-oldsite-summary.json';target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'output':str(target),'sources':[{'id':x['id'],'status':x.get('status'),'bytes':x.get('bytes'),'error':x.get('error'),'saved_source':x.get('saved_source'),'payload_summary':{k:v for k,v in (x.get('payload_summary') or {}).items() if k not in ['meta']}} for x in rows]},ensure_ascii=False,indent=2))
