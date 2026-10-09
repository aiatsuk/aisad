import {braille,DOT_BITS,type Raster} from './motion.js';
import {colors,providerColor,type Report,type Row} from './types.js';
export const motionPalette=[colors.coral,colors.lavender,colors.amber,'#d4ad9b',colors.text,'#70c7c7',colors.muted,'#e59b59'];
export type Curve={provider:string;values:(number|null)[];alpha?:ArrayLike<number>};
export type Minimap={raster:Raster;curves:Curve[];days:number;unknown:number[];maximum:number};
/** Thin provider curves; join only adjacent observed daily values. */
export function curveRaster(curves:readonly Curve[],days:number,width:number,height:number):Raster {
  const raster:Raster={width,height,masks:new Uint8Array(width*height),colors:new Uint8Array(width*height),opacity:new Uint8Array(width*height)};
  const columns=width*2,rows=height*4;
  const xFor=(index:number):number=>Math.min(columns-1,Math.round(index*(columns-1)/(days-1)));
  const yFor=(value:number):number=>Math.round((1-Math.max(0,Math.min(1,value)))*(rows-1));
  const put=(x:number,y:number,color:number,alpha:number):void=>{
    const cell=(y>>2)*width+(x>>1);
    raster.masks[cell]=raster.masks[cell]!|DOT_BITS[y&3]![x&1]!;
    const opacity=Math.round(alpha*255);
    if(opacity>=raster.opacity![cell]!){raster.colors[cell]=color;raster.opacity![cell]=opacity;}
  };
  for(const curve of curves) {
    const color=motionPalette.indexOf(providerColor(curve.provider));
    curve.values.forEach((value,index)=>{
      const alpha=curve.alpha?.[index]??1;
      if(value===null||index>=days||alpha<.02)return;
      let x=xFor(index),y=yFor(value);put(x,y,color,alpha);
      const next=curve.values[index+1];if(next===null||next===undefined||index+1>=days||(curve.alpha?.[index+1]??1)<.02)return;
      const lineAlpha=Math.min(alpha,curve.alpha?.[index+1]??1);
      const nx=xFor(index+1),ny=yFor(next),dx=nx-x,dy=Math.abs(ny-y),sy=y<ny?1:-1;
      let error=dx-dy;
      while(x!==nx||y!==ny) {
        const twice=error*2;
        if(twice>-dy){error-=dy;x++;}
        if(twice<dx){error+=dx;y+=sy;}
        put(x,y,color,lineAlpha);
      }
    });
  }
  return raster;
}
/** Actual full-calendar daily costs, with one common scale across providers. */
export function usageMinimap(report:Pick<Report,'period'|'series'>,width=20,height=2):Minimap {
  if(!Number.isInteger(width)||width<1||width>240||!Number.isInteger(height)||height<1||height>80)throw new Error('Invalid minimap viewport');
  const month=report.period.from.slice(0,7),days=report.period.days;
  const dayIndex=(date:string):number=>date.slice(0,7)===month?Number(date.slice(8))-1:-1;
  const valid=(date:string):boolean=>dayIndex(date)>=0&&dayIndex(date)<days;
  const maximum=Math.max(0,...report.series.flatMap(s=>s.daily.filter(d=>valid(d.date)).map(d=>d.cost_usd??0)));
  const unknown=new Set<number>();
  const curves=report.series.map(series=>{
    const values:(number|null)[]=Array(days).fill(null);
    for(const day of series.daily) {
      if(!valid(day.date))continue;
      const index=dayIndex(day.date),x=Math.round(index*(width*2-1)/(days-1));
      if(day.cost_usd!==null)values[index]=day.cost_usd/(maximum||1);
      else if(day.observations)unknown.add((height-1)*width+(x>>1));
    }
    return {provider:series.provider,values};
  });
  return {raster:curveRaster(curves,days,width,height),curves,days,unknown:[...unknown],maximum};
}
export function rasterRows(raster:Raster,ascii=false,unknown:readonly number[]=[]):Row[] {
  const markers=new Set(unknown);
  return Array.from({length:raster.height},(_,y)=>{
    const row:Row=[];
    for(let x=0;x<raster.width;x++) {
      const index=y*raster.width+x,mask=raster.masks[index]!;
      let color=markers.has(index)?colors.muted:motionPalette[raster.colors[index]!]!;
      if(!markers.has(index)&&raster.opacity&&raster.opacity[index]!<255&&mask) {
        const opacity=raster.opacity[index]!/255;
        color='#'+[1,3,5].map(offset=>Math.round(27+(parseInt(color.slice(offset,offset+2),16)-27)*opacity).toString(16).padStart(2,'0')).join('');
      }
      const text=markers.has(index)?'?':ascii?(mask?'.':' '):braille(mask),previous=row.at(-1);
      if(previous?.color===color)previous.text+=text;else row.push({text,color});
    }
    return row;
  });
}
