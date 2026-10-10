(function(root){
  const DEFAULT_HASH='#ubs';
  const LEGACY={repositories:'#ubs',overview:'#ubs/repo/ubs-engine',prs:'#ubs/repo/ubs-engine',quality:'#ubs/repo/ubs-engine/quality',method:'#method'};
  function decode(part){try{return decodeURIComponent(part)}catch{return part}}
  function partsOf(hash){return String(hash==null?'':hash).replace(/^#/,'').split('/').filter(Boolean).map(decode)}
  function parseHash(hash){
    const parts=partsOf(hash);
    if(parts[0]==='triton')return {domain:'triton'};
    if(parts[0]==='method')return {domain:'method'};
    if(parts[0]==='ubs'){
      if(parts[1]==='repo'&&parts[2])return parts[3]==='quality'?{domain:'ubs',repo:parts[2],sub:'quality'}:{domain:'ubs',repo:parts[2]};
      return {domain:'ubs'};
    }
    return null;
  }
  function toHash(route){
    if(!route)return DEFAULT_HASH;
    if(route.domain==='triton'||route.domain==='method')return '#'+route.domain;
    if(route.domain==='ubs'&&route.repo)return '#ubs/repo/'+encodeURIComponent(route.repo)+(route.sub==='quality'?'/quality':'');
    return DEFAULT_HASH;
  }
  function resolve(hash){
    const raw=String(hash==null?'':hash).replace(/^#/,'');
    const parts=raw.split('/').filter(Boolean);
    if(!parts.length)return DEFAULT_HASH;
    const head=decode(parts[0]);
    if(head==='repo'&&parts[1])return parts[2]==='method'?'#method':toHash({domain:'ubs',repo:decode(parts[1]),sub:parts[2]==='quality'?'quality':null});
    if(head==='ubs'||head==='triton'||head==='method'){const route=parseHash(raw);return route?toHash(route):DEFAULT_HASH}
    return LEGACY[head]||DEFAULT_HASH;
  }
  function keepPRPage(prevRepo,view,repo){return !(view==='ubs-repo'||view==='ubs-quality')||repo===prevRepo}
  /* ---- P-011: new #workbench / #projects/{id}/{task} scheme (introductory;
     the shell consumes these; the legacy parseHash/toHash/resolve remain the
     active model until the catalog-driven shell takes over) ---- */
  const PROJECT_TASKS=['overview','trends','records','quality','collection','method'];
  function parseQuery(qs){const out={};if(!qs)return out;for(const part of String(qs).split('&')){if(!part)continue;const idx=part.indexOf('='),key=decode(idx<0?part:part.slice(0,idx)),val=idx<0?'':decode(part.slice(idx+1));if(!key)continue;if(key in out)out[key]=Array.isArray(out[key])?out[key].concat(val):[out[key],val];else out[key]=val;}return out;}
  function serializeQuery(query){const parts=[];for(const key of Object.keys(query||{})){const values=Array.isArray(query[key])?query[key]:[query[key]];for(const v of values)parts.push(encodeURIComponent(key)+'='+encodeURIComponent(v==null?'':v));}return parts.length?'?'+parts.join('&'):'';}
  function parseRoute(hash){const raw=String(hash==null?'':hash).replace(/^#/,''),qIdx=raw.indexOf('?'),path=qIdx<0?raw:raw.slice(0,qIdx),query=parseQuery(qIdx<0?'':raw.slice(qIdx+1));if(path==='workbench')return {view:'workbench',query};const parts=path.split('/').filter(Boolean).map(decode);if(parts.length===3&&parts[0]==='projects'&&PROJECT_TASKS.includes(parts[2]))return {view:'projects',project:parts[1],task:parts[2],query};return null;}
  function formatRoute(route){if(!route)return '#workbench';if(route.view==='workbench')return '#workbench'+serializeQuery(route.query);if(route.view==='projects'&&route.project&&PROJECT_TASKS.includes(route.task))return '#projects/'+encodeURIComponent(route.project)+'/'+route.task+serializeQuery(route.query);return '#workbench';}
  /* Legacy hash -> intended new-route intent. ``repository`` carries the legacy
     short name; the shell resolves it to a stable repository id via the catalog. */
  function legacyIntent(hash){const raw=String(hash==null?'':hash).replace(/^#/,''),path=raw.split('?')[0],parts=path.split('/').filter(Boolean).map(decode);if(parseRoute(raw))return null;if(!parts.length)return {view:'projects',project:'ubs',task:'overview'};const head=parts[0];if(head==='ubs'){if(parts[1]==='repo'&&parts[2])return {view:'projects',project:'ubs',task:parts[3]==='quality'?'quality':'overview',repository:parts[2]};return {view:'projects',project:'ubs',task:'overview'};}if(head==='triton')return {view:'projects',project:'triton',task:'trends'};if(head==='method')return {view:'projects',project:null,task:'method'};if(head==='repositories')return {view:'projects',project:'ubs',task:'overview'};if(head==='overview')return {view:'projects',project:'ubs',task:'overview',repository:'ubs-engine'};if(head==='prs')return {view:'projects',project:'ubs',task:'records',repository:'ubs-engine',entity:'batches'};if(head==='quality')return {view:'projects',project:'ubs',task:'quality',repository:'ubs-engine'};if(head==='repo'&&parts[1])return {view:'projects',project:'ubs',task:parts[2]==='quality'?'quality':parts[2]==='method'?'method':'overview',repository:parts[1]};return null;}
  const api={parseHash,toHash,resolve,keepPRPage,PROJECT_TASKS,parseQuery,serializeQuery,parseRoute,formatRoute,legacyIntent};if(typeof module!=='undefined')module.exports=api;else root.Router=api;
})(typeof window!=='undefined'?window:globalThis);
