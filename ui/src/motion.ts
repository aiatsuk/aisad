/** React-independent, normalized particle motion; no timers or terminal writes. */
export type Point = {x: number; y: number; color?: number};
export type Shape = {points: Float32Array; colors: Uint8Array; visible: boolean};
export type Raster = {width: number; height: number; masks: Uint8Array; colors: Uint8Array;opacity?:Uint8Array};
export const DOT_BITS = [[1,8],[2,16],[4,32],[64,128]] as const;
const clamp = (value: number): number => Math.max(0,Math.min(1,value));
/** Quintic ease-in-out: zero velocity and acceleration at both endpoints. */
export const easeInOut = (value:number):number => {const t=clamp(value);return t*t*t*(t*(6*t-15)+10);};
export function morton(x: number,y: number): number {
  const spread=(value:number):number=>{let n=Math.floor(clamp(value)*1023);n=(n|(n<<8))&0x00ff00ff;n=(n|(n<<4))&0x0f0f0f0f;n=(n|(n<<2))&0x33333333;return (n|(n<<1))&0x55555555;};
  return spread(x)|(spread(y)<<1);
}
export function shape(points: readonly Point[],count: number): Shape {
  if(!Number.isInteger(count)||count<1||count>800)throw new Error('Particle count must be 1..800');
  if(points.some(p=>!Number.isFinite(p.x)||!Number.isFinite(p.y)))throw new Error('Invalid shape coordinates');
  const ordered=[...points].sort((a,b)=>morton(a.x,a.y)-morton(b.x,b.y));
  const positions=new Float32Array(count*2),colors=new Uint8Array(count);
  for(let i=0;i<count;i++){const p=ordered[Math.min(ordered.length-1,Math.floor(i*ordered.length/count))]??{x:.5,y:.5};positions[i*2]=clamp(p.x);positions[i*2+1]=clamp(p.y);colors[i]=(p.color??0)%8;}
  return {points:positions,colors,visible:points.length>0};
}
export function badgeShape(kind:'ring'|'graph'|'weeks'|'previous'|'next',count=96): Shape {
  const points:Point[]=[];
  for(let i=0;i<count;i++) {
    const t=i/(count-1||1);
    if(kind==='ring')points.push({x:.5+.43*Math.cos(t*2*Math.PI),y:.5+.42*Math.sin(t*2*Math.PI),color:i%3});
    else if(kind==='graph')points.push({x:.07+.86*t,y:.5+.35*Math.sin(t*2.5*Math.PI),color:Math.floor(t*3)});
    else if(kind==='weeks'){const column=i%5,row=Math.floor(i/5)%3;points.push({x:.12+column*.19,y:.16+row*.34,color:column%3});}
    else {const x=.15+.65*Math.abs(2*t-1);points.push({x:kind==='previous'?x:1-x,y:.1+.8*t,color:1});}
  }
  return shape(points,count);
}
export class Morph {
  readonly count:number;
  readonly x:Float32Array;readonly y:Float32Array;readonly alpha:Float32Array;
  private readonly fromX:Float32Array;private readonly fromY:Float32Array;private readonly toX:Float32Array;private readonly toY:Float32Array;
  private readonly fromAlpha:Float32Array;private readonly toAlpha:Float32Array;private readonly colors:Uint8Array;
  private started=0;private duration=0;private raster:Raster={width:0,height:0,masks:new Uint8Array(),colors:new Uint8Array()};
  constructor(initial:Shape) {
    this.count=initial.colors.length;
    this.x=new Float32Array(this.count);this.y=new Float32Array(this.count);this.alpha=new Float32Array(this.count);
    this.fromX=new Float32Array(this.count);this.fromY=new Float32Array(this.count);this.toX=new Float32Array(this.count);this.toY=new Float32Array(this.count);
    this.fromAlpha=new Float32Array(this.count);this.toAlpha=new Float32Array(this.count);this.colors=new Uint8Array(this.count);
    for(let i=0;i<this.count;i++){this.x[i]=this.toX[i]=initial.points[i*2]!;this.y[i]=this.toY[i]=initial.points[i*2+1]!;this.alpha[i]=this.toAlpha[i]=Number(initial.visible);this.colors[i]=initial.colors[i]!;}
  }
  /** Fork only the visible pose; a prepared transition cannot mutate a committed one. */
  copy():Morph {
    const points=new Float32Array(this.count*2);
    for(let i=0;i<this.count;i++){points[i*2]=this.x[i]!;points[i*2+1]=this.y[i]!;}
    const result=new Morph({points,colors:this.colors,visible:true});
    result.alpha.set(this.alpha);result.fromAlpha.set(this.alpha);result.toAlpha.set(this.alpha);
    return result;
  }
  morphTo(target:Shape,now:number,duration=500):void {
    if(target.colors.length!==this.count||target.points.length!==this.count*2||!Number.isFinite(now)||!Number.isFinite(duration)||duration<0)throw new Error('Invalid transition');
    this.update(now);this.fromX.set(this.x);this.fromY.set(this.y);this.fromAlpha.set(this.alpha);
    const sources=Array.from({length:this.count},(_,i)=>i).sort((a,b)=>morton(this.x[a]!,this.y[a]!)-morton(this.x[b]!,this.y[b]!));
    const targets=Array.from({length:this.count},(_,i)=>i).sort((a,b)=>morton(target.points[a*2]!,target.points[a*2+1]!)-morton(target.points[b*2]!,target.points[b*2+1]!));
    for(let j=0;j<this.count;j++){const i=sources[j]!,t=targets[j]!;this.toX[i]=target.points[t*2]!;this.toY[i]=target.points[t*2+1]!;this.toAlpha[i]=Number(target.visible);this.colors[i]=target.colors[t]!;}
    this.started=now;this.duration=duration;this.update(now);
  }
  update(now:number):boolean {
    const t=this.duration?clamp((now-this.started)/this.duration):1,e=easeInOut(t);
    for(let i=0;i<this.count;i++) {
      this.x[i]=t===1?this.toX[i]!:this.fromX[i]!+(this.toX[i]!-this.fromX[i]!)*e;
      this.y[i]=t===1?this.toY[i]!:this.fromY[i]!+(this.toY[i]!-this.fromY[i]!)*e;
      this.alpha[i]=t===1?this.toAlpha[i]!:this.fromAlpha[i]!+(this.toAlpha[i]!-this.fromAlpha[i]!)*e;
    }
    return t<1;
  }
  render(width:number,height:number):Raster {
    if(!Number.isInteger(width)||!Number.isInteger(height)||width<1||width>240||height<1||height>80)throw new Error('Invalid motion viewport');
    if(this.raster.width!==width||this.raster.height!==height)this.raster={width,height,masks:new Uint8Array(width*height),colors:new Uint8Array(width*height)};
    const {masks,colors}=this.raster;masks.fill(0);colors.fill(0);
    for(let i=0;i<this.count;i++) {
      if(this.alpha[i]!<.05)continue;
      const x=Math.min(width*2-1,Math.floor(this.x[i]!*width*2)),y=Math.min(height*4-1,Math.floor(this.y[i]!*height*4)),cell=(y>>2)*width+(x>>1);
      masks[cell]=masks[cell]!|DOT_BITS[y&3]![x&1]!;colors[cell]=this.colors[i]!;
    }
    return this.raster;
  }
}
export const braille = (mask:number):string => mask ? String.fromCharCode(0x2800+mask) : ' ';
export function motionEnabled(options:{ascii:boolean;color:boolean},env:Record<string,string|undefined>,screenReader=false):boolean {
  return !screenReader&&!options.ascii&&options.color&&env.AISAD_REDUCED_MOTION!=='1'&&!env.CI&&env.TERM!=='dumb'&&env.INK_SCREEN_READER!=='1';
}
