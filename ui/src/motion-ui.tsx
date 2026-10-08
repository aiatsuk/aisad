import React,{useEffect,useLayoutEffect,useMemo,useRef,useState} from 'react';
import {useAnimation} from 'ink';
import {badgeShape,braille,DOT_BITS,Morph,shape,type Point,type Raster,type Shape} from './motion.js';
import {Rows} from './rows.js';
import {colors,type Row} from './types.js';
const palette=[colors.coral,colors.lavender,colors.amber,'#d4ad9b',colors.text,'#70c7c7',colors.muted,'#e59b59'];
/** Only this small adapter subscribes to Ink's shared clock, and only while moving. */
function useMorph(target:Shape,key:string,enabled:boolean,via?:Shape,initial=false):{controller:Morph;active:boolean} {
  const [controller]=useState(()=>new Morph(initial&&enabled?badgeShape('ring',target.colors.length):target));
  const [active,setActive]=useState(initial&&enabled),last=useRef({key,target,enabled,initialized:false});
  const pending=useRef<{shape:Shape;at:number}|null>(null);
  const tick=useAnimation({interval:34,isActive:active});
  useLayoutEffect(()=>{
    const previous=last.current;last.current={key,target,enabled,initialized:true};
    if(previous.initialized&&previous.key===key&&previous.target===target&&previous.enabled===enabled)return;
    const now=performance.now();pending.current=null;
    // Resizing chart geometry settles to exact data; never animate an unavailable view.
    if(!enabled||previous.initialized&&previous.key===key){controller.morphTo(target,now,0);setActive(false);return;}
    if(!previous.initialized&&!initial)return;
    controller.morphTo(via??target,now,via?140:420);
    if(via)pending.current={shape:target,at:now+140};
    setActive(true);
  },[target,key,enabled,via,controller,initial]);
  useEffect(()=>{
    if(!active)return;
    const now=performance.now();
    if(pending.current&&now>=pending.current.at){controller.morphTo(pending.current.shape,now,280);pending.current=null;}
    if(!controller.update(now)&&!pending.current)setActive(false);
  },[tick.frame,active,controller]);
  if(active)controller.update(performance.now());
  return {controller,active};
}
function rasterRows(raster:Raster):Row[] {
  return Array.from({length:raster.height},(_,y)=>{
    const row:Row=[];
    for(let x=0;x<raster.width;x++) {
      const index=y*raster.width+x,mask=raster.masks[index]!,color=palette[raster.colors[index]!]!,text=braille(mask),previous=row.at(-1);
      if(previous?.color===color)previous.text+=text;else row.push({text,color});
    }
    return row;
  });
}
export function MotionBadge({index,view,enabled,color,ascii}: {index:number;view:'graph'|'weeks';enabled:boolean;color:boolean;ascii:boolean}):React.ReactElement {
  const previous=useRef(index);
  const target=useMemo(()=>badgeShape(view==='graph'?'graph':'weeks'),[view]);
  const via=useMemo(()=>index===previous.current?undefined:badgeShape(index<previous.current?'previous':'next'),[index,view]);
  useEffect(()=>{previous.current=index;},[index]);
  const {controller}=useMorph(target,index+':'+view,enabled,via,true);
  const rows=ascii?[[{text:view==='graph'?'~ ~ ~':'# # #'}],[]]:rasterRows(controller.render(10,2));
  return <Rows rows={rows} color={color}/>;
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
    const original=rows[scene.top+y]!,cells=original.slice(1).flatMap(s=>[...s.text].map(text=>({...s,text})));
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
  const {controller,active}=useMorph(target,month,enabled&&scene!==null);
  return <Rows rows={active&&scene?overlayGraph(rows,scene,controller.render(scene.width,scene.height)):rows} color={color}/>;
}
