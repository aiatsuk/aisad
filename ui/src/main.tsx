import React from 'react';
import {readFileSync,writeFileSync} from 'node:fs';
import {dirname,join} from 'node:path';
import {render} from 'ink';
import {Dashboard} from './app.js';
import {parseDataset,type Dataset} from './types.js';
import {mergeDataset,watchDataset} from './live.js';
const [input,output]=process.argv.slice(2);
if(!input||!output||!process.stdin.isTTY||!process.stdout.isTTY) throw new Error('AISAD UI requires dataset/state paths and a terminal');
const source:string=input;
const dataset=parseDataset(JSON.parse(readFileSync(source,'utf8')) as unknown);
let current=dataset,stop=():void=>{};
const view=(shown:Dataset)=><Dashboard dataset={shown} onRefresh={shown.refresh?refresh:undefined} onExit={(state,code)=>{
  writeFileSync(output,JSON.stringify({month:shown.months[state.index]!.month,view:state.view}),{mode:0o600});process.exitCode=code;
}}/>;
// A stale dataset is being recollected; the collector replaces the file when fresh numbers are ready.
function follow():void {stop=watchDataset(source,fresh=>{current=mergeDataset(current,fresh);app.rerender(view(current));});}
/** R: ask the collector (it watches this directory) for one fresh collection. */
function refresh():void {
  if(current.stale)return;
  try{writeFileSync(join(dirname(source),'refresh.request'),'',{mode:0o600});}catch{return;}
  current={...current,stale:true};follow();app.rerender(view(current));
}
// Keep the render throttle (~5 ms) below the 8 ms motion clock; equal
// clock/throttle intervals can drop alternating ticks after timer rounding.
const app=render(view(dataset),{exitOnCtrlC:false,patchConsole:false,alternateScreen:true,incrementalRendering:true,interactive:true,maxFps:240});
if(dataset.stale)follow();
await app.waitUntilExit();
stop();
