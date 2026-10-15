import React from 'react';
import {describe,expect,test} from 'bun:test';
import {mkdtempSync,renameSync,writeFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {render} from 'ink';
import {PassThrough} from 'node:stream';
import {mergeDataset,watchDataset} from '../src/live.js';
import {parseDataset,type Dataset,type Report} from '../src/types.js';
import {Dashboard} from '../src/app.js';
import {fixture} from './fixture.js';
const options={color:false,ascii:false,width:null,height:8};
const dataset=(months:[string,Report][],initial=months.at(-1)![0],stale?:boolean):Dataset=>({schema_version:1,initial_month:initial,initial_view:'graph',options,months:months.map(([month,report])=>({month,report})),...(stale===undefined?{}:{stale})});
const scaled=(report:Report,factor:number):Report=>({...report,series:report.series.map(s=>({...s,known_cost_usd:s.known_cost_usd*factor,daily:s.daily.map(d=>({...d,cost_usd:d.cost_usd===null?null:d.cost_usd*factor}))}))});
describe('stale-while-revalidate start',()=>{
  test('unchanged months keep identity; changed months get a new revision',()=>{
    const sep=fixture('2026-09',30),oct=fixture('2026-10');
    const before=dataset([['2026-09',sep],['2026-10',oct]],'2026-10',true);
    const after=mergeDataset(before,dataset([['2026-09',structuredClone({...sep,generated:'later'} as Report)],['2026-10',scaled(oct,2)]]));
    expect(after.months[0]).toBe(before.months[0]!);
    expect(after.months[1]!.revision).toBe(1);
    expect(after.stale).toBeUndefined();
    expect(mergeDataset(after,dataset([['2026-09',sep],['2026-10',scaled(oct,3)],['2026-11',fixture('2026-11',30)]])).months.map(m=>m.revision??0)).toEqual([0,2,0]);
    expect(()=>parseDataset({...before,stale:'yes'})).toThrow();
  });
  test('the watcher ignores stale rewrites and delivers the fresh file once',async()=>{
    const dir=mkdtempSync(join(tmpdir(),'aisad-live-')),path=join(dir,'data.json');
    const write=(value:unknown)=>{writeFileSync(path+'.tmp',JSON.stringify(value));renameSync(path+'.tmp',path);};
    const stale=dataset([['2026-10',fixture()]],'2026-10',true);write(stale);
    const seen:Dataset[]=[];const stop=watchDataset(path,d=>seen.push(d),5);
    await Bun.sleep(20);write({...stale,options:{...options,height:9}});await Bun.sleep(30);
    expect(seen).toHaveLength(0);
    write('{broken');await Bun.sleep(30);expect(seen).toHaveLength(0);
    write(dataset([['2026-10',scaled(fixture(),2)]]));await Bun.sleep(40);
    write(dataset([['2026-10',scaled(fixture(),4)]]));await Bun.sleep(40);
    stop();
    expect(seen).toHaveLength(1);expect(seen[0]!.months[0]!.report.series[0]!.known_cost_usd).toBeCloseTo(190.7);
  });
  test('fresh data follows the new initial month until the user navigates',async()=>{
    process.env.AISAD_REDUCED_MOTION='1';
    const sep=fixture('2026-09',30),oct=fixture('2026-10');
    const stale=dataset([['2026-08',fixture('2026-08')],['2026-09',sep]],'2026-09',true);
    const fresh=mergeDataset(stale,dataset([['2026-08',fixture('2026-08')],['2026-09',sep],['2026-10',oct]],'2026-10'));
    const run=async(keys:string):Promise<{month:string;text:string}>=>{
      const stdout=Object.assign(new PassThrough(),{columns:100,rows:30,isTTY:true}) as unknown as NodeJS.WriteStream;
      const stdin=Object.assign(new PassThrough(),{isTTY:true,setRawMode(){},ref(){},unref(){}}) as unknown as NodeJS.ReadStream;
      let text='';(stdout as unknown as PassThrough).on('data',chunk=>{text+=String(chunk);});
      let month='';const view=(d:Dataset)=><Dashboard dataset={d} onExit={state=>{month=d.months[state.index]!.month;}}/>;
      const app=render(view(stale),{stdout,stdin,patchConsole:false,exitOnCtrlC:false,interactive:true});
      await Bun.sleep(40);for(const key of keys){(stdin as unknown as PassThrough).write(key);await Bun.sleep(20);}
      app.rerender(view(fresh));await Bun.sleep(40);
      (stdin as unknown as PassThrough).write('q');await Bun.sleep(30);app.unmount();
      return {month,text};
    };
    const idle=await run('');
    expect(idle.text).toContain('Updating');expect(idle.month).toBe('2026-10');
    expect((await run('h')).month).toBe('2026-08');
    // R asks for a refresh only when the collector supports it and nothing is pending.
    const stdout=Object.assign(new PassThrough(),{columns:100,rows:30,isTTY:true}) as unknown as NodeJS.WriteStream;
    const stdin=Object.assign(new PassThrough(),{isTTY:true,setRawMode(){},ref(){},unref(){}}) as unknown as NodeJS.ReadStream;
    let text='';(stdout as unknown as PassThrough).on('data',chunk=>{text+=String(chunk);});
    let asked=0;const app=render(<Dashboard dataset={{...fresh,refresh:true}} onRefresh={()=>{asked++;}} onExit={()=>{}}/>,{stdout,stdin,patchConsole:false,exitOnCtrlC:false,interactive:true});
    await Bun.sleep(40);(stdin as unknown as PassThrough).write('r');await Bun.sleep(20);app.unmount();
    expect(asked).toBe(1);expect(text).toContain('R refresh');
    delete process.env.AISAD_REDUCED_MOTION;
  });
});
