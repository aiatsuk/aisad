import {describe,expect,test} from 'bun:test';
import {face,LitMorph,MORPH_MS,ENTER_MS} from '../src/lit-morph.js';
import {band,fade,hexToRgb,rgbToHex,shade} from '../src/light.js';
import {fadeRows} from '../src/motion-ui.js';
import {rasterRows,usageMinimap} from '../src/minimap.js';
import {MinimapMorph} from '../src/minimap-motion.js';
import type {Row} from '../src/types.js';
const palette=['#d77757','#a5a9ff'];
const line=(y:number,color=0,count=64)=>face(Array.from({length:40},(_,i)=>({x:(i+.5)/40,y,color})),palette,count);
describe('lit particle morph',()=>{
  test('at rest every particle keeps its exact tint and position',()=>{
    expect(shade(0xd77757,0,0,1,0,1)).toBe(0xd77757);
    const m=new LitMorph(line(.5)),r=m.render(20,4);
    expect([...r.masks].filter(Boolean)).toHaveLength(20);
    expect(rgbToHex(r.rgb![r.masks.findIndex(Boolean)]!)).toBe(rgbToHex(0xd77757));
  });
  test('particles keep provider/day rank, blend color, lift mid-flight and settle exactly',()=>{
    const m=new LitMorph(line(.2)),b=line(.8,1);m.morphTo(b,0,MORPH_MS,1);
    expect(m.y[0]).toBeCloseTo(.2,6);m.update(MORPH_MS/2);
    expect([...m.z].some(z=>z>0)).toBe(true);expect([...m.tint].some(c=>c!==0xd77757&&c!==0xa5a9ff)).toBe(true);
    // Stagger: L sweeps from the right, so right-hand particles lead.
    expect(m.y[m.count-1]!).toBeGreaterThan(m.y[0]!);
    expect(m.update(MORPH_MS)).toBe(false);
    expect([...m.y].every(y=>Math.abs(y-.8)<1e-6)).toBe(true);expect([...m.z].every(z=>z===0)).toBe(true);expect([...m.tint].every(c=>c===0xa5a9ff)).toBe(true);
  });
  test('H mirrors the wave; forks retarget from the visible pose without mutating the original',()=>{
    const m=new LitMorph(line(.2));m.morphTo(line(.8),0,MORPH_MS,-1);m.update(MORPH_MS*.4);
    expect(m.y[0]!).toBeGreaterThan(m.y[m.count-1]!);
    const visible=[...m.x,...m.y,...m.z],fork=m.copy();fork.morphTo(line(.5),MORPH_MS*.4,MORPH_MS,1);
    expect([...fork.x,...fork.y,...fork.z].map(v=>Math.round(v*1e5))).toEqual(visible.map(v=>Math.round(v*1e5)));
    expect([...m.x,...m.y,...m.z]).toEqual(visible);
    expect(fork.update(MORPH_MS*3)).toBe(false);expect(fork.y[0]).toBeCloseTo(.5,6);
  });
  test('a partial month starts moving at once (wave spans occupied columns only)',()=>{
    const narrow=face(Array.from({length:10},(_,i)=>({x:(i+.5)/40,y:.3})),palette,64);
    const m=new LitMorph(line(.8,0,64));m.morphTo(narrow,0,MORPH_MS,1);m.update(MORPH_MS*.06);
    expect([...m.y].some(y=>Math.abs(y-.8)>1e-3)).toBe(true);
  });
  test('entrance grows from the $0 baseline',()=>{
    const m=new LitMorph(line(.3));m.enter(0,ENTER_MS);
    expect([...m.y].every(y=>y===1)).toBe(true);m.update(ENTER_MS/2);
    expect([...m.y].some(y=>y<1&&y>.3)).toBe(true);expect(m.update(ENTER_MS)).toBe(false);expect(m.y[0]).toBeCloseTo(.3,6);
  });
  test('zero-duration retargets apply immediately; rendering is deterministic, clipped and reuses buffers',()=>{
    const z=new LitMorph(line(.2));z.morphTo(line(.6),5,0);expect(z.y[0]).toBeCloseTo(.6,6);expect(z.update(10)).toBe(false);
    const make=()=>{const m=new LitMorph(line(.5));m.morphTo(line(.1),0,MORPH_MS,1);m.update(170);return m;};
    const a=make(),b=make();expect(a.render(30,5)).toEqual(b.render(30,5));
    const first=a.render(30,5).masks;expect(a.render(30,5).masks).toBe(first);expect(a.render(240,80).masks).toHaveLength(19200);
    expect(()=>a.render(0,5)).toThrow();expect(()=>face([{x:NaN,y:0}],palette)).toThrow();
    expect(()=>a.morphTo(line(.2,0,32),0)).toThrow();
  });
});
describe('fades and sweeps',()=>{
  test('fade blends toward the background and is exact at full opacity',()=>{
    expect(fade('#d77757',1)).toBe('#d77757');expect(fade('#ffffff',0)).toBe('#1c1c1c');
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
