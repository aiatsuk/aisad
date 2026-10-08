import {mkdir,readdir,readFile,writeFile} from 'node:fs/promises';
import {join} from 'node:path';
await mkdir('dist',{recursive:true});
const result=await Bun.build({entrypoints:['src/main.tsx'],outdir:'dist',naming:'aisad-ui.mjs',target:'bun',format:'esm',minify:true,define:{'process.env.NODE_ENV':'"production"'},plugins:[{name:'offline-ink',setup(build){
  // Ink's optional devtools import is discovered before dead-code elimination.
  // Pin the public dependency's development-only gate off in this bundle.
  build.onLoad({filter:/\/ink\/build\/reconciler\.js$/},async ({path})=>{
    const source=await readFile(path,'utf8'),gate="process.env['DEV']";
    if(!source.includes(gate))throw new Error('Ink devtools gate changed; review the offline bundle');
    return {contents:source.replace(gate,"'false'"),loader:'js'};
  });
}}]});
if(!result.success) throw new Error(result.logs.map(String).join('\n'));
const notices:string[]=[];
for(const entry of (await readdir('node_modules')).sort()) {
  if(entry.startsWith('.'))continue;
  const dirs=entry.startsWith('@')?(await readdir(join('node_modules',entry))).sort().map(p=>join(entry,p)):[entry];
  for(const dir of dirs) {
    const root=join('node_modules',dir);
    const pkg=JSON.parse(await readFile(join(root,'package.json'),'utf8')) as {name:string;version:string};
    const file=(await readdir(root)).sort().find(name=>/^(license|licence|copying)(\.|$)/i.test(name));
    if(file)notices.push(pkg.name+' '+pkg.version+'\n'+await readFile(join(root,file),'utf8'));
  }
}
await writeFile('dist/THIRD_PARTY_NOTICES.txt',notices.join('\n\n---\n\n'));
console.log('Bundled AISAD Ink UI and dependency license notices.');

const inputs:Record<string,string>={};
for(const name of ['build.ts','package.json','tsconfig.json','bun.lock',...(await readdir('src')).sort().map(name=>'src/'+name)]) {
  inputs[name]=new Bun.CryptoHasher('sha256').update(await readFile(name)).digest('hex');
}
await writeFile('dist/build-meta.json',JSON.stringify({schema_version:1,inputs})+'\n');
