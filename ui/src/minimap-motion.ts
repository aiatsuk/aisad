import {curveRaster,motionPalette,type Curve,type Minimap} from './minimap.js';
import {band,fade,hexToRgb,HIGHLIGHT_RGB,mix} from './light.js';
import {easeInOut,type Raster} from './motion.js';
type Pose={provider:string;values:Float32Array;alpha:Float32Array};
const clone=(poses:readonly Pose[]):Pose[]=>poses.map(p=>({provider:p.provider,values:p.values.slice(),alpha:p.alpha.slice()}));
const poses=(map:Minimap):Pose[]=>map.curves.map(curve=>({provider:curve.provider,values:Float32Array.from({length:31},(_,i)=>curve.values[i]??0),alpha:Float32Array.from({length:31},(_,i)=>Number(curve.values[i]!==null&&curve.values[i]!==undefined))}));
/** Interpolate corresponding provider/day samples, then redraw connected lines.
 * Fixed x correspondence prevents the old particle cloud from scrambling curves. */
export class MinimapMorph {
  private current:Pose[];private from:Pose[];private to:Pose[];
  private days:number;private fromDays:number;private toDays:number;
  private started=0;private duration=0;private progress=1;
  constructor(map:Minimap) {this.current=poses(map);this.from=clone(this.current);this.to=clone(this.current);this.days=this.fromDays=this.toDays=map.days;}
  copy():MinimapMorph {
    const copy=Object.create(MinimapMorph.prototype) as MinimapMorph;
    copy.current=clone(this.current);copy.from=clone(this.current);copy.to=clone(this.current);
    copy.days=copy.fromDays=copy.toDays=this.days;copy.started=copy.duration=0;
    return copy;
  }
  morphTo(target:Minimap,now:number,duration=360):void {
    this.update(now);
    const next=poses(target),providers=[...new Set([...next.map(p=>p.provider),...this.current.map(p=>p.provider)])];
    const oldByProvider=new Map(this.current.map(p=>[p.provider,p])),newByProvider=new Map(next.map(p=>[p.provider,p]));
    this.from=[];this.to=[];
    for(const provider of providers) {
      const old=oldByProvider.get(provider),fresh=newByProvider.get(provider);
      // New/missing samples fade in place rather than flying from a fake zero.
      const source={provider,values:(old?.values??fresh!.values).slice(),alpha:old?.alpha.slice()??new Float32Array(31)};
      const destination={provider,values:(fresh?.values??old!.values).slice(),alpha:fresh?.alpha.slice()??new Float32Array(31)};
      for(let i=0;i<31;i++) {
        if(!source.alpha[i])source.values[i]=destination.values[i]!;
        if(!destination.alpha[i])destination.values[i]=source.values[i]!;
      }
      this.from.push(source);this.to.push(destination);
    }
    this.current=clone(this.from);this.fromDays=this.days;this.toDays=target.days;
    this.started=now;this.duration=duration;this.update(now);
  }
  update(now:number):boolean {
    const t=this.duration?Math.max(0,Math.min(1,(now-this.started)/this.duration)):1,e=easeInOut(t);
    this.progress=t;
    this.days=this.fromDays+(this.toDays-this.fromDays)*e;
    for(let p=0;p<this.current.length;p++)for(let i=0;i<31;i++) {
      this.current[p]!.values[i]=this.from[p]!.values[i]!+(this.to[p]!.values[i]!-this.from[p]!.values[i]!)*e;
      this.current[p]!.alpha[i]=this.from[p]!.alpha[i]!+(this.to[p]!.alpha[i]!-this.from[p]!.alpha[i]!)*e;
    }
    return t<1;
  }
  render(width:number,height:number):Raster {
    const curves:Curve[]=this.current.map(p=>({provider:p.provider,values:Array.from(p.values),alpha:p.alpha}));
    const raster=curveRaster(curves,this.days,width,height);
    if(this.progress>=1)return raster;
    // Codex-style light sweep travels with the morph, then leaves exact colors.
    const center=-4+(width+8)*easeInOut(this.progress),rgb=new Uint32Array(width*height);
    for(let cell=0;cell<width*height;cell++) {
      if(!raster.masks[cell])continue;
      const base=hexToRgb(fade(motionPalette[raster.colors[cell]!]!,raster.opacity![cell]!/255));
      rgb[cell]=mix(base,HIGHLIGHT_RGB,band(cell%width-center,4)*.6);
    }
    return {...raster,rgb};
  }
}
