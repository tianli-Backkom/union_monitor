const {test}=require('node:test');const assert=require('node:assert/strict');const R=require('../web/router.js');
test('parseHash parses every new route shape',()=>{
  assert.deepEqual(R.parseHash('#ubs'),{domain:'ubs'});
  assert.deepEqual(R.parseHash('#ubs/repo/ubs-engine'),{domain:'ubs',repo:'ubs-engine'});
  assert.deepEqual(R.parseHash('#ubs/repo/ubs-comm/quality'),{domain:'ubs',repo:'ubs-comm',sub:'quality'});
  assert.deepEqual(R.parseHash('#ubs/repo/OmniStateStore'),{domain:'ubs',repo:'OmniStateStore'});
  assert.deepEqual(R.parseHash('#triton'),{domain:'triton'});
  assert.deepEqual(R.parseHash('#method'),{domain:'method'});
});
test('parseHash decodes repo names and rejects legacy or unknown hashes',()=>{
  assert.deepEqual(R.parseHash('#ubs/repo/a%20b'),{domain:'ubs',repo:'a b'});
  assert.equal(R.parseHash(''),null);
  assert.equal(R.parseHash('#'),null);
  assert.equal(R.parseHash('#repositories'),null);
  assert.equal(R.parseHash('#overview'),null);
  assert.equal(R.parseHash('#prs'),null);
  assert.equal(R.parseHash('#quality'),null);
  assert.equal(R.parseHash('#xyz'),null);
  assert.equal(R.parseHash('#UBS'),null);
  assert.deepEqual(R.parseHash('#ubs/repo'),{domain:'ubs'});
});
test('toHash emits canonical hashes for every route',()=>{
  assert.equal(R.toHash({domain:'ubs'}),'#ubs');
  assert.equal(R.toHash({domain:'ubs',repo:'ubs-engine'}),'#ubs/repo/ubs-engine');
  assert.equal(R.toHash({domain:'ubs',repo:'ubs-engine',sub:'quality'}),'#ubs/repo/ubs-engine/quality');
  assert.equal(R.toHash({domain:'ubs',repo:'ubs-virt',sub:'other'}),'#ubs/repo/ubs-virt');
  assert.equal(R.toHash({domain:'triton'}),'#triton');
  assert.equal(R.toHash({domain:'method'}),'#method');
  assert.equal(R.toHash(null),'#ubs');
  assert.equal(R.toHash({domain:'ubs'}),'#ubs');
});
test('resolve maps every legacy hash to its new route',()=>{
  assert.equal(R.resolve(''),'#ubs');
  assert.equal(R.resolve('#'),'#ubs');
  assert.equal(R.resolve('#repositories'),'#ubs');
  assert.equal(R.resolve('#overview'),'#ubs/repo/ubs-engine');
  assert.equal(R.resolve('#prs'),'#ubs/repo/ubs-engine');
  assert.equal(R.resolve('#repo/ubs-virt'),'#ubs/repo/ubs-virt');
  assert.equal(R.resolve('#repo/ubs-virt/quality'),'#ubs/repo/ubs-virt/quality');
  assert.equal(R.resolve('#repo/ubs-virt/method'),'#method');
  assert.equal(R.resolve('#quality'),'#ubs/repo/ubs-engine/quality');
  assert.equal(R.resolve('#method'),'#method');
});
test('resolve canonicalizes near-canonical and unknown hashes to the default',()=>{
  assert.equal(R.resolve('#ubs'),'#ubs');
  assert.equal(R.resolve('ubs'),'#ubs');
  assert.equal(R.resolve('#ubs/'),'#ubs');
  assert.equal(R.resolve('#ubs/extra'),'#ubs');
  assert.equal(R.resolve('#ubs/repo'),'#ubs');
  assert.equal(R.resolve('#ubs/repo/ubs-engine/'),'#ubs/repo/ubs-engine');
  assert.equal(R.resolve('#ubs/repo/ubs-engine/quality'),'#ubs/repo/ubs-engine/quality');
  assert.equal(R.resolve('#ubs/repo/ubs-engine/unknown'),'#ubs/repo/ubs-engine');
  assert.equal(R.resolve('#triton'),'#triton');
  assert.equal(R.resolve('#method'),'#method');
  assert.equal(R.resolve('#unknown'),'#ubs');
  assert.equal(R.resolve('#repo'),'#ubs');
  assert.equal(R.resolve('#repos/itories'),'#ubs');
});
test('resolve is idempotent and round-trips with parseHash and toHash',()=>{
  for(const h of ['','#repositories','#overview','#prs','#repo/ham','#repo/ham/quality','#quality','#method','#nope','#ubs','#ubs/repo/ubs-engine','#ubs/repo/ubs-engine/quality','#triton']){
    const once=R.resolve(h);
    assert.equal(R.resolve(once),once);
    assert.equal(R.toHash(R.parseHash(once)),once);
  }
});
