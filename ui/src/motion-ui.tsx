import React,{useEffect,useMemo,useState} from 'react';
import {useAnimation} from 'ink';
import {DOT_BITS,Morph,shape,type Point,type Raster,type Shape} from './motion.js';
import {Rows} from './rows.js';
import {colors,type Report,type Row} from './types.js';
import {motionPalette as palette,rasterRows,usageMinimap,type Minimap} from './minimap.js';
import {MinimapMorph} from './minimap-motion.js';
/** Subscribe to Ink's shared clock only while moving between actual datasets. */
type Controller<T>={copy:()=>Controller<T>;morphTo:(target:T,now:number,duration:number)=>void;update:(now:number)=>boolean;render:(width:number,height:number)=>Raster};
type MotionState<T>={controller:Controller<T>;key:string;target:T;enabled:boolean;active:boolean};
const particleController=(target:Shape):Controller<Shape>=>new Morph(target);
const curveController=(target:Minimap):Controller<Minimap>=>new MinimapMorph(target);
function useMotion<T>(target:T,key:string,enabled:boolean,create:(target:T)=>Controller<T>):{controller:Controller<T>;active:boolean} {
  const [stored,setMotion]=useState<MotionState<T>>(()=>({controller:create(target),key,target,enabled,active:false}));
  let motion=stored;
  if(stored.key!==key||stored.target!==target||stored.enabled!==enabled) {
    // Prepare before children commit: an effect would flash the finished target.
    const controller=stored.controller.copy(),active=enabled&&stored.key!==key;
    controller.morphTo(target,performance.now(),active?360:0);
    motion={controller,key,target,enabled,active};setMotion(motion);
  }
  // main.tsx permits a render between ticks; idle components never subscribe.
  const tick=useAnimation({interval:34,isActive:motion.active});
  const moving=motion.active&&motion.controller.update(performance.now());
  useEffect(()=>{
    if(motion.active&&!moving)setMotion(current=>current===motion?{...current,active:false}:current);
  },[tick.frame,motion,moving]);
  return {controller:motion.controller,active:moving};
}
export function UsageMinimap({report,month,enabled,color,ascii,width=20}: {report:Report;month:string;enabled:boolean;color:boolean;ascii:boolean;width?:number}):React.ReactElement {
  const map=useMemo(()=>usageMinimap(report,width),[report,width]);
  const {controller,active}=useMotion(map,month,enabled,curveController);
  return <Rows rows={rasterRows(active?controller.render(map.raster.width,map.raster.height):map.raster,ascii,map.unknown)} color={color}/>;
}
export type GraphScene={shape:Shape;top:number;left:number;width:number;height:number};
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
  return {shape:shape(points,512),top,left,width:plotWidth,height};
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
  const target=useMemo(()=>scene?.shape??shape([],512),[scene]);
  const {controller,active}=useMotion(target,month,enabled&&scene!==null,particleController);
  return <Rows rows={active&&scene?overlayGraph(rows,scene,controller.render(scene.width,scene.height)):rows} color={color}/>;
}
