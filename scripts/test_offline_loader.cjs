// Run the actual embedded decoder with standard Web APIs; no browser or listener.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const {gzipSync} = require('node:zlib');
const source = fs.readFileSync(path.join(__dirname,'../agent_usage.py'),'utf8');
const code = source.slice(source.indexOf('async function loadSnapshot('),source.indexOf('(async()=>{'));
const context = vm.createContext({Blob,Response,DecompressionStream,atob,Uint8Array});
vm.runInContext(code,context);
async function decode(data) {
  context.node={textContent:JSON.stringify(data)};
  return JSON.parse(JSON.stringify(await vm.runInContext('loadSnapshot(node)',context)));
}
(async()=>{
  const data={rows:[{input:123456789,output:42,cost:null,model:'Кэш </script>'}],request_stats:[]};
  assert.deepEqual(await decode(data),data);
  const packed={encoding:'gzip-base64',data:gzipSync(JSON.stringify(data)).toString('base64')};
  assert.deepEqual(await decode(packed),data);
  await assert.rejects(decode({encoding:'gzip-base64',data:'not valid gzip'}));
  context.DecompressionStream=undefined;
  await assert.rejects(decode(packed),/cannot decompress/);
  new vm.Script(source.split('</script><script>')[1].split('</script>')[0]);
  console.log('PASS offline loader: plain/compressed roundtrip, unicode, missing prices, corrupt data and unsupported browser failures');
})().catch(e=>{console.error(e);process.exitCode=1});
