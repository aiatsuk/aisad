import {describe,expect,test} from 'bun:test';
import {face,LitMorph,MORPH_MS,ENTER_MS,planMorph} from '../src/lit-morph.js';
import {band,fade,hexToRgb,rgbToHex,shade} from '../src/light.js';
import {fadeRows} from '../src/motion-ui.js';
import {rasterRows,usageMinimap} from '../src/minimap.js';
import {MinimapMorph} from '../src/minimap-motion.js';
import type {Row} from '../src/types.js';
const palette=['#d77757','#a5a9ff'];
const line=(y:number,color=0,count=64)=>face(Array.from({length:40},(_,i)=>({x:(i+.5)/40,y,color})),palette,count);
const visible=(m:LitMorph)=>[...m.alpha.keys()].filter(i=>m.alpha[i]!>.5);
describe('lit particle morph',()=>{
  test('at rest every particle keeps its exact tint and position',()=>{
    expect(shade(0xd77757,0,0,1,0,1)).toBe(0xd77757);
    const m=new LitMorph(line(.5)),r=m.render(20,4);
    expect(visible(m)).toHaveLength(64);expect([...r.masks].filter(Boolean)).toHaveLength(20);
    expect(rgbToHex(r.rgb![r.masks.findIndex(Boolean)]!)).toBe(rgbToHex(0xd77757));
  });
  test('same provider and day: particles move vertically, lift mid-flight and settle exactly',()=>{
    const m=new LitMorph(line(.2));m.morphTo(line(.8),0,MORPH_MS,1);
    const ids=visible(m),xs=ids.map(i=>m.x[i]!);m.update(MORPH_MS/2);
    expect([...m.z].some(z=>z>0)).toBe(true);
    // L sweeps from the right, so right-hand particles lead.
    const right=ids.reduce((a,b)=>m.x[a]!>m.x[b]!?a:b),left=ids.reduce((a,b)=>m.x[a]!<m.x[b]!?a:b);
    expect(m.y[right]!).toBeGreaterThan(m.y[left]!);
    expect(m.update(MORPH_MS)).toBe(false);
    expect(visible(m).every(i=>Math.abs(m.y[i]!-.8)<1e-6)).toBe(true);expect([...m.z].every(z=>z===0)).toBe(true);
    expect(ids.map(i=>m.x[i]!)).toEqual(xs);
  });
  test('providers never trade particles: old dots dissolve, new ones grow from $0',()=>{
    const m=new LitMorph(line(.2,0));m.morphTo(line(.8,1),0,MORPH_MS,1);
    const leaving=visible(m);expect(leaving.every(i=>m.tint[i]===0xd77757)).toBe(true);
    m.update(MORPH_MS/2);
    expect([...m.tint.keys()].filter(i=>m.alpha[i]!>.06).every(i=>m.tint[i]===0xd77757||m.tint[i]===0xa5a9ff)).toBe(true);
    m.update(MORPH_MS);
    // Duplicate samples of the same dot collapse after the morph: one particle per dot.
    const ids=visible(m);expect(ids).toHaveLength(40);
    expect(ids.every(i=>m.tint[i]===0xa5a9ff&&Math.abs(m.y[i]!-.8)<1e-6)).toBe(true);
    expect(leaving.every(i=>m.alpha[i]===0)).toBe(true);
  });
  test('a partial month keeps days in place: missing days dissolve, the rest moves at once',()=>{
    const narrow=face(Array.from({length:10},(_,i)=>({x:(i+.5)/40,y:.3})),palette,64);
    const m=new LitMorph(line(.8,0,64));m.morphTo(narrow,0,MORPH_MS,1);m.update(MORPH_MS*.06);
    expect([...m.y].some((y,i)=>m.alpha[i]!>.06&&Math.abs(y-.8)>1e-3)).toBe(true);
    m.update(MORPH_MS);
    expect(visible(m).every(i=>m.x[i]!<11/40&&Math.abs(m.y[i]!-.3)<1e-6)).toBe(true);
  });
  test('transfer plan moves, splits and merges on-screen dots; only far days use $0',()=>{
    const pts=(xs:number[],ys:number[])=>face(xs.flatMap(x=>ys.map(y=>({x,y}))),palette,xs.length*ys.length);
    const plan=(from:ReturnType<typeof face>,to:ReturnType<typeof face>)=>planMorph(from.x,from.y,from.tint,[...Array(from.count).keys()],to);
    // A day's line grows: 2 dots become 4, the extra two split off the existing ones.
    const grow=plan(pts([.5],[.4,.5]),pts([.5],[.2,.3,.4,.5]));
    expect([...grow.moves].every(j=>j>=0)).toBe(true);expect(grow.spawns.every(([,p])=>p>=0)).toBe(true);expect(grow.spawns).toHaveLength(2);
    // It shrinks: 4 dots become 2, extras merge instead of dissolving.
    const shrink=plan(pts([.5],[.2,.3,.4,.5]),pts([.5],[.4,.5]));
    expect([...shrink.moves].every(j=>j>=0)).toBe(true);expect(shrink.spawns).toHaveLength(0);
    // A new day two days away borrows from its neighbour; one far away grows from $0.
    const near=plan(pts([.50],[.5]),pts([.50,.56],[.5]));expect(near.spawns.every(([,p])=>p>=0)).toBe(true);
    const far=plan(pts([.10],[.5]),pts([.10,.90],[.5]));expect(far.spawns.some(([,p])=>p<0)).toBe(true);
    // A provider with nothing nearby dissolves.
    const gone=plan(pts([.10],[.5]),pts([.90],[.5]));expect([...gone.moves]).toEqual([-1]);
  });
  test('H mirrors the wave; forks retarget from the visible pose without mutating the original',()=>{
    const m=new LitMorph(line(.2));m.morphTo(line(.8),0,MORPH_MS,-1);m.update(MORPH_MS*.4);
    const ids=visible(m),right=ids.reduce((a,b)=>m.x[a]!>m.x[b]!?a:b),left=ids.reduce((a,b)=>m.x[a]!<m.x[b]!?a:b);
    expect(m.y[left]!).toBeGreaterThan(m.y[right]!);
    // Every particle on screen keeps its pose; only hidden ones are prepared as arrivals.
    const shown=[...m.alpha.keys()].filter(i=>m.alpha[i]!>0),pick=(k:LitMorph)=>shown.flatMap(i=>[k.x[i]!,k.y[i]!,k.z[i]!,k.alpha[i]!].map(v=>Math.round(v*1e5)));
    const all=[...m.x,...m.y,...m.z,...m.alpha],pose=pick(m),fork=m.copy();fork.morphTo(line(.5),MORPH_MS*.4,MORPH_MS,1);
    expect(pick(fork)).toEqual(pose);expect([...m.x,...m.y,...m.z,...m.alpha]).toEqual(all);
    expect(fork.update(MORPH_MS*3)).toBe(false);expect(visible(fork).every(i=>Math.abs(fork.y[i]!-.5)<1e-6)).toBe(true);
  });
  test('entrance grows from the $0 baseline',()=>{
    const m=new LitMorph(line(.3));m.enter(0,ENTER_MS);
    expect(visible(m).every(i=>m.y[i]===1)).toBe(true);m.update(ENTER_MS/2);
    expect([...m.y].some((y,i)=>m.alpha[i]!>.5&&y<1&&y>.3)).toBe(true);
    expect(m.update(ENTER_MS)).toBe(false);expect(visible(m).every(i=>Math.abs(m.y[i]!-.3)<1e-6)).toBe(true);
  });
  test('zero-duration retargets apply immediately; rendering is deterministic, clipped and reuses buffers',()=>{
    const z=new LitMorph(line(.2));z.morphTo(line(.6),5,0);expect(visible(z).every(i=>Math.abs(z.y[i]!-.6)<1e-6)).toBe(true);expect(z.update(10)).toBe(false);
    const make=()=>{const m=new LitMorph(line(.5));m.morphTo(line(.1),0,MORPH_MS,1);m.update(170);return m;};
    const a=make(),b=make();expect(a.render(30,5)).toEqual(b.render(30,5));
    const first=a.render(30,5).masks;expect(a.render(30,5).masks).toBe(first);expect(a.render(240,80).masks).toHaveLength(19200);
    expect(()=>a.render(0,5)).toThrow();expect(()=>face([{x:NaN,y:0}],palette)).toThrow();
    expect(()=>a.morphTo(line(.2,0,32),0)).toThrow();
  });
});
describe('fades and sweeps',()=>{
  test('fade blends toward the background and is exact at full opacity',()=>{
    expect(fade('#d77757',1)).toBe('#d77757');expect(fade('#ffffff',0)).toBe('#202020');
    expect(hexToRgb('#a5a9ff')).toBe(0xa5a9ff);expect(band(0,4)).toBe(1);expect(band(4,4)).toBe(0);
    const rows:Row[]=[[{text:'Title',color:'#cccccc'}],[{text:'plain'}]];
    expect(fadeRows(rows,1)).toBe(rows);
    const start=fadeRows(rows,0);expect(start[0]![0]!.color).not.toBe('#cccccc');expect(start[1]![0]).toBe(rows[1]![0]!);
    expect(start.map(r=>r.map(s=>s.text).join(''))).toEqual(['Title','plain']);
  });
  test('minimap sweep only changes color during a morph, never dots or text',()=>{
    const report=(cost:number)=>({period:{from:'2026-10-01',to:'2026-10-31',days:31},series:[{provider:'Claude',basis:'x',daily:Array.from({length:31},(_,i)=>({date:`2026-10-${String(i+1).padStart(2,'0')}`,cost_usd:(i*cost)%50,observations:1,unpriced_observations:0,incomplete:false})),known_cost_usd:1,observations:31,unpriced_observations:0,incomplete:false}]});
    const from=usageMinimap(report(7)),m=new MinimapMorph(from);
    m.morphTo(usageMinimap(report(7)),0,MORPH_MS);m.update(MORPH_MS/2);const raster=m.render(20,2);
    expect(raster.rgb).toBeDefined();expect(raster.masks).toEqual(from.raster.masks);
    expect(rasterRows(raster).map(r=>r.map(s=>s.text).join(''))).toEqual(rasterRows(from.raster).map(r=>r.map(s=>s.text).join('')));
    m.update(MORPH_MS);expect(m.render(20,2).rgb).toBeUndefined();
  });
});
