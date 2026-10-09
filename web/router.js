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
  const api={parseHash,toHash,resolve,keepPRPage};if(typeof module!=='undefined')module.exports=api;else root.Router=api;
})(typeof window!=='undefined'?window:globalThis);
