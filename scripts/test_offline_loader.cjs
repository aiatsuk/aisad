// Run the actual embedded decoder with standard Web APIs; no browser or listener.
const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {gzipSync} = require('node:zlib');
const source = fs.readFileSync(path.join(__dirname,'../agent_usage.py'),'utf8');
const code = source.slice(source.indexOf('async function loadSnapshot('),source.indexOf('(async()=>{'));
const context = vm.createContext({Blob,Response,DecompressionStream,atob,Uint8Array,setTimeout});
vm.runInContext(code,context);
async function decode(data,progress) {
  context.node={textContent:JSON.stringify(data)};context.progress=progress;
  return JSON.parse(JSON.stringify(await vm.runInContext('loadSnapshot(node,progress)',context)));
}
// The collector's own writer packs a synthetic snapshot into many small parts.
function pack(snapshot,limit) {
  return JSON.parse(execFileSync(process.env.PYTHON||'python3',['-B','-c',
    'import json,sys; import agent_usage as a; print(json.dumps(a.pack_snapshot(json.load(sys.stdin),int(sys.argv[1]))))',String(limit)],
    {cwd:path.join(__dirname,'..'),input:JSON.stringify(snapshot),encoding:'utf8'}));
}
(async()=>{
  const data={rows:[{input:123456789,output:42,cost:null,model:'Кэш </script>'}],request_stats:[]};
  assert.deepEqual(await decode(data),data);
  const packed={encoding:'gzip-base64',data:gzipSync(JSON.stringify(data)).toString('base64')};
  assert.deepEqual(await decode(packed),data);
  await assert.rejects(decode({encoding:'gzip-base64',data:'not valid gzip'}));
  // Parts: arrays by item ranges, objects by key ranges, small keys together.
  const large={version:'test',titles:{'Claude:a':'Заголовок 🚀'},summary:{requests:400},empty:[],
    request_stats:Array.from({length:400},(_,i)=>({id:'r'+i,input:i===7?9007199254740991:i,cost:i%9?i/3:null,model:'Кэш </script>'})),
    event_previews:Object.fromEntries([['__proto__',[{kind:'usage',ts:1}]],['constructor',[{kind:'usage',ts:2}]],['Claude:old',null],
      ...Array.from({length:60},(_,i)=>['Codex:s'+i,[{kind:'usage',ts:i,date:'2026-09-05'}]])]),
    session_details:Array.from({length:60},(_,i)=>({id:'Codex:s'+i,children:[]}))};
  const parts=pack(large,1500);
  assert.equal(parts.encoding,'gzip-base64-parts');
  assert(parts.parts.length>15,'many parts');
  const seen=[];
  const restored=await decode(parts,(part,total)=>seen.push([part,total]));
  assert.deepEqual(restored,large);
  assert(Object.prototype.hasOwnProperty.call(restored.event_previews,'__proto__'));
  // Keys that name object internals are plain data; a part opening with one still merges.
  const awkward={event_previews:Object.fromEntries([['constructor',[1,2,3]],['Claude:b',[4,5,6]],['Claude:c',[7,8,9]]]),rows:[]};
  assert.deepEqual(await decode(pack(awkward,50)),awkward);
  assert.deepEqual(seen,parts.parts.map((_,i)=>[i+1,parts.parts.length]));
  // One bad part fails the whole snapshot; nothing half-built is returned.
  const corrupt=structuredClone(parts);corrupt.data[Math.floor(corrupt.data.length/2)]=gzipSync('{"cut":').toString('base64').slice(0,12);
  await assert.rejects(decode(corrupt));
  const garbage=structuredClone(parts);garbage.data[1]='not valid gzip';
  await assert.rejects(decode(garbage));
  const miscounted=structuredClone(parts);miscounted.parts[miscounted.parts.findIndex(p=>p.kind==='items')].count+=1;
  await assert.rejects(decode(miscounted),/does not match its manifest/);
  const unknown=structuredClone(parts);unknown.parts[0].kind='other';
  await assert.rejects(decode(unknown),/does not match its manifest/);
  await assert.rejects(decode({...parts,format:2}),/unknown or incomplete layout/);
  await assert.rejects(decode({...parts,data:parts.data.slice(1)}),/unknown or incomplete layout/);
  context.DecompressionStream=undefined;
  await assert.rejects(decode(packed),/cannot decompress/);
  await assert.rejects(decode(parts),/cannot decompress/);
  new vm.Script(source.split('</script><script>')[1].split('</script>')[0]);
  console.log('PASS offline loader: plain/compressed/parts roundtrip, unicode, missing prices, corrupt or miscounted parts and unsupported browser failures');
})().catch(e=>{console.error(e);process.exitCode=1});
