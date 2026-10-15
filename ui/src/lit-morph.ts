/** Lit particle morph for the cost plot.
 * Particles are bound to provider and day and transfer from the dots on screen: a day's dots
 * move up or down, split when its line grows and merge when it shrinks, new days flow in from
 * neighbouring days; only a provider with nothing nearby dissolves or grows from $0.
 * Providers never trade particles. On top of that: a staggered wave in the
 * navigation direction, an arc with a slight landing overshoot, a lift toward the camera with
 * perspective, a gentle plot tilt, glow and short afterimages. Lighting, z-buffering and
 * per-cell averaging follow the Codex CLI welcome mark. */
import {DOT_BITS,easeInOut,type Point,type Raster} from './motion.js';
import {band,hexToRgb,HIGHLIGHT_RGB,mix,shade} from './light.js';
export type Face={x:Float32Array;y:Float32Array;tint:Uint32Array;count:number};
export const PARTICLES=768,MORPH_MS=620,ENTER_MS=700;
const STAGGER=.3,TILT=14*Math.PI/180,TRAILS=[[.035,.42],[.07,.2]] as const;
const OVERSHOOT=.07,DRIFT=.35,LAND=.82;
const SINK=.12;
const pose=new Float64Array(3);
/** Rank dots by provider, then day (x), then value (y) and resample to a fixed count. */
export function face(points:readonly Point[],palette:readonly string[],count=PARTICLES):Face {
  if(!Number.isInteger(count)||count<1||count>4096)throw new Error('Particle count must be 1..4096');
  if(points.some(p=>!Number.isFinite(p.x)||!Number.isFinite(p.y)))throw new Error('Invalid face coordinates');
  const ordered=[...points].sort((a,b)=>(a.color??0)-(b.color??0)||a.x-b.x||a.y-b.y),tints=palette.map(hexToRgb);
  const result:Face={x:new Float32Array(count),y:new Float32Array(count),tint:new Uint32Array(count),count};
  for(let i=0;i<count;i++) {
    const p=ordered[Math.floor(i*ordered.length/count)]??{x:.5,y:1,color:0};
    result.x[i]=Math.max(0,Math.min(1,p.x));result.y[i]=Math.max(0,Math.min(1,p.y));result.tint[i]=tints[(p.color??0)%tints.length]??0xd77757;
  }
  return result;
}
/** Stable per-particle variation in [0,1). */
const hash=(i:number):number=>{let h=Math.imul(i^0x9e3779b9,0x85ebca6b);h^=h>>>13;h=Math.imul(h,0xc2b2ae35);return ((h^(h>>>16))>>>0)/4294967296;};
/**
 * Plan where every visible particle goes, transferring from the dots on screen as much as
 * possible. Per provider, the plot is split into narrow x bins (a few per day):
 * - a bin with old and new dots maps old onto new by height rank; when the day's line
 *   grows, extra dots split off the existing ones, when it shrinks, extras merge;
 * - a new bin with no old dots borrows from the nearest old bin within `reach`;
 * - old dots with no new bin within `reach` merge into the nearest one, or dissolve.
 * Only when a provider has nothing nearby do dots grow from the $0 baseline.
 * Returns the target per particle (-1 = dissolve) and spawns as [target, parent|-1].
 */
export function planMorph(px:ArrayLike<number>,py:ArrayLike<number>,ptint:ArrayLike<number>,visible:readonly number[],target:Face,bins=64,reach=8):{moves:Int32Array;spawns:[number,number][]} {
  const moves=new Int32Array(px.length).fill(-1),spawns:[number,number][]=[];
  const bin=(x:number)=>Math.max(0,Math.min(bins-1,Math.floor(x*bins)));
  const providers=new Map<number,{s:number[][];t:number[][]}>();
  const group=(tint:number)=>{let g=providers.get(tint);if(!g){g={s:Array.from({length:bins},()=>[]),t:Array.from({length:bins},()=>[])};providers.set(tint,g);}return g;};
  for(const i of visible)group(ptint[i]!).s[bin(px[i]!)]!.push(i);
  for(let j=0;j<target.count;j++)group(target.tint[j]!).t[bin(target.x[j]!)]!.push(j);
  const nearest=(lists:number[][],k:number):number=>{for(let d=1;d<=reach;d++){if(lists[k-d]?.length)return k-d;if(lists[k+d]?.length)return k+d;}return -1;};
  for(const {s,t} of providers.values()) {
    for(const list of s)list.sort((a,b)=>py[a]!-py[b]!);
    for(const list of t)list.sort((a,b)=>target.y[a]!-target.y[b]!);
    const used=new Set<number>();
    const claim=(j:number,parent:number)=>{if(parent>=0&&!used.has(parent)){used.add(parent);moves[parent]=j;}else spawns.push([j,parent]);};
    // Same bin first, so a day's own dots take priority over neighbours.
    for(let k=0;k<bins;k++){const T=t[k]!,S=s[k]!;if(!T.length||!S.length)continue;T.forEach((j,n)=>claim(j,S[Math.floor(n*S.length/T.length)]!));}
    for(let k=0;k<bins;k++){const T=t[k]!;if(!T.length||s[k]!.length)continue;const near=nearest(s,k);
      T.forEach((j,n)=>claim(j,near<0?-1:s[near]![Math.floor(n*s[near]!.length/T.length)]!));}
    // Unused old dots merge into the closest new dot nearby, else dissolve.
    for(let k=0;k<bins;k++)for(const [r,i] of s[k]!.entries()) {
      if(used.has(i))continue;
      const home=t[k]!.length?k:nearest(t,k);if(home<0)continue;
      const T=t[home]!;moves[i]=T[Math.min(T.length-1,Math.floor(r*T.length/Math.max(1,s[k]!.length)))]!;
    }
  }
  return {moves,spawns};
}
export class LitMorph {
  /** Pool size: twice the face, so arrivals always find a hidden particle. */
  readonly count:number;readonly faceCount:number;
  readonly x:Float32Array;readonly y:Float32Array;readonly z:Float32Array;readonly tint:Uint32Array;readonly alpha:Float32Array;
  private readonly fx:Float32Array;private readonly fy:Float32Array;private readonly fz:Float32Array;private readonly ft:Uint32Array;private readonly fa:Float32Array;
  private readonly tx:Float32Array;private readonly ty:Float32Array;private readonly tt:Uint32Array;private readonly ta:Float32Array;
  private readonly delay:Float32Array;private readonly lift:Float32Array;private readonly hop:Float32Array;
  private direction=1;private started=0;private duration=0;private progress=1;
  private depth=new Float32Array(0);private dots=new Uint32Array(0);
  private raster:Raster={width:0,height:0,masks:new Uint8Array(),colors:new Uint8Array(),rgb:new Uint32Array()};
  constructor(initial:Face) {
    const m=this.faceCount=initial.count,n=this.count=m*2;
    const f32=()=>new Float32Array(n);
    this.x=f32();this.y=f32().fill(1);this.z=f32();this.tint=new Uint32Array(n);this.alpha=f32();
    for(let i=0;i<m;i++){this.x[i]=initial.x[i]!;this.y[i]=initial.y[i]!;this.tint[i]=initial.tint[i]!;this.alpha[i]=1;}
    for(let i=m;i<n;i++){this.x[i]=initial.x[i-m]!;this.tint[i]=initial.tint[i-m]!;}
    this.fx=this.x.slice();this.fy=this.y.slice();this.fz=f32();this.ft=this.tint.slice();this.fa=this.alpha.slice();
    this.tx=this.x.slice();this.ty=this.y.slice();this.tt=this.tint.slice();this.ta=this.alpha.slice();this.delay=f32();
    this.lift=Float32Array.from({length:n},(_,i)=>.07+.025*hash(i));
    this.hop=Float32Array.from({length:n},(_,i)=>.06+.015*hash(i+65537));
  }
  /** Fork the visible pose; a prepared transition cannot mutate a committed one. */
  copy():LitMorph {
    const copy=new LitMorph({x:new Float32Array(this.faceCount),y:new Float32Array(this.faceCount),tint:new Uint32Array(this.faceCount),count:this.faceCount});
    for(const key of ['x','y','z','tint','alpha'] as const)copy[key].set(this[key]);
    copy.fx.set(this.x);copy.fy.set(this.y);copy.fz.set(this.z);copy.ft.set(this.tint);copy.fa.set(this.alpha);
    copy.tx.set(this.x);copy.ty.set(this.y);copy.tt.set(this.tint);copy.ta.set(this.alpha);
    copy.direction=this.direction;return copy;
  }
  /** Grow out of the $0 baseline, left to right. */
  enter(now:number,duration=ENTER_MS):void {
    const target=this.visibleFace();
    for(let i=0;i<this.count;i++){this.y[i]=1;this.z[i]=0;}
    this.morphTo(target,now,duration,-1);
  }
  private visibleFace():Face {
    const ids=[...this.alpha.keys()].filter(i=>this.alpha[i]!>.5).slice(0,this.faceCount),m=this.faceCount;
    const result:Face={x:new Float32Array(m),y:new Float32Array(m).fill(1),tint:new Uint32Array(m),count:m};
    ids.forEach((i,j)=>{result.x[j]=this.x[i]!;result.y[j]=this.y[i]!;result.tint[j]=this.tint[i]!;});
    for(let j=ids.length;j<m;j++){result.x[j]=result.x[j%Math.max(1,ids.length)]!;result.tint[j]=result.tint[j%Math.max(1,ids.length)]!;result.y[j]=ids.length?result.y[j%ids.length]!:1;}
    return result;
  }
  morphTo(target:Face|null,now:number,duration=MORPH_MS,direction=1):void {
    if(!Number.isFinite(now)||!Number.isFinite(duration)||duration<0)throw new Error('Invalid transition');
    if(target&&target.count!==this.faceCount)throw new Error('Invalid transition');
    this.update(now);
    this.fx.set(this.x);this.fy.set(this.y);this.fz.set(this.z);this.ft.set(this.tint);this.fa.set(this.alpha);
    this.direction=direction<0?-1:1;
    const visible:number[]=[],hidden:number[]=[];
    for(let i=0;i<this.count;i++)(this.alpha[i]!>.02?visible:hidden).push(i);
    // Leaving by default: sink a little and dissolve in place.
    for(let i=0;i<this.count;i++){this.tx[i]=this.fx[i]!;this.ty[i]=Math.min(1,this.fy[i]!+SINK);this.tt[i]=this.ft[i]!;this.ta[i]=0;}
    if(target) {
      const {moves,spawns}=planMorph(this.fx,this.fy,this.ft,visible,target);
      for(const i of visible){const j=moves[i]!;if(j<0)continue;this.tx[i]=target.x[j]!;this.ty[i]=target.y[j]!;this.tt[i]=target.tint[j]!;this.ta[i]=1;}
      // Spawned dots split off their parent on screen; with no parent they grow from $0.
      spawns.forEach(([j,parent],k)=>{
        const i=hidden[k];if(i===undefined)return;
        const from=parent>=0;
        this.fx[i]=from?this.fx[parent]!:target.x[j]!;this.fy[i]=from?this.fy[parent]!:1;this.fz[i]=from?this.fz[parent]!:0;
        this.ft[i]=from?this.ft[parent]!:target.tint[j]!;this.fa[i]=from?this.fa[parent]!:0;
        this.x[i]=this.fx[i]!;this.y[i]=this.fy[i]!;this.z[i]=this.fz[i]!;this.tint[i]=this.ft[i]!;this.alpha[i]=this.fa[i]!;
        this.tx[i]=target.x[j]!;this.ty[i]=target.y[j]!;this.tt[i]=target.tint[j]!;this.ta[i]=1;
      });
    }
    // The wave starts on the side we navigate from: L sweeps right-to-left like a page turn.
    // Normalize over the occupied span so a partial month never waits on empty columns.
    let low=1,high=0;
    for(let i=0;i<this.count;i++){if(!this.fa[i]&&!this.ta[i])continue;const x=(this.fx[i]!+this.tx[i]!)/2;if(x<low)low=x;if(x>high)high=x;}
    const span=Math.max(1e-6,high-low);
    for(let i=0;i<this.count;i++){const x=Math.max(0,Math.min(1,((this.fx[i]!+this.tx[i]!)/2-low)/span)),along=this.direction>0?1-x:x;this.delay[i]=STAGGER*(.96*along+.04*hash(i+7919));}
    this.started=now;this.duration=duration;
    if(!duration){this.x.set(this.tx);this.y.set(this.ty);this.z.fill(0);this.tint.set(this.tt);this.alpha.set(this.ta);this.progress=1;this.dedupe();return;}
    this.update(now);
  }
  update(now:number):boolean {
    // A settled or forked pose holds still; only a running morph advances.
    if(!this.duration){this.progress=1;return false;}
    const t=Math.max(0,Math.min(1,(now-this.started)/this.duration));this.progress=t;
    for(let i=0;i<this.count;i++) {
      if(t>=1){this.x[i]=this.tx[i]!;this.y[i]=this.ty[i]!;this.z[i]=0;this.tint[i]=this.tt[i]!;this.alpha[i]=this.ta[i]!;continue;}
      if(!this.fa[i]&&!this.ta[i])continue;
      const p=this.phase(i,t);this.at(i,p);
      this.x[i]=pose[0]!;this.y[i]=pose[1]!;this.z[i]=pose[2]!;
      const e=easeInOut(p);this.tint[i]=this.ft[i]===this.tt[i]?this.tt[i]!:mix(this.ft[i]!,unpack3(this.tt[i]!),e);
      this.alpha[i]=this.fa[i]!+(this.ta[i]!-this.fa[i]!)*e;
    }
    if(t>=1){this.duration=0;this.dedupe();}
    return t<1;
  }
  /** After a morph, particles merged onto the same dot collapse into one, so the hidden
   * half of the pool is always free for the next split. */
  private dedupe():void {
    const seen=new Set<string>();
    for(let i=0;i<this.count;i++) {
      if(this.alpha[i]!<.5)continue;
      const key=this.x[i]+':'+this.y[i]+':'+this.tint[i];
      if(seen.has(key)){this.alpha[i]=0;this.fa[i]=0;this.ta[i]=0;}else seen.add(key);
    }
  }
  /** Linear per-particle progress after its wave delay. */
  private phase(i:number,t:number):number {return Math.max(0,Math.min(1,(t-this.delay[i]!)/(1-STAGGER)));}
  /** Flight path: quintic travel with a small landing overshoot, an upward hop that drifts
   * in the navigation direction, and a lift toward the camera. Exact at p=0 and p=1. */
  private at(i:number,p:number):void {
    const e=easeInOut(p)+OVERSHOOT*Math.sin(Math.PI*p*p*p),arc=Math.sin(Math.PI*p),h=this.hop[i]!;
    pose[0]=this.fx[i]!+(this.tx[i]!-this.fx[i]!)*e+this.direction*DRIFT*h*arc;
    pose[1]=this.fy[i]!+(this.ty[i]!-this.fy[i]!)*e-h*arc;
    pose[2]=this.fz[i]!*(1-easeInOut(p))+arc*this.lift[i]!;
  }
  render(width:number,height:number):Raster {
    if(!Number.isInteger(width)||!Number.isInteger(height)||width<1||width>240||height<1||height>80)throw new Error('Invalid motion viewport');
    const W=width*2,H=height*4,size=W*H;
    if(this.raster.width!==width||this.raster.height!==height) {
      this.raster={width,height,masks:new Uint8Array(width*height),colors:new Uint8Array(width*height),rgb:new Uint32Array(width*height)};
      this.depth=new Float32Array(size);this.dots=new Uint32Array(size);
    }
    const {masks,rgb}=this.raster,depth=this.depth,dots=this.dots;
    masks.fill(0);rgb!.fill(0);depth.fill(-Infinity);
    const t=this.progress,swing=Math.sin(Math.PI*easeInOut(t));
    const theta=this.direction*TILT*swing,sy=Math.sin(theta),cy=Math.cos(theta),phi=-.05*swing,sx=Math.sin(phi),cx=Math.cos(phi);
    const half=W/2,distance=W*2.2,nx=sy,ny=-cy*sx,nz=cy*cx;
    const plot=(X:number,Y:number,Z:number,tint:number,glow:number,gain:number):void=>{
      const x1=X*cy+Z*sy,z1=-X*sy+Z*cy,y2=Y*cx-z1*sx,z2=Y*sx+z1*cx;
      const p=distance/(distance-z2),column=Math.floor(half+x1*p),row=Math.floor(H/2+y2*p);
      if(column<0||column>=W||row<0||row>=H)return;
      const index=row*W+column;if(z2<=depth[index]!)return;
      depth[index]=z2;
      let color=shade(tint,nx,ny,nz,z2/half,this.direction);
      if(glow>0)color=mix(color,HIGHLIGHT_RGB,Math.min(1,glow));
      if(gain<1){const [r,g,b]=unpack3(color);color=((27+(r-27)*gain)<<16)|((27+(g-27)*gain)<<8)|(27+(b-27)*gain);}
      dots[index]=color;
    };
    const moving=t<1;
    for(let i=0;i<this.count;i++) {
      const a=this.alpha[i]!;if(a<.06)continue;
      const X=(this.x[i]!-.5)*W,Y=(this.y[i]!-.5)*H,Z=this.z[i]!*half;
      if(!moving){plot(X,Y,Z,this.tint[i]!,0,a);continue;}
      const p=this.phase(i,t),flight=Math.sin(Math.PI*p);
      // Soft glow in flight and a bright crest as each particle lands (not when dissolving).
      plot(X,Y,Z,this.tint[i]!,flight*.22+(this.ta[i]?band(p-LAND,.14)*.75:0),a);
      if(flight<.05||!this.ta[i])continue;
      // Comet tail only where a particle moves fast, so slow regions stay crisp.
      for(const [lag,gain] of TRAILS) {
        this.at(i,this.phase(i,Math.max(0,t-lag)));
        const dx=(pose[0]!-this.x[i]!)*W,dy=(pose[1]!-this.y[i]!)*H;
        if(dx*dx+dy*dy<2.25)break;
        plot((pose[0]!-.5)*W,(pose[1]!-.5)*H,pose[2]!*half-2,this.tint[i]!,0,gain*a);
      }
    }
    for(let row=0;row<height;row++)for(let column=0;column<width;column++) {
      let mask=0,count=0,r=0,g=0,b=0;
      for(let dy=0;dy<4;dy++)for(let dx=0;dx<2;dx++) {
        const index=(row*4+dy)*W+column*2+dx;if(depth[index]===-Infinity)continue;
        const color=dots[index]!;mask|=DOT_BITS[dy]![dx]!;count++;r+=(color>>16)&255;g+=(color>>8)&255;b+=color&255;
      }
      if(!count)continue;
      const cell=row*width+column;masks[cell]=mask;rgb![cell]=(Math.round(r/count)<<16)|(Math.round(g/count)<<8)|Math.round(b/count);
    }
    return this.raster;
  }
}
const unpack3=(c:number):[number,number,number]=>[(c>>16)&255,(c>>8)&255,c&255];
