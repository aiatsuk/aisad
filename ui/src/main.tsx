import React from 'react';
import {readFileSync,writeFileSync} from 'node:fs';
import {render} from 'ink';
import {Dashboard} from './app.js';
import {parseDataset} from './types.js';
const [input,output]=process.argv.slice(2);
if(!input||!output||!process.stdin.isTTY||!process.stdout.isTTY) throw new Error('AISAD UI requires dataset/state paths and a terminal');
const dataset=parseDataset(JSON.parse(readFileSync(input,'utf8')) as unknown);
const app=render(<Dashboard dataset={dataset} onExit={(state,code)=>{
  writeFileSync(output,JSON.stringify({month:dataset.months[state.index]!.month,view:state.view}),{mode:0o600});process.exitCode=code;
}}/>,{exitOnCtrlC:false,patchConsole:false,alternateScreen:true,incrementalRendering:true,interactive:true});
await app.waitUntilExit();
