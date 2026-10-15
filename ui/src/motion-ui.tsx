import React,{useEffect,useMemo,useRef,useState} from 'react';
import {useClock} from './clock.js';
import {DOT_BITS,easeInOut,shape,type Point,type Raster,type Shape} from './motion.js';
import {Rows} from './rows.js';
import {colors,type Report,type Row} from './types.js';
import {motionPalette as palette,rasterRows,usageMinimap,type Minimap} from './minimap.js';
import {MinimapMorph} from './minimap-motion.js';
import {face,LitMorph,MORPH_MS,ENTER_MS,type Face} from './lit-morph.js';
import {fade} from './light.js';
import {amountFrame,readAmounts,renderAmounts,type Amounts} from './amounts.js';
/** Subscribe to Ink's shared clock only while moving between actual datasets. */
type Controller<T>={copy:()=>Controller<T>;morphTo:(target:T,now:number,duration:number,direction?:number)=>void;update:(now:number)=>boolean;render:(width:number,height:number)=>Raster;enter?:(now:number,duration?:number)=>void};
type MotionState<T>={controller:Controller<T>;key:string;target:T;enabled:boolean;active:boolean};
const curveController=(target:Minimap):Controller<Minimap>=>new MinimapMorph(target);
const litController=(target:Face):Controller<Face>=>new LitMorph(target);
const emptyFace=face([],palette);
/** Keys are calendar months (YYYY-MM), so string order is navigation direction. */
const direction=(from:string,to:string):number=>to<from?-1:1;
function useMotion<T>(target:T,key:string,enabled:boolean,create:(target:T)=>Controller<T>,duration:number,intro=0):{controller:Controller<T>;active:boolean} {
  const [stored,setMotion]=useState<MotionState<T>>(()=>{
    const controller=create(target),entering=enabled&&intro>0&&!!controller.enter;
    if(entering)controller.enter!(performance.now(),intro);
    return {controller,key,target,enabled,active:entering};
  });
  let motion=stored;
  if(stored.key!==key||stored.target!==target||stored.enabled!==enabled) {
    // Prepare before children commit: an effect would flash the finished target.
    const controller=stored.controller.copy(),active=enabled&&stored.key!==key;
    controller.morphTo(target,performance.now(),active?duration:0,direction(stored.key,key));
    motion={controller,key,target,enabled,active};setMotion(motion);
  }
  // One shared clock drives every animation; it stops when nothing moves.
  const frame=useClock(motion.active);
  const moving=motion.active&&motion.controller.update(performance.now());
  useEffect(()=>{
    if(motion.active&&!moving)setMotion(current=>current===motion?{...current,active:false}:current);
  },[frame,motion,moving]);
  return {controller:motion.controller,active:moving};
}
export const FADE_MS=420;
type Fade={key:string;started:number;active:boolean;direction:number};
/** Progress 0..1 that restarts whenever `key` changes (and on mount); idle at 1.
 * `direction` follows month order so text sweeps the same way as the plot wave. */
export function useFade(key:string,enabled:boolean,duration=FADE_MS):{t:number;direction:number} {
  const [state,setState]=useState<Fade>(()=>({key,started:performance.now(),active:enabled,direction:-1}));
  let current=state;
  if(state.key!==key){current={key,started:performance.now(),active:enabled,direction:direction(state.key,key)};setState(current);}
  const frame=useClock(current.active);
  const t=current.active?Math.min(1,(performance.now()-current.started)/duration):1;
  useEffect(()=>{if(current.active&&t>=1)setState(s=>s===current?{...s,active:false}:s);},[frame,current,t]);
  return {t,direction:current.direction};
}
type Roll={key:string;from:Amounts;started:number;active:boolean};
/** Roll legend and budget amounts from the last visible values to the new month's.
 * Retargets start from what is on screen; settled rows are returned unchanged. */
export function useAmountRoll(rows:Row[],key:string,enabled:boolean,duration=MORPH_MS):Row[] {
  const finals=useMemo(()=>readAmounts(rows),[rows]),shown=useRef<Amounts>(finals);
  const [state,setState]=useState<Roll>(()=>({key,from:finals,started:0,active:false}));
  let current=state;
  if(state.key!==key){current={key,from:shown.current,started:performance.now(),active:enabled&&finals.size>0};setState(current);}
  const tick=useClock(current.active);
  const t=current.active?Math.min(1,(performance.now()-current.started)/duration):1;
  useEffect(()=>{if(current.active&&t>=1)setState(s=>s===current?{...s,active:false}:s);},[tick,current,t]);
  if(!current.active||t>=1){shown.current=finals;return rows;}
  const roll=amountFrame(current.from,finals,t);shown.current=roll.values;
  return renderAmounts(rows,roll);
}
const TEXT_STAGGER=.45;
/** Sweep text in from the background: each segment starts by its column (wave direction)
 * with a slight row offset. Uncolored segments and text never change; exact at t=1. */
export function fadeRows(rows:Row[],t:number,floor=.3,direction=-1):Row[] {
  if(t>=1)return rows;
  const width=Math.max(1,...rows.map(row=>row.reduce((n,s)=>n+s.text.length,0))),n=Math.max(1,rows.length);
  const delays=rows.map((row,index)=>{
    let column=0;
    return row.map(segment=>{
      const start=column;column+=segment.text.length;
      if(!segment.color)return -1;
      const along=direction>0?1-start/width:start/width;
      return TEXT_STAGGER*(.8*along+.2*index/n);
    });
  });
  // Start the sweep at the first colored segment, so nothing waits on empty columns.
  const first=Math.min(TEXT_STAGGER,...delays.flat().filter(d=>d>=0));
  return rows.map((row,index)=>row.map((segment,j)=>{
    const delay=delays[index]![j]!;if(delay<0)return segment;
    // Ease-out: text answers the key press at once, then settles softly.
    const p=Math.max(0,Math.min(1,(t-(delay-first))/(1-TEXT_STAGGER))),o=1-(1-p)**3;
    return o>=1?segment:{...segment,color:fade(segment.color!,floor+(1-floor)*o)};
  }));
}
export function FadeRows({rows,fadeKey,enabled,color}:{rows:Row[];fadeKey:string;enabled:boolean;color:boolean}):React.ReactElement {
  const {t,direction:dir}=useFade(fadeKey,enabled);
  const rolling=useAmountRoll(rows,fadeKey,enabled);
  return <Rows rows={fadeRows(rolling,t,.15,dir)} color={color}/>;
}
export function UsageMinimap({report,month,enabled,color,ascii,width=20}: {report:Report;month:string;enabled:boolean;color:boolean;ascii:boolean;width?:number}):React.ReactElement {
  const map=useMemo(()=>usageMinimap(report,width),[report,width]);
  const {controller,active}=useMotion(map,month,enabled,curveController,MORPH_MS);
  // Stable identity when idle, so the screen writer skips unchanged frames.
  const staticRows=useMemo(()=>rasterRows(map.raster,ascii,map.unknown),[map,ascii]);
  const rows=active?rasterRows(controller.render(map.raster.width,map.raster.height),ascii,map.unknown):staticRows;
  return <Rows rows={rows} color={color} slot="minimap"/>;
}
export type GraphScene={shape:Shape;face:Face;points:Point[];top:number;left:number;width:number;height:number};
const lineMasks:Record<string,number>={'─':0x24,'╶':0x20,'│':0x47,'╭':0x64,'╮':0xa4,'╰':0x27,'╯':0x3c,'┼':0x67,'┴':0x27,'┬':0x64,'┤':0x47,'├':0x67};
export function graphScene(rows:Row[],width:number):GraphScene|null {
  const indices=rows.flatMap((row,index)=>/^\s*\$[\d,.]+ [┤┼] /.test(row[0]?.text??'')?[index]:[]);
  if(!indices.length||indices.some((n,i)=>i>0&&n!==indices[i-1]!+1))return null; // Keep multi-panel/narrow graphs static.
  const top=indices[0]!,left=[...rows[top]![0]!.text].length,height=indices.length,plotWidth=width-left;
  if(plotWidth<1||height>80)return null;
  const points:Point[]=[];
  for(let y=0;y<height;y++) {
    let x=0;
    for(const segment of rows[top+y]!.slice(1)) {
      const color=Math.max(0,palette.indexOf(segment.color??colors.coral));
      for(const glyph of segment.text) {
        const mask=lineMasks[glyph]??0;
        for(let dy=0;dy<4;dy++)for(let dx=0;dx<2;dx++)if(mask&DOT_BITS[dy]![dx]!)points.push({x:(x*2+dx+.5)/(plotWidth*2),y:(y*4+dy+.5)/(height*4),color});
        x++;
      }
    }
  }
  if(!points.length)return null;
  return {shape:shape(points,512),face:face(points,palette),points,top,left,width:plotWidth,height};
}
export function overlayGraph(rows:Row[],scene:GraphScene,raster:Raster):Row[] {
  const result=[...rows],painted=rasterRows(raster);
  for(let y=0;y<scene.height;y++) {
    const original=rows[scene.top+y]!;
    // Most rows have no unknown prices. Reuse grouped raster segments directly
    // rather than allocating and merging an object for every terminal cell.
    if(!original.slice(1).some(segment=>segment.text.includes('?'))) {result[scene.top+y]=[original[0]!,...painted[y]!];continue;}
    const cells=original.slice(1).flatMap(s=>[...s.text].map(text=>({...s,text})));
    const overlay=painted[y]!.flatMap(s=>[...s.text].map(text=>({...s,text})));
    // Unknown-price markers remain readable, even during a visual transition.
    const line:Row=[original[0]!];
    for(let x=0;x<scene.width;x++) {
      const cell=cells[x]?.text==='?'?cells[x]!:overlay[x]!,previous=line.at(-1);
      if(line.length>1&&previous&&previous.color===cell.color)previous.text+=cell.text;else line.push({...cell});
    }
    result[scene.top+y]=line;
  }
  return result;
}
export function MotionGraphRows({rows,width,month,color,enabled}: {rows:Row[];width:number;month:string;color:boolean;enabled:boolean}):React.ReactElement {
  const scene=useMemo(()=>graphScene(rows,width),[rows,width]);
  const target=scene?.face??emptyFace;
  // Lines grow out of the baseline on mount and flow into the next month's lines.
  const {controller,active}=useMotion<Face>(target,month,enabled&&scene!==null,litController,MORPH_MS,ENTER_MS);
  // Labels switch instantly between months (amounts roll instead); the sweep only
  // plays when the graph view opens, so axes never dim during a morph.
  const {t,direction:dir}=useFade('graph',enabled,MORPH_MS);
  const rolling=useAmountRoll(rows,month,enabled);
  const faded=fadeRows(rolling,t,.3,dir);
  return <Rows rows={active&&scene?overlayGraph(faded,scene,controller.render(scene.width,scene.height)):faded} color={color}/>;
}
