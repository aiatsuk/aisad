import React from 'react';
import {describe,expect,test} from 'bun:test';
import {render} from 'ink';
import {PassThrough} from 'node:stream';
import {composeScreen,fitRow,ScreenWriter} from '../src/screen.js';
import {Rows} from '../src/rows.js';
import type {Row} from '../src/types.js';
const text=(rows:Row[])=>rows.map(row=>row.map(s=>s.text).join(''));
describe('direct screen writer',()=>{
  test('rows are cut to the terminal width without changing styles',()=>{
    const row:Row=[{text:'abc',color:'#d77757'},{text:'défg',bold:true}];
    expect(fitRow(row,5)).toEqual([{text:'abc',color:'#d77757'},{text:'dé',bold:true}]);
    expect(fitRow(row,99)).toEqual(row);expect(fitRow(row,0)).toEqual([]);
  });
  test('footer hint sits bottom-left and the minimap is right-aligned',()=>{
    const screen=composeScreen([[{text:'Cost per Day'}]],[[{text:'⣀⣤'}],[{text:'⠉⠛'}]],[{text:'Q quit'}],20);
    expect(text(screen)).toEqual(['Cost per Day',' '.repeat(18)+'⣀⣤','Q quit'+' '.repeat(12)+'⠉⠛']);
    expect(text(composeScreen([],[[{text:'x'.repeat(30)}]],[{text:'hint'}],20))).toEqual(['','hint']);
  });
  test('writes only changed lines inside one synchronized update, and nothing when idle',async()=>{
    const stdout=Object.assign(new PassThrough(),{columns:30,rows:6,isTTY:true}) as unknown as NodeJS.WriteStream;
    const stdin=Object.assign(new PassThrough(),{isTTY:true,setRawMode(){},ref(){},unref(){}}) as unknown as NodeJS.ReadStream;
    const chunks:string[]=[];(stdout as unknown as PassThrough).on('data',chunk=>chunks.push(String(chunk)));
    const footer:Row=[{text:'Q quit'}];
    const view=(lines:string[])=><ScreenWriter columns={30} lines={6} color={false} footer={footer}><Rows rows={lines.map(text=>[{text}])} color={false}/></ScreenWriter>;
    const app=render(view(['one','two','three']),{stdout,stdin,patchConsole:false,exitOnCtrlC:false,interactive:true});
    await new Promise(resolve=>setTimeout(resolve,30));
    const first=chunks.filter(c=>c.includes('\x1b[?2026h')).join('');
    expect(first).toContain('\x1b[2J');expect(first).toContain('one');expect(first).toContain('\x1b[5;1HQ quit');
    chunks.length=0;app.rerender(view(['one','TWO','three']));await new Promise(resolve=>setTimeout(resolve,30));
    const second=chunks.filter(c=>c.includes('\x1b[?2026h')).join('');
    expect(second).toBe('\x1b[?2026h\x1b[2;1HTWO\x1b[?2026l');
    chunks.length=0;app.rerender(view(['one','TWO','three']));await new Promise(resolve=>setTimeout(resolve,30));
    expect(chunks.filter(c=>c.includes('\x1b[?2026h'))).toEqual([]);
    app.unmount();
  });
});
