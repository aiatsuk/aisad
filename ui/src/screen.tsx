import React,{createContext,useCallback,useContext,useLayoutEffect,useMemo,useRef} from 'react';
import {useStdout} from 'ink';
import chalk from 'chalk';
import type {Row} from './types.js';
/**
 * Direct frame writer for the full-screen dashboard.
 *
 * Ink rebuilds and re-tokenizes the whole screen on every frame; on slower
 * machines that alone costs 15–20 ms, too slow for 60–120 fps motion. Ink still owns
 * input, raw mode, the alternate screen, resize events and cleanup, but its tree
 * renders nothing visible here. Components register their rows into named slots;
 * after each commit the writer composes the screen, compares it cell by cell with
 * the last frame and rewrites only changed runs with minimal color codes, inside
 * one synchronized update. Fewer bytes matter as much as CPU: slow terminals
 * block the writer while they parse.
 */
type Screen={set:(slot:string,rows:Row[])=>void};
const ScreenContext=createContext<Screen|null>(null);
export const useScreen=():Screen|null=>useContext(ScreenContext);
const BEGIN='\x1b[?2026h',END='\x1b[?2026l';
/** Cut a row to `width` terminal cells (all dashboard glyphs are one cell wide). */
export function fitRow(row:Row,width:number):Row {
  // Rows that already fit keep their identity, so per-row caches stay warm across frames.
  if(row.reduce((n,s)=>n+s.text.length,0)<=width&&!row.some(s=>/[\ud800-\udbff]/.test(s.text)))return row;
  let left=width;const result:Row=[];
  for(const segment of row) {
    if(left<=0)break;
    const chars=[...segment.text];
    if(chars.length<=left){result.push(segment);left-=chars.length;}
    else {result.push({...segment,text:chars.slice(0,left).join('')});left=0;}
  }
  return result;
}
const width=(row:Row):number=>row.reduce((n,s)=>n+[...s.text].length,0);
/** Content rows, then a two-line footer: hint text bottom-left, minimap right-aligned. */
export function composeScreen(main:Row[],minimap:Row[],footer:Row,columns:number):Row[] {
  const lines=main.map(row=>fitRow(row,columns));
  for(let i=0;i<2;i++) {
    const left:Row=i===1?fitRow(footer,columns):[],map=minimap[i]??[],mapWidth=width(map);
    const gap=Math.max(1,columns-width(left)-mapWidth);
    lines.push(mapWidth&&width(left)+1+mapWidth<=columns?[...left,{text:' '.repeat(gap)},...map]:left);
  }
  return lines;
}
/** SGR open sequence for a style, via Ink's chalk (same 16/256/truecolor level). */
const opens=new Map<string,string>();
export function openCode(color:string|undefined,bold:boolean,enabled:boolean):string {
  if(!enabled||(!color&&!bold)||chalk.level===0)return bold&&chalk.level>0?'\x1b[1m':'';
  const key=(color??'')+(bold?'!':'');let code=opens.get(key);
  if(code===undefined){let c=color?chalk.hex(color):chalk;if(bold)c=c.bold;code=c('\u0000').split('\u0000')[0]!;if(opens.size<8192)opens.set(key,code);}
  return code;
}
/** A screen line as parallel arrays of glyphs and style codes ('' = default). */
type Cells={chars:string[];styles:string[]};
const cellCache=[new WeakMap<Row,Cells>(),new WeakMap<Row,Cells>()];
/** Cells for a row, cached by row identity: unchanged rows cost nothing per frame. */
export function toCells(row:Row,color:boolean):Cells {
  const cache=cellCache[color?1:0]!,hit=cache.get(row);if(hit)return hit;
  const cells=buildCells(row,color);cache.set(row,cells);return cells;
}
function buildCells(row:Row,color:boolean):Cells {
  const chars:string[]=[],styles:string[]=[];
  for(const segment of row){const style=openCode(segment.color,segment.bold??false,color);for(const ch of segment.text){chars.push(ch);styles.push(style);}}
  return {chars,styles};
}
const RESET='\x1b[0m';
/** Encode cells [from,to) with minimal SGR changes; spaces never switch style. */
export function encodeSpan(cells:Cells,from:number,to:number):string {
  let out='',current='';
  for(let x=from;x<to;x++) {
    const ch=cells.chars[x]??' ',style=cells.styles[x]??'';
    if(ch!==' '&&style!==current){out+=(current?RESET:'')+style;current=style;}
    out+=ch;
  }
  return current?out+RESET:out;
}
/** Changed column runs; short unchanged gaps are rewritten rather than re-addressed. */
export function changedRuns(before:Cells|undefined,after:Cells,join=6):[number,number][] {
  const width=Math.max(after.chars.length,before?.chars.length??0),runs:[number,number][]=[];
  const same=(x:number)=>{
    const a=after.chars[x]??' ',b=before?.chars[x]??' ';
    return a===b&&(a===' '||(after.styles[x]??'')===(before?.styles[x]??''));
  };
  for(let x=0;x<width;x++) {
    if(same(x))continue;
    const last=runs.at(-1);
    if(last&&x-last[1]<=join)last[1]=x+1;else runs.push([x,x+1]);
  }
  return runs;
}
export function ScreenWriter({columns,lines,color,footer,children}:{columns:number;lines:number;color:boolean;footer:Row;children:React.ReactNode}):React.ReactElement {
  const {stdout}=useStdout();
  const slots=useRef(new Map<string,Row[]>()),previous=useRef<Cells[]>([]),size=useRef(''),pending=useRef(false);
  const props=useRef({columns,lines,color,footer});props.current={columns,lines,color,footer};
  const flush=useCallback(()=>{
    pending.current=false;
    const {columns,lines,color,footer}=props.current;
    const screen=composeScreen(slots.current.get('main')??[],slots.current.get('minimap')??[],footer,columns).slice(0,Math.max(1,lines));
    const next=screen.map(row=>toCells(row,color));
    const key=columns+'x'+lines+(color?'c':'m');
    let out='';
    if(size.current!==key){out+='\x1b[H\x1b[2J';previous.current=[];size.current=key;}
    const old=previous.current;
    for(let y=0;y<Math.max(next.length,old.length);y++) {
      const line=next[y]??{chars:[],styles:[]};
      if(line===old[y])continue;
      for(const [from,to] of changedRuns(old[y],line)) {
        // Past the end of the new line: erase instead of writing spaces.
        const end=Math.min(to,line.chars.length);
        out+='\x1b['+(y+1)+';'+(from+1)+'H'+(end>from?encodeSpan(line,from,end):'')+(to>line.chars.length?'\x1b[K':'');
      }
    }
    previous.current=next;
    if(out)stdout.write(BEGIN+out+END);
  },[stdout]);
  const schedule=useCallback(()=>{if(!pending.current){pending.current=true;queueMicrotask(flush);}},[flush]);
  const screen=useMemo<Screen>(()=>({set(slot,rows){if(slots.current.get(slot)!==rows){slots.current.set(slot,rows);schedule();}}}),[schedule]);
  // Size, color or footer changes repaint even when no slot changed.
  useLayoutEffect(()=>{schedule();},[columns,lines,color,footer,schedule]);
  return <ScreenContext.Provider value={screen}>{children}</ScreenContext.Provider>;
}
/** Register rows into a screen slot after commit (no Ink output of its own). */
export function useSlot(screen:Screen,slot:string,rows:Row[]):void {
  useLayoutEffect(()=>{screen.set(slot,rows);},[screen,slot,rows]);
}
